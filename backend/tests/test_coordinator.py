import pytest

from app.analysis.runs import verify_replay
from app.simulation.engine import Engine, EventError
from app.simulation.scenarios import get_preset
from app.safety.shield import audit_invariants


@pytest.mark.parametrize("strategy", ["centralized", "greedy", "decentralized"])
def test_outage_dispatch_and_restoration(strategy):
    engine = Engine(get_preset("normal"), strategy)
    engine.inject("COORDINATOR_OUTAGE", {"duration": 10})
    for _ in range(9):
        engine.step()
    assert bool(engine.world.assignments) == (strategy == "decentralized")
    assert not engine.last_frame()["coordinator"]["available"]
    engine.step()
    assert engine.last_frame()["coordinator"]["available"]
    assert engine.world.assignments
    assert not audit_invariants(engine.world)
    assert verify_replay(engine)["identical"]


@pytest.mark.parametrize("duration", [0, -1, 301, True, "10", 1.5])
def test_invalid_outage_is_atomic(duration):
    engine = Engine(get_preset("normal"))
    with pytest.raises(EventError):
        engine.inject("COORDINATOR_OUTAGE", {"duration": duration})
    assert engine.world.coordinator_down_until == 0
    assert not engine.injected


def test_existing_missions_continue_during_outage():
    engine = Engine(get_preset("normal"), "centralized")
    for _ in range(5):
        engine.step()
    assignments = set(engine.world.assignments)
    distance = sum(r.distance_km for r in engine.world.resources.values())
    engine.inject("COORDINATOR_OUTAGE", {"duration": 20})
    for _ in range(5):
        engine.step()
    assert set(engine.world.assignments) == assignments
    assert sum(r.distance_km for r in engine.world.resources.values()) > distance


def test_bridge_demo_breaks_a_live_route_and_preserves_evidence():
    from app.routing.router import edge_between
    engine = Engine(get_preset("bridge_dependency", seed=7))
    bridge = None
    for _ in range(30):
        engine.step()
        for resource in engine.world.resources.values():
            path = engine.remaining_path(resource)
            for a, b in zip(path, path[1:]):
                edge = edge_between(engine.world, a, b)
                if resource.assignment_id and edge.kind == "bridge" and edge.ground_ok:
                    bridge = edge.id
        if bridge:
            break
    assert bridge, "demo must have a live bridge-dependent route"
    engine.inject("TRIPLE_FAILURE", {"edge_id": bridge})
    assert engine.last_frame()["route_ghosts"]
    assert any(g["edge"] == bridge for g in engine.route_ghosts)
    assert not audit_invariants(engine.world)
    assert verify_replay(engine)["identical"]
