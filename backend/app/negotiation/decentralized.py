"""Decentralised negotiation: contract-net bidding + deferred acceptance.

Protocol per round
  1. REQUEST     incident agents broadcast open requests (agents hear them after `comm_delay`)
  2. BID         each idle rescue agent plans on its *own believed* network and bids on
                 its top-3 requests (cost, ETA, seats, preferred shelter)
  3. PROVISIONAL_ACCEPT / REJECT
                 incident-proposing deferred acceptance (Gale–Shapley): each incident
                 proposes to its best remaining bidder; a rescue agent holding several
                 proposals keeps the one with its lowest cost and REJECTs the rest
  4. RESERVE     matched agent asks shelter agents for capacity (shelter accepts/rejects)
  5. SAFETY      the shield validates route, capacity, versions and reservation
  6. COMMIT      versioned assignment; failures release reservations and re-enter next pass

Tie-breaking (deterministic): incident priority = (urgency desc, deadline asc,
confidence desc, id); agent preference = (cost asc, incident priority); bid
ranking = (cost asc, resource id). Up to 3 passes per tick.

Information model: agents know their own state exactly, hear incident publications
and network closures `comm_delay` ticks late (or not at all during a comms blackout),
and discover closures physically. They never read other agents' positions.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from ..routing.router import believed_closed
from .common import (
    Candidate,
    NegotiationRound,
    available_resources,
    evaluate,
    is_eligible,
    neighbourhood_waits,
    priority_key,
    shelter_offers,
    try_commit,
)
from ..simulation.state import IncidentStatus

TOP_K_BIDS = 3
MAX_PASSES = 3


def visible_publication(inc: Any, tick: int) -> Optional[dict]:
    best = None
    for p in inc.publications:
        if p["tick"] <= tick:
            best = p
        else:
            break
    return best


def run(engine: Any, trigger: str) -> Optional[NegotiationRound]:
    world = engine.world
    cfg = engine.cfg
    agents = available_resources(world)
    if not agents:
        return None
    delay = max(0, int(cfg.comm_delay))
    seen_tick = world.tick - delay
    views: dict[str, dict] = {}
    for inc in sorted(world.incidents.values(), key=priority_key):
        pub = visible_publication(inc, seen_tick)
        if not pub or pub["status"] in (IncidentStatus.RESCUED, IncidentStatus.FALSE_ALARM):
            continue
        if not pub.get("eligible") or pub["unassigned"] <= 0:
            continue
        # the incident agent itself knows its *current* state: withdrawn requests are not re-sent
        ok, _ = is_eligible(world, inc)
        if not ok or inc.status in (IncidentStatus.RESCUED, IncidentStatus.FALSE_ALARM):
            continue
        views[inc.id] = pub
    if not views:
        return None

    t0 = time.perf_counter()
    rnd = NegotiationRound(engine.next_round_id(), world.tick, "decentralized", trigger)
    rnd.incidents = list(views.keys())
    rnd.resources = [a.id for a in agents]
    for iid, v in views.items():
        rnd.msg("REQUEST", iid, "broadcast", iid, people=v["unassigned"], urgency=v["urgency"], node=v["node"], version=v["version"], heard_by=len(agents))
    offers = shelter_offers(world)
    for sid, free in offers.items():
        rnd.msg("OFFER", sid, "broadcast", "", free=free)
    waits = neighbourhood_waits(world)
    cache: dict = {}

    # ---- 2. bidding: every agent plans on its own beliefs
    all_cands: dict[str, list[Candidate]] = {iid: [] for iid in views}
    bids: dict[str, list[Candidate]] = {iid: [] for iid in views}
    for ag in agents:
        closed = believed_closed(world, ag, delay)
        evals = [evaluate(world, cfg, ag, views[iid], offers, waits, closed, cache, knowledge=f"belief@t{seen_tick}") for iid in views]
        for c in evals:
            all_cands[c.incident_id].append(c)
        feasible = sorted((c for c in evals if c.feasible), key=lambda c: (c.cost, priority_key(engine.world.incidents[c.incident_id])))
        for c in feasible[:TOP_K_BIDS]:
            bids[c.incident_id].append(c)
            rnd.msg("BID", ag.id, c.incident_id, c.incident_id, cost=round(c.cost, 4), eta_pickup=round(c.eta_pickup, 1), eta_total=round(c.eta_dropoff, 1), people=c.people, shelter=c.shelter_options[0][0], version=c.inc_version)

    # ---- incident agents screen bids against their current version
    for iid, lst in bids.items():
        inc = world.incidents[iid]
        keep = []
        for c in lst:
            if c.inc_version != inc.version:
                rnd.msg("REJECT", iid, c.resource_id, iid, reason=f"stale bid: request v{c.inc_version}, current v{inc.version} — rebid after update")
            else:
                keep.append(c)
        bids[iid] = sorted(keep, key=lambda c: (c.cost, c.resource_id))

    decisions: dict[str, dict] = {}
    for iid in views:
        decisions[iid] = engine.new_decision(rnd, world.incidents[iid], all_cands[iid], views[iid])

    excluded: set[tuple[str, str]] = set()
    busy: set[str] = set()
    done_incidents: set[str] = set()
    for _pass in range(MAX_PASSES):
        # ---- 3. deferred acceptance
        queue = [iid for iid in sorted(views, key=lambda i: priority_key(world.incidents[i])) if iid not in done_incidents and bids[iid]]
        next_idx = {iid: 0 for iid in queue}
        held: dict[str, Candidate] = {}
        while queue:
            rnd.iterations += 1
            iid = queue.pop(0)
            lst = [c for c in bids[iid] if c.resource_id not in busy and (c.resource_id, iid) not in excluded]
            if next_idx[iid] >= len(lst):
                continue
            c = lst[next_idx[iid]]
            next_idx[iid] += 1
            rnd.msg("PROVISIONAL_ACCEPT", iid, c.resource_id, iid, cost=round(c.cost, 4))
            cur = held.get(c.resource_id)
            if cur is None:
                held[c.resource_id] = c
                continue
            new_key = (c.cost, priority_key(world.incidents[iid]))
            cur_key = (cur.cost, priority_key(world.incidents[cur.incident_id]))
            if new_key < cur_key:
                held[c.resource_id] = c
                rnd.msg("REJECT", c.resource_id, cur.incident_id, cur.incident_id, reason=f"{c.resource_id} prefers {iid} (cost {c.cost:.3f} < {cur.cost:.3f})")
                decisions[cur.incident_id]["rejections"].append({"resource": c.resource_id, "reason": f"preferred {iid} (cost {c.cost:.3f} < {cur.cost:.3f})"})
                queue.append(cur.incident_id)
            else:
                rnd.msg("REJECT", c.resource_id, iid, iid, reason=f"{c.resource_id} holds {cur.incident_id} (cost {cur.cost:.3f} <= {c.cost:.3f})")
                decisions[iid]["rejections"].append({"resource": c.resource_id, "reason": f"held {cur.incident_id} (cost {cur.cost:.3f} <= {c.cost:.3f})"})
                queue.append(iid)
        if not held:
            break
        matched = sorted(held.values(), key=lambda c: priority_key(world.incidents[c.incident_id]))
        progress = False
        for c in matched:
            rnd.matching.append({"pass": _pass + 1, "resource": c.resource_id, "incident": c.incident_id, "cost": round(c.cost, 4)})
            dec = decisions[c.incident_id]
            dec["selected"] = c.to_dict()
            a = try_commit(engine, c, rnd, dec)
            busy.add(c.resource_id)
            if a is None:
                excluded.add((c.resource_id, c.incident_id))
                busy.discard(c.resource_id)
                continue
            progress = True
            done_incidents.add(c.incident_id)
        if not progress:
            break

    rnd.duration_ms = (time.perf_counter() - t0) * 1000
    for iid, dec in decisions.items():
        engine.finalize_decision(dec)
    return rnd
