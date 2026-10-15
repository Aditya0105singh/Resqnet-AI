"""Message-passing agents: transport semantics, idempotency, timeouts, leases, partitions."""
import pytest

from app.analysis.runs import verify_replay
from app.metrics.metrics import compute_metrics
from app.negotiation.transport import Bus
from app.simulation.engine import Engine, EventError
from app.simulation.scenarios import get_preset
from app.simulation.state import ACTIVE_ASSIGNMENT, ReservationStatus


def run(scenario="normal", seed=3, until=None, check=None, **ov):
    e = Engine(get_preset(scenario, seed=seed, **ov), "message_passing", record_frames=False)
    while not e.finished and (until is None or e.world.tick < until):
        e.step()
        if check:
            check(e)
    return e


def messages(e):
    return [m for r in e.rounds for m in r.messages]


# ------------------------------------------------------------------ bus unit tests


class _W:
    """Minimal world stand-in for the bus: tick + reachability."""

    def __init__(self):
        self.tick = 0
        self.cut = set()

    def reachable(self, a, b):
        return not ({a, b} & self.cut)


def test_bus_latency_and_dedup():
    w, bus = _W(), Bus(latency=2, duplicate=1.0, seed=1)
    bus.send(w, "PING", "a", "b")
    w.tick = 1
    bus.deliver(w)
    assert bus.take("b") == []
    w.tick = 2
    bus.deliver(w)
    got = bus.take("b")
    assert [m.type for m in got] == ["PING"]  # delivered twice, processed once
    assert bus.stats["duplicated"] == 1 and bus.stats["deduplicated"] == 1


def test_bus_drops_messages_across_partition_at_delivery():
    w, bus = _W(), Bus(latency=1, seed=1)
    bus.send(w, "PING", "a", "b")
    w.tick, w.cut = 1, {"b"}
    bus.deliver(w)
    assert bus.take("b") == [] and bus.stats["partitioned"] == 1


def test_bus_loss_is_seeded():
    def lost(seed):
        w, bus = _W(), Bus(loss=0.5, seed=seed)
        for _ in range(200):
            bus.send(w, "PING", "a", "b")
        return bus.stats["lost"]

    assert lost(4) == lost(4) and 50 < lost(4) < 150


# ------------------------------------------------------------------ protocol


def test_message_passing_is_deterministic_and_replays():
    a, b = run(until=60), run(until=60)
    assert a.hashes == b.hashes
    a.inject("NETWORK_PARTITION", {"members": ["B1", "G1"], "duration": 20})
    for _ in range(30):
        a.step()
    v = verify_replay(a)
    assert v["identical"], v


@pytest.mark.parametrize("scenario", ["normal", "lossy_network", "network_partition", "triple_failure", "contradictory"])
def test_message_passing_is_safe(scenario):
    e = run(scenario)
    m = compute_metrics(e)
    assert m["invariant_violations"] == 0
    assert m["route_violations"] == 0
    assert m["people_rescued"] > 0


def test_every_commit_follows_a_reservation_grant_for_that_proposal():
    e = run(until=80)
    msgs = messages(e)
    granted = {(m.to, m.payload["proposal"]) for m in msgs if m.type == "ACCEPT_RESERVATION"}
    confirms = [m for m in msgs if m.type == "CONFIRM"]
    commits = [m for m in msgs if m.type == "COMMIT"]
    assert commits and len(confirms) == len(commits)
    for c in confirms:
        assert (c.frm, c.payload["proposal"]) in granted
    # commits are made by the rescue agent itself, not a coordinator
    assert all(m.frm in e.world.resources for m in commits)


def test_duplicate_delivery_never_double_reserves():
    seen_bound = []

    def check(e):
        by_assignment = {}
        for r in e.world.reservations.values():
            if r.status == ReservationStatus.ACTIVE:
                by_assignment[r.assignment_id] = by_assignment.get(r.assignment_id, 0) + 1
        seen_bound.append(max(by_assignment.values(), default=0))

    e = run(msg_duplicate=0.5, check=check)
    stats = e.mas.bus.stats
    assert stats["duplicated"] > 0 and stats["deduplicated"] > 0
    assert max(seen_bound) == 1
    assert compute_metrics(e)["invariant_violations"] == 0


def test_lost_messages_recovered_by_timeouts_and_leases():
    def check(e):
        w = e.world
        for r in w.reservations.values():
            if r.status != ReservationStatus.ACTIVE:
                continue
            a = w.assignments.get(r.assignment_id)
            # every held seat is either bound to a live mission or inside its lease
            assert (a is not None and a.status in ACTIVE_ASSIGNMENT) or r.pending_until >= w.tick - 1

    e = run(msg_loss=0.3, msg_latency=1, check=check)
    msgs = messages(e)
    assert e.mas.bus.stats["lost"] > 0
    assert any(m.type == "EXPIRE" for m in msgs), "an unanswered proposal should time out"
    assert any(m.type == "LOST" for m in msgs)
    assert compute_metrics(e)["people_rescued"] > 0


def test_unclaimed_lease_returns_seats():
    e = run(msg_loss=0.4, msg_latency=1, seed=5)
    lapsed = [a for a in e.audit_log if "unclaimed lease" in a.message]
    assert lapsed, "with 40% loss some granted reservations must lapse"
    for a in lapsed:
        rsv = e.world.reservations[a.refs["reservation"]]
        assert rsv.status == ReservationStatus.EXPIRED


def test_partition_blocks_new_commitments_but_missions_continue():
    e = run(until=20)
    members = ["B1", "B2", "B3", "S2"]
    active_before = {r: e.world.resources[r].assignment_id for r in members if r in e.world.resources and e.world.resources[r].assignment_id}
    e.inject("NETWORK_PARTITION", {"members": members, "duration": 30})
    start = e.world.tick
    for _ in range(30):
        e.step()
    during = [a for a in e.world.assignments.values() if start <= a.created_tick <= start + 30 and a.resource_id in members]
    assert during == [], "no new commitment may cross the partition"
    for rid, aid in active_before.items():
        a = e.world.assignments[aid]
        assert a.status != "CANCELLED" or "disabled" in a.cancel_reason, f"{rid} kept its mission"
    for _ in range(60):
        e.step()
    after = [a for a in e.world.assignments.values() if a.created_tick > start + 30 and a.resource_id in members]
    assert after, "partitioned units rejoin negotiation after the partition heals"


def test_centralized_cannot_dispatch_partitioned_units():
    e = Engine(get_preset("normal", seed=3), "centralized", record_frames=False)
    for _ in range(5):
        e.step()
    e.inject("NETWORK_PARTITION", {"members": ["B1", "B2", "G1"], "duration": 40})
    start = e.world.tick
    for _ in range(40):
        e.step()
    assert not [a for a in e.world.assignments.values() if start <= a.created_tick < start + 40 and a.resource_id in ("B1", "B2", "G1")]


def test_partition_event_validation():
    e = run(until=2)
    for bad in ({"members": []}, {"members": ["NOPE"]}, {"members": ["B1"], "duration": 0}, {"members": ["B1", "B1"]}):
        with pytest.raises(EventError):
            e.inject("NETWORK_PARTITION", bad)
    e.inject("NETWORK_PARTITION", {"members": ["B1"], "duration": 5})
    with pytest.raises(EventError):
        e.inject("NETWORK_PARTITION", {"members": ["B1"], "duration": 5})


def test_zero_latency_lossless_tracks_instant_protocol():
    """With a perfect network the message protocol should serve about as well as the
    instant protocol (it is a different mechanism, so results are close, not equal)."""
    mp = compute_metrics(run("normal", seed=1))
    e = Engine(get_preset("normal", seed=1), "decentralized", record_frames=False)
    while not e.finished:
        e.step()
    inst = compute_metrics(e)
    assert abs(mp["people_rescued"] - inst["people_rescued"]) <= 0.15 * inst["people_rescued"]
