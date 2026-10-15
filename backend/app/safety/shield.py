"""Safety shield — an independent validator that runs before every commitment and
before every movement step. It checks proposals against the *authoritative* world
state, never against an agent's beliefs, and it is shared by every strategy.

Invariants enforced:
  S1  no resource holds incompatible simultaneous assignments (no double booking)
  S2  no shelter exceeds effective capacity
  S3  no movement / route traverses an edge prohibited for that resource's mode
  S4  no rescue exceeds the resource's declared transport capacity
  S5  no commitment is made from stale entity versions
  S6  reservations must be ACTIVE, unexpired, and bound to the commitment
  S7  disabled / disconnected resources cannot accept new commitments
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..routing.router import path_valid
from ..simulation.state import (
    ACTIVE_ASSIGNMENT,
    IncidentStatus,
    ReservationStatus,
    ResourceStatus,
    WorldState,
)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class ShieldResult:
    ok: bool
    checks: list[Check] = field(default_factory=list)
    reason: str = ""
    code: str = ""
    bad_edge: Optional[str] = None


def validate_commit(
    world: WorldState,
    *,
    resource_id: str,
    incident_id: str,
    people: int,
    pickup_path: list[str],
    dropoff_path: list[str],
    reservation_id: Optional[str],
    resource_version: int,
    incident_version: int,
) -> ShieldResult:
    checks: list[Check] = []
    res = world.resources.get(resource_id)
    inc = world.incidents.get(incident_id)
    fail_code = ""
    bad_edge = None

    def add(name: str, ok: bool, detail: str, code: str) -> None:
        nonlocal fail_code
        checks.append(Check(name, ok, detail))
        if not ok and not fail_code:
            fail_code = code

    if res is None or inc is None:
        return ShieldResult(False, [Check("entities exist", False, "unknown resource or incident")], "unknown entity", "UNKNOWN")

    add("S7 resource operational", res.status != ResourceStatus.DISABLED, f"{res.id} status {res.status}", "RESOURCE_DISABLED")
    add("S7 resource connected", res.blackout_until < world.tick, f"{res.id} comms {'down' if res.blackout_until >= world.tick else 'up'}", "RESOURCE_DISCONNECTED")
    busy = [a.id for a in world.assignments.values() if a.resource_id == res.id and a.status in ACTIVE_ASSIGNMENT]
    add("S1 no double booking", not busy, f"active commitments: {busy or 'none'}", "DOUBLE_BOOKING")
    add("S5 resource version", res.version == resource_version, f"bid v{resource_version} / current v{res.version}", "STALE_STATE")
    add("S5 incident version", inc.version == incident_version, f"bid v{incident_version} / current v{inc.version}", "STALE_STATE")
    add("incident still open", inc.status not in (IncidentStatus.RESCUED, IncidentStatus.FALSE_ALARM), f"{inc.id} {inc.status}", "INCIDENT_CLOSED")
    add("S4 transport capacity", 0 < people <= res.capacity, f"{people} people / capacity {res.capacity}", "OVER_CAPACITY")

    ok1, e1 = path_valid(world, res.kind, pickup_path)
    add("S3 pickup route traversable", ok1, f"blocked edge {e1}" if not ok1 else f"{max(0, len(pickup_path) - 1)} edges valid for {res.kind}", "INVALID_ROUTE")
    ok2, e2 = path_valid(world, res.kind, dropoff_path)
    add("S3 dropoff route traversable", ok2, f"blocked edge {e2}" if not ok2 else f"{max(0, len(dropoff_path) - 1)} edges valid for {res.kind}", "INVALID_ROUTE")
    bad_edge = e1 or e2
    if pickup_path and dropoff_path:
        add("route continuity", pickup_path[-1] == inc.node and dropoff_path[0] == inc.node, "pickup ends / dropoff starts at incident node", "INVALID_ROUTE")

    rsv = world.reservations.get(reservation_id) if reservation_id else None
    if rsv is None:
        add("S6 reservation held", False, "no shelter reservation", "NO_RESERVATION")
    else:
        sh = world.shelters[rsv.shelter_id]
        add("S6 reservation active", rsv.status == ReservationStatus.ACTIVE, f"{rsv.id} {rsv.status}", "RESERVATION_INVALID")
        add("S6 reservation unexpired", rsv.expires_tick >= world.tick, f"expires t={rsv.expires_tick}", "RESERVATION_EXPIRED")
        add("S6 reservation bound", rsv.resource_id == res.id and rsv.incident_id == inc.id and rsv.people >= people, f"{rsv.people} seats for {rsv.resource_id}->{rsv.incident_id}", "RESERVATION_INVALID")
        add("S2 shelter capacity", sh.occupancy + sh.reserved(world) <= sh.capacity, f"{sh.id}: occ {sh.occupancy} + reserved {sh.reserved(world)} / cap {sh.capacity}", "SHELTER_OVER_CAPACITY")
        if dropoff_path:
            add("dropoff at reserved shelter", dropoff_path[-1] == sh.node, f"route ends at {dropoff_path[-1]} / shelter {sh.node}", "INVALID_ROUTE")

    ok = all(c.passed for c in checks)
    reason = "" if ok else next(f"{c.name}: {c.detail}" for c in checks if not c.passed)
    return ShieldResult(ok, checks, reason, fail_code, bad_edge)


def validate_move(world: WorldState, resource_id: str, edge_id: str) -> Check:
    """Gate run before a resource enters an edge."""
    res = world.resources[resource_id]
    e = world.edges[edge_id]
    ok = e.ground_ok if res.kind == "ground" else e.boat_ok
    return Check("S3 movement gate", ok, f"{res.id} -> {e.id} ({e.kind}, depth {e.depth:.2f}m{', closed: ' + e.closed_reason if e.manual_closed else ''})")


def audit_invariants(world: WorldState) -> list[str]:
    """Global invariant sweep run every tick; any message here is a violation."""
    out: list[str] = []
    per_res: dict[str, int] = {}
    for a in world.assignments.values():
        if a.status in ACTIVE_ASSIGNMENT:
            per_res[a.resource_id] = per_res.get(a.resource_id, 0) + 1
    out += [f"S1 {r} has {n} active assignments" for r, n in per_res.items() if n > 1]
    for s in world.shelters.values():
        if s.occupancy > s.capacity and s.reserved(world) > 0:
            out.append(f"S2 {s.id} reservations while over capacity")
        if s.occupancy + s.reserved(world) > s.capacity and s.reserved(world) > 0:
            out.append(f"S2 {s.id} occupancy+reserved {s.occupancy + s.reserved(world)} > cap {s.capacity}")
    for r in world.resources.values():
        if r.load > r.capacity:
            out.append(f"S4 {r.id} load {r.load} > capacity {r.capacity}")
    return out
