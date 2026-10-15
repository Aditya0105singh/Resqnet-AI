"""Uncertainty-aware SOS report reconciliation.

Reports are matched to an existing incident when they fall within the larger of
the two location uncertainties (plus 50 m) and arrive within 45 minutes.

Evidence aggregation (heuristic, NOT a calibrated probability):
    Reports are first grouped into *independent sources*: verbatim forwards of one
    message share a content fingerprint and form one group whose reliability is the
    best in the group (copying a message does not make it more true).
    cp = 1 - Π(1 - r_g)   over independent PRESENT groups (r = source reliability metadata)
    cn = 1 - Π(1 - r_g)   over independent NO_VICTIMS groups
    confidence = cp                     if no contradicting reports
               = cp * cp / (cp + cn)    otherwise
Status: VERIFIED >= 0.80, SUSPECTED >= 0.50, else UNVERIFIED.
FALSE_ALARM when cn >= 0.85 and cn > cp + 0.2 (and nobody has been picked up),
when a dispatcher dismisses it, or when a unit on scene finds nobody.
DISPUTED (abstain) when both cp >= 0.5 and cn >= 0.5 but neither rule above fires:
the system does not pick a side. It waits for a dispatcher decision
(RESOLVE_DISPUTE confirm / dismiss / verify) and, failing one, sends a single
verification visit after a review window (rule E5).

Conflicting fields are resolved conservatively: people = max reported (missing
-> assume 4), urgency = max reported (missing -> 3), location = most reliable,
most precise report.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from .state import Incident, IncidentReport, IncidentStatus
from .world import DEADLINE_BY_URGENCY, nearest_land_nbhd

MATCH_WINDOW = 45
ASSUMED_PEOPLE = 4
ASSUMED_URGENCY = 3
DISPUTE_THRESHOLD = 0.5


def independent_groups(reports: list[IncidentReport], dedup: bool = True) -> list[list[IncidentReport]]:
    """Group reports by observable content fingerprint. Reports without one, or with
    dedup disabled (ablation), are each their own source."""
    groups: dict[str, list[IncidentReport]] = {}
    for r in reports:
        key = r.fingerprint if (dedup and r.fingerprint) else r.id
        groups.setdefault(key, []).append(r)
    return [groups[k] for k in sorted(groups)]


def _combine(groups: list[list[IncidentReport]]) -> float:
    return 1 - math.prod(1 - max(r.reliability for r in g) for g in groups) if groups else 0.0


def _dist(world: Any, a: str, b: str) -> float:
    na, nb = world.nodes[a], world.nodes[b]
    return math.hypot(na.x - nb.x, na.y - nb.y)


def find_match(world: Any, rep: IncidentReport) -> Optional[Incident]:
    best = None
    for inc in world.incidents.values():
        if inc.status == IncidentStatus.RESCUED:
            continue
        if rep.tick - inc.reported_tick > MATCH_WINDOW:
            continue
        inc_unc = max((world.reports[r].location_uncertainty_km for r in inc.report_ids), default=0.0)
        d = _dist(world, rep.node, inc.node)
        if d <= max(rep.location_uncertainty_km, inc_unc) + 0.05:
            key = (round(d, 4), -inc.reported_tick, inc.id)
            if best is None or key < best[0]:
                best = (key, inc)
    return best[1] if best else None


def ingest(engine: Any, rep: IncidentReport) -> Optional[Incident]:
    world = engine.world
    world.reports[rep.id] = rep
    inc = find_match(world, rep)
    if inc is None:
        if rep.claim != "PRESENT":
            engine.audit("incident", f"{rep.id} ({rep.source}) reports no victims at {rep.node} — no matching incident, logged only", {"report": rep.id}, "info")
            return None
        iid = world.next_id("I")
        inc = Incident(
            id=iid,
            node=rep.node,
            neighbourhood=nearest_land_nbhd(world, rep.node),
            reported_tick=world.tick,
            urgency=rep.urgency or ASSUMED_URGENCY,
            people_estimate=rep.people or ASSUMED_PEOPLE,
            deadline_tick=world.tick + DEADLINE_BY_URGENCY[rep.urgency or ASSUMED_URGENCY],
            version=0,
        )
        world.incidents[iid] = inc
        engine.audit("incident", f"New incident {iid} at {rep.node} from {rep.source} report {rep.id} ({rep.note or 'SOS'})", {"incident": iid, "report": rep.id}, "warn")
    else:
        engine.audit("incident", f"{rep.id} ({rep.source}, {rep.claim.lower().replace('_', ' ')}) reconciled into {inc.id}" + (f" — {rep.note}" if rep.note else ""), {"incident": inc.id, "report": rep.id}, "info")
    rep.incident_id = inc.id
    inc.report_ids.append(rep.id)
    if rep.truth_id and rep.truth_id not in inc.truth_ids:
        inc.truth_ids.append(rep.truth_id)
    recompute(engine, inc)
    return inc


def recompute(engine: Any, inc: Incident) -> None:
    world = engine.world
    reps = [world.reports[r] for r in inc.report_ids]
    present = [r for r in reps if r.claim == "PRESENT"]
    negative = [r for r in reps if r.claim == "NO_VICTIMS"]
    dedup = bool(getattr(engine.cfg, "fusion_dedup", True))
    pg, ng = independent_groups(present, dedup), independent_groups(negative, dedup)
    cp, cn = _combine(pg), _combine(ng)
    if inc.verdict == "confirmed":
        negative, cn = [], 0.0  # the dispatcher overruled the negative reports
    inc.evidence = {
        "cp": round(cp, 3),
        "cn": round(cn, 3),
        "present_reports": len(present),
        "present_sources": len(pg),
        "negative_reports": len([r for r in reps if r.claim == "NO_VICTIMS"]),
        "negative_sources": len(ng),
        "forwarded_copies": sum(len(g) - 1 for g in pg + ng),
        "verdict": inc.verdict,
    }
    before = (inc.node, inc.urgency, inc.people_estimate, inc.status, round(inc.confidence, 3))
    if inc.visited:
        conf = 1.0
    elif inc.verdict == "confirmed":
        conf = max(cp, 0.8)  # dispatcher confirmation (e.g. a call-back) counts as verification
    else:
        conf = cp if not negative else (cp * cp / (cp + cn) if cp + cn > 0 else 0.0)
    inc.confidence = round(conf, 3)
    if not inc.visited and present:
        reported = [r.people for r in present if r.people is not None]
        max_people = max(reported) if reported else ASSUMED_PEOPLE
        loaded = engine.people_taken(inc.id)
        inc.people_estimate = max(0, max_people - loaded)
        best = sorted(present, key=lambda r: (-r.reliability, r.location_uncertainty_km, r.tick, r.id))[0]
        if best.node != inc.node:
            engine.audit("incident", f"{inc.id} location revised {inc.node} → {best.node} (more reliable {best.source} report {best.id})", {"incident": inc.id}, "warn")
            inc.node = best.node
            inc.neighbourhood = nearest_land_nbhd(world, best.node)
    urg = [r.urgency for r in present if r.urgency is not None]
    if urg and max(urg) > inc.urgency:
        inc.urgency = max(urg)
        inc.deadline_tick = inc.reported_tick + DEADLINE_BY_URGENCY[inc.urgency]
    dismissed = inc.verdict == "dismissed"
    false_alarm = not inc.visited and inc.first_pickup_tick is None and (dismissed or (bool(negative) and cn >= 0.85 and cn > cp + 0.2))
    disputed = not inc.visited and not false_alarm and inc.verdict not in ("confirmed", "dismissed") and cp >= DISPUTE_THRESHOLD and cn >= DISPUTE_THRESHOLD
    if disputed and inc.disputed_since is None:
        inc.disputed_since = world.tick
        engine.audit("incident", f"{inc.id} DISPUTED: {len(pg)} independent source(s) for (cp={cp:.2f}) vs {len(ng)} against (cn={cn:.2f}) — no automatic dispatch; awaiting dispatcher review", {"incident": inc.id}, "warn")
    elif not disputed and inc.disputed_since is not None:
        inc.disputed_since = None
        why = "verified on scene" if inc.visited else f"dispatcher verdict: {inc.verdict}" if inc.verdict else "new evidence settled it"
        engine.audit("incident", f"{inc.id} dispute resolved ({why})", {"incident": inc.id}, "info")
    if false_alarm and inc.status != IncidentStatus.FALSE_ALARM:
        inc.status = IncidentStatus.FALSE_ALARM
        engine.on_false_alarm(inc, "dismissed by dispatcher" if dismissed else f"responder evidence (cn={cn:.2f}) outweighs SOS evidence (cp={cp:.2f})")
    elif not false_alarm and inc.status == IncidentStatus.FALSE_ALARM and not inc.visited:
        engine.audit("incident", f"{inc.id} re-opened: new evidence contradicts the false-alarm classification", {"incident": inc.id}, "warn")
        inc.status = IncidentStatus.UNVERIFIED
    engine.refresh_incident_status(inc)
    after = (inc.node, inc.urgency, inc.people_estimate, inc.status, round(inc.confidence, 3))
    if after != before or inc.version == 0:
        inc.version += 1
        engine.publish(inc)
