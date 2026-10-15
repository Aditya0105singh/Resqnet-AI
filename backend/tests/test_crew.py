"""Crew app: crew-driven missions, validated idempotent crew events, reconciliation, escalation."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.analysis.runs import verify_replay
from app.api import main as api
from app.metrics.metrics import compute_metrics
from app.simulation.engine import CREW_ACK_TIMEOUT, Engine, EventError
from app.simulation.scenarios import get_preset


def crew_engine(seed=3):
    """Every unit crew-driven from t=0, so the first commitments wait for their crews."""
    e = Engine(get_preset("normal", seed=seed), "decentralized")
    for r in sorted(e.world.resources):
        e.inject("CREW_MODE", {"resource_id": r, "on": True})
    e.step()
    return e


def mission(e):
    a = next(a for a in sorted(e.world.assignments.values(), key=lambda a: a.id) if a.crew_state == "awaiting_ack")
    return e.world.resources[a.resource_id], a


def crew(e, r, a, action, **kw):
    return e.inject("CREW_UPDATE", {"resource_id": r.id, "assignment_id": a.id, "action": action, "event_uuid": kw.pop("uid", str(uuid.uuid4())), "client_tick": e.world.tick, **kw})


def run_until(e, cond, limit=120):
    for _ in range(limit):
        if cond():
            return True
        e.step()
    return cond()


def test_unit_holds_until_crew_accepts_and_departs():
    e = crew_engine()
    r, a = mission(e)
    start = (r.node, r.next_node)
    for _ in range(2):
        e.step()
    assert (r.node, r.next_node) == start and r.distance_km == 0, "no movement before the crew departs"
    crew(e, r, a, "ACK")
    e.step()
    assert r.distance_km == 0, "accepting is not departing"
    crew(e, r, a, "DEPART")
    assert run_until(e, lambda: r.distance_km > 0, 5)


def test_full_crew_lifecycle_delivers_people():
    e = crew_engine()
    r, a = mission(e)
    inc = e.world.incidents[a.incident_id]
    crew(e, r, a, "ACK")
    crew(e, r, a, "DEPART")
    assert run_until(e, lambda: not r.next_node and r.node == inc.node)
    e.step()
    assert a.status == "COMMITTED" and r.load == 0, "arrival is not reported automatically"
    crew(e, r, a, "ARRIVED")
    crew(e, r, a, "BOARDED", count=r.capacity)
    assert a.status == "LOADED" and r.load > 0 and a.crew_state == "boarded"
    load = r.load
    crew(e, r, a, "DEPART")
    sh = e.world.shelters[a.shelter_id]
    assert run_until(e, lambda: not r.next_node and r.node == sh.node)
    crew(e, r, a, "ARRIVED")
    before = sh.occupancy
    crew(e, r, a, "COMPLETE")
    assert a.status == "COMPLETED" and sh.occupancy == before + load and r.assignment_id != a.id
    nxt = e.world.assignments.get(r.assignment_id or "")
    assert nxt is None or nxt.crew_state == "awaiting_ack", "a new mission also waits for the crew to accept it"
    assert compute_metrics(e)["invariant_violations"] == 0


def test_crew_count_caps_the_load():
    e = crew_engine()
    r, a = mission(e)
    inc = e.world.incidents[a.incident_id]
    crew(e, r, a, "ACK")
    crew(e, r, a, "DEPART")
    run_until(e, lambda: not r.next_node and r.node == inc.node)
    crew(e, r, a, "ARRIVED")
    crew(e, r, a, "BOARDED", count=1)
    assert r.load == 1


def test_duplicate_event_uuid_is_a_no_op():
    e = crew_engine()
    r, a = mission(e)
    crew(e, r, a, "ACK", uid="same-uuid")
    ev = crew(e, r, a, "ACK", uid="same-uuid")
    assert "duplicate" in ev.effects[0] and a.crew_state == "acked"


def test_invalid_steps_are_rejected_with_reasons():
    e = crew_engine()
    r, a = mission(e)
    with pytest.raises(EventError, match="cannot report people on board now"):
        crew(e, r, a, "BOARDED", count=3)
    crew(e, r, a, "ACK")
    crew(e, r, a, "DEPART")
    with pytest.raises(EventError, match="arrival not recorded"):
        crew(e, r, a, "ARRIVED")


def test_queued_update_for_cancelled_mission_is_rejected():
    """An update queued offline must not apply to a mission that was cancelled meanwhile."""
    e = crew_engine()
    r, a = mission(e)
    crew(e, r, a, "ACK")
    e.inject("CANCEL_ASSIGNMENT", {"assignment_id": a.id, "reason": "dispatcher reassigned"})
    with pytest.raises(EventError, match="cancelled: operator cancelled"):
        crew(e, r, a, "DEPART")


def test_unacknowledged_mission_times_out_and_is_renegotiated():
    e = crew_engine()
    r, a = mission(e)
    for _ in range(CREW_ACK_TIMEOUT + 1):
        e.step()
    assert a.status == "CANCELLED" and "did not acknowledge" in a.cancel_reason


def test_cannot_continue_disables_unit_and_frees_the_incident():
    e = crew_engine()
    r, a = mission(e)
    crew(e, r, a, "ACK")
    crew(e, r, a, "CANNOT_CONTINUE", reason="engine trouble")
    assert r.status == "DISABLED" and a.status == "CANCELLED"


def test_unsafe_landing_closes_the_next_segment():
    e = crew_engine()
    r, a = mission(e)
    crew(e, r, a, "ACK")
    path = e.remaining_path(r)
    if len(path) < 2:
        pytest.skip("unit already at the incident")
    ev = crew(e, r, a, "UNSAFE_LANDING", reason="debris")
    assert "unsafe" in ev.effects[0] and any(x.manual_closed for x in e.world.edges.values())


def test_crew_events_replay_exactly():
    e = crew_engine()
    r, a = mission(e)
    crew(e, r, a, "ACK", uid="u1")
    crew(e, r, a, "ACK", uid="u1")
    crew(e, r, a, "DEPART", uid="u2")
    for _ in range(10):
        e.step()
    assert verify_replay(e)["identical"]


def test_crew_view_api():
    client = TestClient(api.app)
    sid = client.post("/api/simulations", json={"scenario": "normal", "strategy": "decentralized", "seed": 3}).json()["id"]
    rid = "B1"
    client.post(f"/api/simulations/{sid}/events", json={"type": "CREW_MODE", "params": {"resource_id": rid, "on": True}})
    for _ in range(30):
        v = client.get(f"/api/simulations/{sid}/crew/{rid}").json()
        if v["mission"]:
            break
        client.post(f"/api/simulations/{sid}/step", json={"ticks": 1})
    assert v["unit"]["crew_driven"] and v["mission"]
    assert v["mission"]["step"] == "awaiting_ack" and v["allowed_actions"][:1] == ["ACK"]
    assert v["mission"]["route"]["nodes"] and "messages" in v["mission"]["incident"]
    body = {"type": "CREW_UPDATE", "params": {"resource_id": rid, "assignment_id": v["mission"]["assignment"], "action": "ACK", "event_uuid": "abc", "client_tick": v["tick"]}}
    assert client.post(f"/api/simulations/{sid}/events", json=body).status_code == 200
    assert client.post(f"/api/simulations/{sid}/events", json=body).status_code == 200, "replayed outbox item is accepted as a no-op"
    assert client.get(f"/api/simulations/{sid}/crew/{rid}").json()["mission"]["step"] == "acked"
    assert client.get(f"/api/simulations/{sid}/crew/X9").status_code == 404
