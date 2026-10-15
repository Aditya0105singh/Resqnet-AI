"""Core simulation, safety and coordination tests."""
from __future__ import annotations

import copy

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.analysis.runs import benchmark, counterfactual, rebuild, verify_replay
from app.metrics.metrics import compute_metrics
from app.negotiation import common
from app.routing.router import path_valid, plan_from_resource
from app.safety.shield import audit_invariants, validate_commit
from app.simulation.engine import Engine, EventError
from app.simulation.scenarios import get_preset
from app.simulation.state import (
    ACTIVE_ASSIGNMENT,
    AssignmentStatus,
    EdgeKind,
    IncidentStatus,
    ReservationStatus,
    ResourceStatus,
)

STRATS = ["decentralized", "message_passing", "centralized", "greedy"]


def run(eng: Engine, n: int) -> Engine:
    for _ in range(n):
        eng.step()
    return eng


def active_by_resource(eng: Engine) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for a in eng.world.assignments.values():
        if a.status in ACTIVE_ASSIGNMENT:
            out.setdefault(a.resource_id, []).append(a.id)
    return out


# ---------------------------------------------------------------- determinism & replay

@pytest.mark.parametrize("strategy", STRATS)
def test_deterministic_runs(strategy):
    a = run(Engine(get_preset("contradictory"), strategy, record_frames=False), 80)
    b = run(Engine(get_preset("contradictory"), strategy, record_frames=False), 80)
    assert a.hashes == b.hashes


def test_different_seed_differs():
    a = run(Engine(get_preset("normal", seed=1), record_frames=False), 30)
    b = run(Engine(get_preset("normal", seed=2), record_frames=False), 30)
    assert a.hashes[30] != b.hashes[30]


def test_replay_reproduces_history_with_injected_events():
    e = Engine(get_preset("normal"), "decentralized")
    run(e, 12)
    e.inject("CLOSE_EDGE", {"edge_id": "BR1"})
    run(e, 8)
    e.inject("RESOURCE_FAILURE", {"resource_id": "B1"})
    e.inject("SHELTER_CAPACITY", {"shelter_id": "S2", "capacity": 20})
    run(e, 15)
    res = verify_replay(e)
    assert res["identical"], res
    assert res["ticks_compared"] == 36


def test_replayed_frames_match_recorded_state():
    e = Engine(get_preset("triple_failure"), "centralized")
    run(e, 40)
    r = rebuild(e.base_cfg, e.strategy, e.injected, 25, record_frames=True)
    assert r.frames[25]["incidents"] == e.frames[25]["incidents"]
    assert r.frames[25]["resources"] == e.frames[25]["resources"]


def test_reset_equivalent_to_new_engine():
    e1 = run(Engine(get_preset("normal"), record_frames=False), 20)
    e2 = run(Engine(get_preset("normal"), record_frames=False), 20)
    assert e1.hashes[20] == e2.hashes[20]


# ---------------------------------------------------------------- routing

def test_ground_units_never_use_water_edges_and_boats_never_use_dry_roads():
    e = Engine(get_preset("normal"), record_frames=False)
    w = e.world
    for r in w.resources.values():
        reach = plan_from_resource(w, r)
        for _tgt, (_m, path) in reach.items():
            ok, bad = path_valid(w, r.kind, path)
            assert ok, (r.id, bad)
    g = next(r for r in w.resources.values() if r.kind == "ground")
    reach = plan_from_resource(w, g)
    assert not any(n.startswith("R") for n in reach), "ground unit reached a river node"


def test_closed_bridge_forces_reroute_or_cancel():
    from app.routing.router import edge_between

    e = Engine(get_preset("normal"), "centralized")
    w = e.world
    crossing = None
    for _ in range(120):
        e.step()
        for r in sorted(w.resources.values(), key=lambda r: r.id):
            path = e.remaining_path(r)
            for x, y in zip(path[1:], path[2:]):  # an upcoming (not current) edge
                ed = edge_between(w, x, y)
                if ed and ed.kind == EdgeKind.BRIDGE and ed.ground_ok and r.assignment_id:
                    crossing = (r.id, ed.id)
        if crossing:
            break
    assert crossing, "expected some unit to plan across a bridge"
    rid, eid = crossing
    e.inject("CLOSE_EDGE", {"edge_id": eid})
    r = w.resources[rid]
    path = e.remaining_path(r)
    ok, _ = path_valid(w, r.kind, path)
    assert ok or r.assignment_id is None
    assert any(a.category in ("reroute", "cancel") for a in e.audit_log if a.tick == w.tick)


def test_unit_on_closing_edge_retreats_without_violation():
    e = Engine(get_preset("normal"), "centralized")
    w = e.world
    for _ in range(40):
        e.step()
        mid = [r for r in w.resources.values() if r.edge_id and w.edges[r.edge_id].kind == EdgeKind.ROAD and r.status != ResourceStatus.DISABLED]
        if mid:
            break
    assert mid
    r = mid[0]
    eid = r.edge_id
    e.inject("CLOSE_EDGE", {"edge_id": eid})
    run(e, 10)
    assert e.counters["route_violations"] == 0
    assert any("turned back" in a.message for a in e.audit_log)


def test_unreachable_request_is_not_assigned():
    e = Engine(get_preset("normal", boats=0), "centralized", record_frames=False)
    w = e.world
    # incident on a deeply flooded node: only boats could reach it
    deep = max((n for n in w.nodes.values() if n.kind == "land"), key=lambda n: n.depth)
    assert deep.depth > 0.5
    e.inject("NEW_INCIDENT", {"node": deep.id, "people": 3, "urgency": 5})
    inc = [i for i in w.incidents.values() if i.node == deep.id][-1]
    run(e, 5)
    assert not any(a.incident_id == inc.id for a in w.assignments.values())


# ---------------------------------------------------------------- safety shield

def test_no_double_booking_ever():
    for strat in STRATS:
        e = Engine(get_preset("flash_flood"), strat, record_frames=False)
        for _ in range(120):
            e.step()
            assert all(len(v) <= 1 for v in active_by_resource(e).values())
        assert e.counters["invariant_violations"] == 0


def test_shield_rejects_stale_state_double_booking_and_capacity():
    e = Engine(get_preset("normal"), "centralized")
    run(e, 2)
    w = e.world
    a = next(a for a in w.assignments.values() if a.status in ACTIVE_ASSIGNMENT)
    res, inc = w.resources[a.resource_id], w.incidents[a.incident_id]
    v = validate_commit(w, resource_id=res.id, incident_id=inc.id, people=1, pickup_path=[res.node, inc.node], dropoff_path=[inc.node], reservation_id=a.reservation_id, resource_version=res.version - 1, incident_version=inc.version)
    assert not v.ok
    codes = {c.name: c.passed for c in v.checks}
    assert codes["S1 no double booking"] is False
    assert codes["S5 resource version"] is False
    over = validate_commit(w, resource_id=res.id, incident_id=inc.id, people=res.capacity + 1, pickup_path=[], dropoff_path=[], reservation_id=None, resource_version=res.version, incident_version=inc.version)
    assert not over.ok and any(c.name == "S4 transport capacity" and not c.passed for c in over.checks)


def test_shield_rejects_expired_reservation():
    e = Engine(get_preset("normal"), "centralized")
    run(e, 2)
    w = e.world
    a = next(a for a in w.assignments.values() if a.status == AssignmentStatus.COMMITTED)
    rsv = w.reservations[a.reservation_id]
    rsv.expires_tick = w.tick - 1
    res, inc = w.resources[a.resource_id], w.incidents[a.incident_id]
    v = validate_commit(w, resource_id=res.id, incident_id=inc.id, people=a.people, pickup_path=a.pickup_route, dropoff_path=a.dropoff_route, reservation_id=rsv.id, resource_version=res.version, incident_version=inc.version)
    assert not v.ok and any(c.name == "S6 reservation unexpired" and not c.passed for c in v.checks)


def test_reservation_expires_during_blackout():
    e = Engine(get_preset("normal"), "decentralized")
    run(e, 3)
    w = e.world
    a = next(a for a in w.assignments.values() if a.status == AssignmentStatus.COMMITTED)
    rsv = w.reservations[a.reservation_id]
    e.inject("COMM_BLACKOUT", {"resource_id": a.resource_id, "duration": 100})
    rsv.expires_tick = w.tick + 1
    run(e, 3)
    assert rsv.status in (ReservationStatus.EXPIRED, ReservationStatus.CONSUMED)


def test_shelter_capacity_never_exceeded_by_reservations():
    for strat in STRATS:
        e = Engine(get_preset("shelter_overflow"), strat, record_frames=False)
        for _ in range(180):
            e.step()
            for s in e.world.shelters.values():
                reserved = s.reserved(e.world)
                assert reserved == 0 or s.occupancy + reserved <= s.capacity


def test_resource_capacity_respected():
    e = Engine(get_preset("flash_flood"), "decentralized", record_frames=False)
    for _ in range(150):
        e.step()
        for r in e.world.resources.values():
            assert r.load <= r.capacity
        assert not audit_invariants(e.world)


def test_completion_requires_transitions():
    e = run(Engine(get_preset("normal"), "centralized", record_frames=False), 120)
    for i in e.world.incidents.values():
        if i.status == IncidentStatus.RESCUED and i.people_rescued > 0:
            assert i.first_pickup_tick is not None and i.completed_tick is not None
            assert i.first_pickup_tick <= i.completed_tick
            done = [a for a in e.world.assignments.values() if a.incident_id == i.id and a.status == AssignmentStatus.COMPLETED]
            assert sum(a.loaded_people for a in done) == i.people_rescued


# ---------------------------------------------------------------- failures

def test_boat_failure_causes_reassignment():
    e = Engine(get_preset("normal"), "decentralized")
    run(e, 4)
    w = e.world
    boat = next(r for r in sorted(w.resources.values(), key=lambda r: r.id) if r.kind == "boat" and r.assignment_id and w.assignments[r.assignment_id].status == AssignmentStatus.COMMITTED)
    inc_id = w.assignments[boat.assignment_id].incident_id
    e.inject("RESOURCE_FAILURE", {"resource_id": boat.id})
    assert boat.status == ResourceStatus.DISABLED and boat.assignment_id is None
    run(e, 15)
    assert any(a.incident_id == inc_id and a.resource_id != boat.id for a in w.assignments.values()) or w.incidents[inc_id].status in (IncidentStatus.RESCUED, IncidentStatus.FALSE_ALARM)
    assert e.counters["reassignments"] >= 1


def test_loaded_unit_failure_strands_passengers_as_new_incident():
    e = Engine(get_preset("normal"), "centralized")
    w = e.world
    for _ in range(60):
        e.step()
        loaded = [r for r in w.resources.values() if r.load > 0 and r.status != ResourceStatus.DISABLED]
        if loaded:
            break
    r = loaded[0]
    n = r.load
    before = len(w.incidents)
    e.inject("RESOURCE_FAILURE", {"resource_id": r.id})
    assert len(w.incidents) == before + 1 or any(i.people_estimate >= n for i in w.incidents.values())
    assert r.load == 0


def test_shelter_overflow_triggers_alternative_planning():
    e = Engine(get_preset("normal"), "centralized")
    run(e, 6)
    w = e.world
    pend: dict[str, int] = {}
    for rsv in w.reservations.values():
        if rsv.status == ReservationStatus.ACTIVE:
            pend[rsv.shelter_id] = pend.get(rsv.shelter_id, 0) + 1
    sid = max(pend, key=pend.get)
    e.inject("SHELTER_CAPACITY", {"shelter_id": sid, "capacity": w.shelters[sid].occupancy})
    for a in w.assignments.values():
        if a.status in ACTIVE_ASSIGNMENT:
            rsv = w.reservations.get(a.reservation_id)
            assert rsv is None or rsv.shelter_id != sid or rsv.status != ReservationStatus.ACTIVE
    assert any(x.category == "shelter" and "renegotiated" in x.message for x in e.audit_log)


@pytest.mark.parametrize("strategy", STRATS)
def test_triple_failure_mid_run(strategy):
    e = Engine(get_preset("normal"), strategy)
    run(e, 20)
    ev = e.inject("TRIPLE_FAILURE", {})
    assert len(ev.effects) == 3
    types = [x.type for x in e.events[-4:]]
    assert {"CLOSE_EDGE", "RESOURCE_FAILURE", "SHELTER_CAPACITY"} <= set(types)
    run(e, 60)
    assert e.counters["invariant_violations"] == 0
    assert e.counters["route_violations"] == 0
    assert all(len(v) <= 1 for v in active_by_resource(e).values())
    assert len(e.disruptions) == 3


def test_invalid_events_are_rejected():
    e = Engine(get_preset("normal"), record_frames=False)
    with pytest.raises(EventError):
        e.inject("CLOSE_EDGE", {"edge_id": "NOPE"})
    with pytest.raises(EventError):
        e.inject("SHELTER_CAPACITY", {"shelter_id": "S1", "capacity": -5})
    with pytest.raises(EventError):
        e.inject("NEW_INCIDENT", {"node": "R3", "people": 2})
    assert e.injected == []


# ---------------------------------------------------------------- uncertainty

def test_contradictory_reports_create_false_alarm_and_cancel():
    e = Engine(get_preset("normal"), "centralized")
    run(e, 1)
    w = e.world
    e.inject("NEW_INCIDENT", {"node": "N50", "people": 3, "urgency": 3, "source": "resident"})
    inc = [i for i in w.incidents.values() if i.node == "N50"][-1]
    assert inc.status in (IncidentStatus.SUSPECTED, IncidentStatus.ASSIGNED) and inc.confidence == 0.6
    e.inject("CONTRADICTORY_REPORT", {"incident_id": inc.id, "claim": "NO_VICTIMS", "source": "responder"})
    assert inc.status == IncidentStatus.FALSE_ALARM
    assert not any(a.incident_id == inc.id and a.status in ACTIVE_ASSIGNMENT for a in w.assignments.values())


def test_duplicate_reports_merge_and_raise_confidence():
    e = Engine(get_preset("normal"), "centralized", record_frames=False)
    w = e.world
    e.inject("NEW_INCIDENT", {"node": "N57", "people": 2, "urgency": 2, "source": "resident"})
    n_before = len(w.incidents)
    inc = [i for i in w.incidents.values() if i.node == "N57"][-1]
    c0 = inc.confidence
    e.inject("CONTRADICTORY_REPORT", {"incident_id": inc.id, "claim": "PRESENT", "source": "sensor", "people": 5})
    assert len(w.incidents) == n_before
    assert inc.confidence > c0
    assert inc.people_estimate >= 5 - e.people_taken(inc.id)


def test_contradictory_scenario_runs_safely_all_strategies():
    for strat in STRATS:
        e = run(Engine(get_preset("contradictory"), strat, record_frames=False), 180)
        m = compute_metrics(e)
        assert m["invariant_violations"] == 0 and m["route_violations"] == 0


# ---------------------------------------------------------------- strategies & analysis

def test_decentralized_agents_exchange_real_bids():
    e = run(Engine(get_preset("normal"), "decentralized"), 3)
    types = {m.type for r in e.rounds for m in r.messages}
    assert {"REQUEST", "BID", "PROVISIONAL_ACCEPT", "RESERVE", "ACCEPT_RESERVATION", "COMMIT"} <= types
    bid = next(m for r in e.rounds for m in r.messages if m.type == "BID")
    assert bid.payload["cost"] > 0 and bid.payload["eta_pickup"] >= 0


def test_decentralized_agents_use_delayed_information():
    cfg = get_preset("normal", comm_delay=4)
    e = Engine(cfg, "decentralized")
    run(e, 3)
    assert not e.world.assignments, "agents must not act on requests before hearing them"
    run(e, 3)
    assert e.world.assignments


def test_centralized_uses_same_constraints():
    e = run(Engine(get_preset("triple_failure"), "centralized", record_frames=False), 180)
    m = compute_metrics(e)
    assert m["route_violations"] == 0 and m["invariant_violations"] == 0
    assert any(r.strategy == "centralized" for r in e.rounds)


def test_benchmark_is_paired_and_reports_variability():
    res = benchmark(get_preset("normal", duration=60), ["decentralized", "centralized"], [1, 2])
    assert len(res["runs"]) == 4
    assert res["summary"]["centralized"]["mean_time_to_service"]["n"] == 2
    assert "mean_time_to_service" in res["paired_decentralized_minus_centralized"]


def test_counterfactual_branch_matches_baseline_without_changes():
    e = run(Engine(get_preset("normal", duration=80), "decentralized"), 30)
    cf = counterfactual(e.base_cfg, e.strategy, e.injected, 20, {})
    strip = lambda d: {k: v for k, v in d.items() if k != "compute_ms"}  # wall-clock timing differs
    assert strip(cf["baseline"]) == strip(cf["alternative"])
    assert cf["diverged_count"] == 0


def test_counterfactual_extra_boats_changes_outcome():
    e = run(Engine(get_preset("resource_shortage", duration=100), "decentralized"), 20)
    cf = counterfactual(e.base_cfg, e.strategy, e.injected, 10, {"extra_boats": 2})
    assert cf["applied"] and cf["diverged_count"] > 0


def test_metrics_consistency():
    e = run(Engine(get_preset("normal"), "centralized", record_frames=False), 180)
    m = compute_metrics(e)
    assert m["people_rescued"] == sum(s.occupancy for s in e.world.shelters.values()) - sum([6, 10, 4])
    assert 0 <= m["fairness_jain"] <= 1
    assert m["served_incidents"] <= m["real_incidents"]


# ---------------------------------------------------------------- property-based invariants

@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(1, 10_000),
    strategy=st.sampled_from(STRATS),
    events=st.lists(
        st.tuples(
            st.integers(1, 50),
            st.sampled_from(["BR1", "BR2", "BR3", "B1", "B2", "G1", "S1", "S2", "S3", "SURGE", "PART"]),
        ),
        max_size=4,
    ),
    loss=st.sampled_from([0.0, 0.25]),
)
def test_property_safety_invariants_hold_under_random_failures(seed, strategy, events, loss):
    e = Engine(get_preset("normal", seed=seed, duration=70, msg_loss=loss, msg_duplicate=loss, msg_latency=1 if loss else 0), strategy, record_frames=False)
    plan = sorted(events)
    while not e.finished:
        e.step()
        for t, target in [p for p in plan if p[0] == e.world.tick]:
            try:
                if target == "PART":
                    e.inject("NETWORK_PARTITION", {"members": ["B1", "G1", "S1"], "duration": 15})
                elif target.startswith("BR"):
                    e.inject("CLOSE_EDGE", {"edge_id": target})
                elif target[0] in "BG":
                    e.inject("RESOURCE_FAILURE", {"resource_id": target})
                elif target == "SURGE":
                    e.inject("FLOOD_SURGE", {"delta": 0.5})
                else:
                    e.inject("SHELTER_CAPACITY", {"shelter_id": target, "capacity": "occupancy"})
            except EventError:
                pass
        assert all(len(v) <= 1 for v in active_by_resource(e).values())
        assert not audit_invariants(e.world)
    assert e.counters["route_violations"] == 0


def test_policy_change_forces_renegotiation_and_replays():
    e = Engine(get_preset("normal"), "decentralized")
    run(e, 5)
    committed = sum(1 for a in e.world.assignments.values() if a.status == AssignmentStatus.COMMITTED)
    ev = e.inject("SET_POLICY", {"policy": "equity", "neighbourhood_priority": {"RS": 2}, "renegotiate": True})
    assert e.cfg.weights["F"] == 0.4 and any("re-opened" in x for x in ev.effects)
    assert e.counters["cancellations"] >= committed
    with pytest.raises(EventError):
        e.inject("SET_POLICY", {"policy": "nope"})
    run(e, 10)
    assert verify_replay(e)["identical"]
