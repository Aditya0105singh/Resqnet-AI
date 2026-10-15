"""Serialisation of world state into UI frames, static geometry and state hashes."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from ..negotiation.common import DISPUTE_REVIEW, DISPUTE_REVIEW_URGENT, unassigned_people
from .flood import river_level
from .state import ACTIVE_ASSIGNMENT, ReservationStatus, WorldState


def static_world(world: WorldState) -> dict[str, Any]:
    return {
        "name": "Riverbend (synthetic)",
        "disclaimer": "Synthetic city for research and education. Not real geography or live flood data.",
        "nodes": [{"id": n.id, "x": n.x, "y": n.y, "elevation": n.elevation, "neighbourhood": n.neighbourhood, "kind": n.kind, "label": n.label} for n in world.nodes.values()],
        "edges": [{"id": e.id, "u": e.u, "v": e.v, "kind": e.kind, "length_km": e.length_km, "name": e.name, "clearance": e.clearance if e.clearance < 90 else None} for e in world.edges.values()],
        "neighbourhoods": [{"id": n.id, "name": n.name, "flood_factor": n.flood_factor} for n in world.neighbourhoods.values()],
    }


def _pos(world: WorldState, r: Any) -> tuple[float, float]:
    a = world.nodes[r.node]
    if r.next_node:
        b = world.nodes[r.next_node]
        p = r.edge_progress
        return (round(a.x + (b.x - a.x) * p, 4), round(a.y + (b.y - a.y) * p, 4))
    return (a.x, a.y)


def frame(engine: Any) -> dict[str, Any]:
    w: WorldState = engine.world
    resources = []
    for r in sorted(w.resources.values(), key=lambda r: r.id):
        x, y = _pos(w, r)
        path = ([r.next_node] if r.next_node else []) + list(r.route)
        a = w.assignments.get(r.assignment_id or "")
        resources.append(
            {
                "id": r.id,
                "name": r.name,
                "kind": r.kind,
                "capacity": r.capacity,
                "load": r.load,
                "status": r.status,
                "x": x,
                "y": y,
                "node": r.node,
                "next_node": r.next_node,
                "route": path,
                "assignment_id": r.assignment_id,
                "incident_id": a.incident_id if a else None,
                "shelter_id": a.shelter_id if a else None,
                "eta": (a.eta_pickup_tick if r.status == "EN_ROUTE_PICKUP" else a.eta_dropoff_tick) if a else None,
                "blackout_until": r.blackout_until if r.blackout_until >= w.tick else None,
                "partition": w.partition_of(r.id),
                "version": r.version,
                "distance_km": round(r.distance_km, 2),
                "busy_ticks": r.busy_ticks,
                "idle_ticks": r.idle_ticks,
                "speed_kmh": r.speed_kmh,
                "home_node": r.home_node,
            }
        )
    incidents = []
    for i in sorted(w.incidents.values(), key=lambda i: i.id):
        n = w.nodes[i.node]
        incidents.append(
            {
                "id": i.id,
                "node": i.node,
                "x": n.x,
                "y": n.y,
                "neighbourhood": i.neighbourhood,
                "status": i.status,
                "urgency": i.urgency,
                "people": i.people_estimate,
                "unassigned": unassigned_people(w, i),
                "rescued": i.people_rescued,
                "confidence": i.confidence,
                "provisional": i.provisional,
                "deadline": i.deadline_tick,
                "reported_tick": i.reported_tick,
                "first_pickup_tick": i.first_pickup_tick,
                "completed_tick": i.completed_tick,
                "reports": list(i.report_ids),
                "version": i.version,
                "visited": i.visited,
                "evidence": i.evidence,
                "disputed_since": i.disputed_since,
                "review_due": (i.disputed_since + (DISPUTE_REVIEW_URGENT if i.urgency >= 4 else DISPUTE_REVIEW)) if i.disputed_since is not None else None,
                "verdict": i.verdict,
                "assigned": sorted(a.resource_id for a in w.assignments.values() if a.incident_id == i.id and a.status in ACTIVE_ASSIGNMENT),
            }
        )
    shelters = []
    for s in sorted(w.shelters.values(), key=lambda s: s.id):
        n = w.nodes[s.node]
        reserved = s.reserved(w)
        shelters.append({"id": s.id, "name": s.name, "node": s.node, "x": n.x, "y": n.y, "capacity": s.capacity, "occupancy": s.occupancy, "reserved": reserved, "free": s.capacity - s.occupancy - reserved, "version": s.version})
    edges = {e.id: [int(e.ground_ok), int(e.boat_ok), int(e.manual_closed), round(e.depth, 2), round(e.risk, 2)] for e in w.edges.values()}
    depths = {n.id: round(n.depth, 2) for n in w.nodes.values() if n.depth > 0}
    assignments = [
        {
            "id": a.id,
            "resource_id": a.resource_id,
            "incident_id": a.incident_id,
            "shelter_id": a.shelter_id,
            "reservation_id": a.reservation_id,
            "people": a.people,
            "loaded": a.loaded_people,
            "status": a.status,
            "created_tick": a.created_tick,
            "eta_pickup": a.eta_pickup_tick,
            "eta_dropoff": a.eta_dropoff_tick,
            "reroutes": a.reroutes,
            "decision_id": a.decision_id,
            "round_id": a.round_id,
            "cancel_reason": a.cancel_reason,
            "version": a.version,
        }
        for a in sorted(w.assignments.values(), key=lambda a: a.id)
    ]
    from ..metrics.metrics import compute_metrics

    m = compute_metrics(engine)
    return {
        "tick": w.tick,
        "version": w.version,
        "strategy": w.strategy,
        "scenario": w.scenario,
        "finished": engine.finished,
        "duration": engine.cfg.duration,
        "river_level": round(river_level(w, engine.cfg.flood_severity, engine.cfg.flood_peak_tick), 2),
        "flood_offset": w.flood_offset,
        "coordinator": {"available": w.tick >= w.coordinator_down_until, "restores_at": w.coordinator_down_until},
        "proposals": [p for p in engine.proposals.values() if p["status"] == "PENDING"] + [p for p in engine.proposals.values() if p["status"] != "PENDING"][-8:],
        "network": {
            "partitions": [p for p in w.partitions if p["start"] <= w.tick <= p["until"]],
            "transport": dict(engine.mas.bus.stats) if engine.mas else None,
            "latency": engine.cfg.msg_latency,
            "loss": engine.cfg.msg_loss,
        },
        "route_ghosts": [g for g in engine.route_ghosts if w.tick - g["tick"] <= 15],
        "resources": resources,
        "incidents": incidents,
        "shelters": shelters,
        "edges": edges,
        "depths": depths,
        "assignments": assignments,
        "reservations": [
            {"id": r.id, "shelter_id": r.shelter_id, "resource_id": r.resource_id, "incident_id": r.incident_id, "people": r.people, "expires": r.expires_tick, "status": r.status}
            for r in sorted(w.reservations.values(), key=lambda r: r.id)
            if r.status == ReservationStatus.ACTIVE
        ],
        "metrics": m,
        "last_event_id": engine.events[-1].id if engine.events else None,
        "audit_count": len(engine.audit_log),
        "round_count": len(engine.rounds),
    }


def state_hash(engine: Any) -> str:
    w: WorldState = engine.world
    core = {
        "t": w.tick,
        "coordinator_down_until": w.coordinator_down_until,
        "r": [(r.id, r.node, r.next_node, round(r.edge_progress, 6), r.status, r.load, r.assignment_id, r.route) for r in sorted(w.resources.values(), key=lambda r: r.id)],
        "i": [(i.id, i.node, i.status, i.people_estimate, i.people_rescued, i.version) for i in sorted(w.incidents.values(), key=lambda i: i.id)],
        "s": [(s.id, s.capacity, s.occupancy, s.version) for s in sorted(w.shelters.values(), key=lambda s: s.id)],
        "a": [(a.id, a.status, a.resource_id, a.incident_id, a.shelter_id) for a in sorted(w.assignments.values(), key=lambda a: a.id)],
        "e": sorted(e.id for e in w.edges.values() if not e.ground_ok),
    }
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:16]
