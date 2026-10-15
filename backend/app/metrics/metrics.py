"""Performance metrics — computed only from simulation state and events.

Definitions
  time to service      first pickup tick - first report tick (served incidents)
  deadline miss        urgency>=4 incident whose first pickup is after its deadline,
                       or still waiting past it
  unmet                ground-truth people not delivered to a shelter (includes people
                       wrongly dismissed as false alarms); `unmet_incidents` counts
                       real incidents not fully rescued
  idle-with-demand     ticks a working unit sat IDLE while an eligible request was uncovered
  utilisation          busy ticks / (busy + idle ticks) over working units
  route violations     traversals of a prohibited edge (the shield should keep this at 0)
  fairness (Jain)      J = (Σx)² / (n·Σx²) over neighbourhood mean waits x_n, where a
                       neighbourhood's wait uses time-to-service for served incidents and
                       the current wait for unserved ones. 1.0 = perfectly even.
  recovery time        ticks from a disruption until every affected incident is again
                       covered (or terminal) and no affected unit is HOLDING
"""
from __future__ import annotations

import statistics
from typing import Any

from ..simulation.state import ACTIVE_ASSIGNMENT, IncidentStatus, ResourceStatus


def _real(engine: Any, inc: Any) -> bool:
    return any(engine.world.truth.get(t, {}).get("exists") for t in inc.truth_ids)


def compute_metrics(engine: Any) -> dict[str, Any]:
    w = engine.world
    now = w.tick
    incs = list(w.incidents.values())
    real = [i for i in incs if _real(engine, i)]
    served = [i for i in real if i.first_pickup_tick is not None]
    tts = [i.first_pickup_tick - i.reported_tick for i in served]
    urgent = [i for i in real if i.urgency >= 4]
    misses = [i for i in urgent if (i.first_pickup_tick is not None and i.first_pickup_tick > i.deadline_tick) or (i.first_pickup_tick is None and now > i.deadline_tick)]
    truth_people = sum(t["people"] for t in w.truth.values() if t["exists"] and t["tick"] <= now and not str(t["id"]).startswith("STR"))
    rescued = sum(i.people_rescued for i in incs)
    in_transit = sum(r.load for r in w.resources.values())
    revealed_remaining = sum(t["remaining"] for t in w.truth.values() if t["exists"] and t["tick"] <= now)
    unmet_people = revealed_remaining + in_transit
    open_incs = [i for i in incs if i.status not in (IncidentStatus.RESCUED, IncidentStatus.FALSE_ALARM)]
    unmet_incidents = [i for i in real if i.status != IncidentStatus.RESCUED]

    working = [r for r in w.resources.values()]
    busy = sum(r.busy_ticks for r in working)
    idle = sum(r.idle_ticks for r in working)
    idle_demand = sum(r.idle_with_demand_ticks for r in working)

    per_n: dict[str, dict[str, Any]] = {}
    for nid, nb in w.neighbourhoods.items():
        mine = [i for i in real if i.neighbourhood == nid]
        waits = [(i.first_pickup_tick - i.reported_tick) if i.first_pickup_tick is not None else (now - i.reported_tick) for i in mine]
        per_n[nid] = {
            "id": nid,
            "name": nb.name,
            "incidents": len(mine),
            "served": sum(1 for i in mine if i.first_pickup_tick is not None),
            "rescued_people": sum(i.people_rescued for i in mine),
            "mean_wait": round(statistics.fmean(waits), 1) if waits else None,
            "max_wait": max(waits) if waits else None,
            "deadline_misses": sum(1 for i in misses if i.neighbourhood == nid),
        }
    xs = [v["mean_wait"] for v in per_n.values() if v["mean_wait"] is not None]
    jain = (sum(xs) ** 2 / (len(xs) * sum(x * x for x in xs))) if xs and sum(x * x for x in xs) > 0 else 1.0

    rounds = engine.rounds
    msgs = sum(1 for r in rounds for m in r.messages if m.type != "LOST")
    rec = [d["recovery"] for d in engine.disruptions if d["recovery"] is not None]
    return {
        "tick": now,
        "incidents_reported": len(incs),
        "real_incidents": len(real),
        "open_incidents": len(open_incs),
        "served_incidents": len(served),
        "rescued_incidents": sum(1 for i in real if i.status == IncidentStatus.RESCUED),
        "people_total_known": truth_people,
        "people_rescued": rescued,
        "people_in_transit": in_transit,
        "unmet_people": unmet_people,
        "unmet_incidents": len(unmet_incidents),
        "mean_time_to_service": round(statistics.fmean(tts), 2) if tts else None,
        "median_time_to_service": round(statistics.median(tts), 2) if tts else None,
        "p90_time_to_service": round(sorted(tts)[int(0.9 * (len(tts) - 1))], 2) if tts else None,
        "urgent_incidents": len(urgent),
        "deadline_misses": len(misses),
        "idle_ticks": idle,
        "idle_with_demand_ticks": idle_demand,
        "utilisation": round(busy / (busy + idle), 3) if busy + idle else 0.0,
        "route_violations": engine.counters["route_violations"],
        "blocked_moves": engine.counters["blocked_moves"],
        "safety_rejections": engine.counters["safety_rejections"],
        "invariant_violations": engine.counters["invariant_violations"],
        "fairness_jain": round(jain, 3),
        "fairness_by_neighbourhood": list(per_n.values()),
        "reassignments": engine.counters["reassignments"],
        "reroutes": engine.counters["reroutes"],
        "cancellations": engine.counters["cancellations"],
        "false_alarm_visits": engine.counters["false_alarm_visits"],
        "provisional_dispatches": engine.counters["provisional_dispatches"],
        "negotiation_rounds": len(rounds),
        "negotiation_messages": msgs,
        "messages_lost": (engine.mas.bus.stats["lost"] + engine.mas.bus.stats["partitioned"]) if getattr(engine, "mas", None) else 0,
        "transport": dict(engine.mas.bus.stats) if getattr(engine, "mas", None) else None,
        "compute_ms": round(sum(r.duration_ms for r in rounds), 2),
        "disruptions": len(engine.disruptions),
        "mean_recovery_time": round(statistics.fmean(rec), 2) if rec else None,
        "unresolved_disruptions": sum(1 for d in engine.disruptions if d["recovery"] is None),
        "service_rate": round(min(1.0, rescued / truth_people), 3) if truth_people else None,
        "outages": len(getattr(engine, "outages", [])),
        "outage_uncovered_people_minutes": sum(o["uncovered_people_minutes"] for o in getattr(engine, "outages", [])),
        "commitments_during_outage": sum(o["commitments"] for o in getattr(engine, "outages", [])),
        "mean_outage_backlog_clear": round(statistics.fmean(bc), 2) if (bc := [o["backlog_clear"] for o in getattr(engine, "outages", []) if o["backlog_clear"] is not None]) else None,
        "outages_unrecovered": sum(1 for o in getattr(engine, "outages", []) if o["backlog_clear"] is None and o["end"] < now),
        "active_assignments": sum(1 for a in w.assignments.values() if a.status in ACTIVE_ASSIGNMENT),
        "units_available": sum(1 for r in w.resources.values() if r.status == ResourceStatus.IDLE),
        "units_disabled": sum(1 for r in w.resources.values() if r.status == ResourceStatus.DISABLED),
    }


SUMMARY_KEYS = [
    "mean_time_to_service",
    "median_time_to_service",
    "deadline_misses",
    "unmet_people",
    "unmet_incidents",
    "people_rescued",
    "idle_with_demand_ticks",
    "utilisation",
    "route_violations",
    "safety_rejections",
    "fairness_jain",
    "reassignments",
    "reroutes",
    "negotiation_messages",
    "messages_lost",
    "compute_ms",
    "mean_recovery_time",
    "unresolved_disruptions",
    "service_rate",
    "outage_uncovered_people_minutes",
    "commitments_during_outage",
    "mean_outage_backlog_clear",
    "outages_unrecovered",
]
