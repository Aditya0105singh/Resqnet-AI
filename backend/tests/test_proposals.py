"""Human approval queue: proposals preview without side effects, approval re-validates."""
import pytest

from app.analysis.runs import verify_replay
from app.simulation.engine import PROPOSAL_TTL, Engine, EventError
from app.simulation.scenarios import get_preset
from app.simulation.serialize import state_hash


def outage_engine(tick=22, seed=2):
    """Coordinator down: units sit idle with open demand, the natural case for proposals."""
    e = Engine(get_preset("coordinator_outage", seed=seed), "centralized")
    while e.world.tick < tick:
        e.step()
    return e


def propose_auto(e):
    for inc in sorted(e.world.incidents.values(), key=lambda i: i.id):
        try:
            e.inject("PROPOSE_ACTION", {"action": "MANUAL_ASSIGN", "params": {"incident_id": inc.id, "resource_id": "auto"}, "source": "recommender"})
            return list(e.proposals.values())[-1]
        except EventError:
            continue
    pytest.skip("no feasible proposal in this state")


def test_proposal_previews_without_changing_the_world():
    e = outage_engine()
    before, n_assign, n_frames = state_hash(e), len(e.world.assignments), len(e.frames)
    pr = propose_auto(e)
    assert pr["status"] == "PENDING" and pr["preview"]["ok"]
    assert pr["preview"]["plan"]["resource"] == pr["params"]["resource_id"]
    assert any(c["name"].startswith("S1") for c in pr["preview"]["checks"]), "preview carries the shield checks"
    assert "lowest cost" in pr["rationale"]
    assert state_hash(e) == before and len(e.world.assignments) == n_assign
    assert len(e.frames) >= n_frames, "dry run must not drop history"


def test_approve_commits_exactly_once():
    e = outage_engine()
    pr = propose_auto(e)
    e.inject("APPROVE_PROPOSAL", {"proposal_id": pr["id"]})
    assert pr["status"] == "APPROVED" and pr["decided_by"] == "dispatcher"
    a = [a for a in e.world.assignments.values() if a.resource_id == pr["params"]["resource_id"] and a.status == "COMMITTED"]
    assert len(a) == 1 and a[0].incident_id == pr["params"]["incident_id"]
    with pytest.raises(EventError):
        e.inject("APPROVE_PROPOSAL", {"proposal_id": pr["id"]})


def test_reject_is_final():
    e = outage_engine()
    pr = propose_auto(e)
    e.inject("REJECT_PROPOSAL", {"proposal_id": pr["id"], "reason": "unit needed elsewhere"})
    assert pr["status"] == "REJECTED" and pr["outcome"] == "unit needed elsewhere"
    with pytest.raises(EventError):
        e.inject("APPROVE_PROPOSAL", {"proposal_id": pr["id"]})


def test_approval_revalidates_against_current_state():
    e = outage_engine()
    pr = propose_auto(e)
    e.inject("RESOURCE_FAILURE", {"resource_id": pr["params"]["resource_id"], "reason": "engine failure"})
    n = len(e.world.assignments)
    with pytest.raises(EventError, match="no longer valid"):
        e.inject("APPROVE_PROPOSAL", {"proposal_id": pr["id"]})
    assert len(e.world.assignments) == n
    assert pr["status"] == "PENDING" and not pr["preview"]["ok"]


def test_ai_can_propose_but_not_approve():
    e = outage_engine()
    pr = propose_auto(e)
    with pytest.raises(EventError, match="cannot approve"):
        e.inject("APPROVE_PROPOSAL", {"proposal_id": pr["id"], "by": "ai-commander"})
    assert pr["status"] == "PENDING"


def test_pending_proposals_expire_and_refresh():
    e = outage_engine()
    pr = propose_auto(e)
    e.step()
    assert pr["preview"]["tick"] == e.world.tick, "preview refreshed against the new tick"
    for _ in range(PROPOSAL_TTL):
        e.step()
    assert pr["status"] == "EXPIRED"


def test_invalid_proposals():
    e = outage_engine()
    with pytest.raises(EventError):
        e.inject("PROPOSE_ACTION", {"action": "CLOSE_EDGE", "params": {"edge_id": "BR1"}})
    with pytest.raises(EventError):
        e.inject("PROPOSE_ACTION", {"action": "MANUAL_ASSIGN", "params": {"incident_id": "I-999", "resource_id": "auto"}})
    e.inject("PROPOSE_ACTION", {"action": "CANCEL_ASSIGNMENT", "params": {"assignment_id": "A-999"}, "source": "ai-commander", "rationale": "test"})
    pr = list(e.proposals.values())[-1]
    assert not pr["preview"]["ok"] and "would be rejected" in pr["preview"]["summary"]
    with pytest.raises(EventError):
        e.inject("APPROVE_PROPOSAL", {"proposal_id": pr["id"]})


def test_queue_is_part_of_the_replayable_event_log():
    e = outage_engine()
    a = propose_auto(e)
    e.step()
    b = propose_auto(e)
    e.inject("APPROVE_PROPOSAL", {"proposal_id": a["id"]})
    e.inject("REJECT_PROPOSAL", {"proposal_id": b["id"]})
    for _ in range(10):
        e.step()
    assert verify_replay(e)["identical"]


def test_conflicting_proposal_preview_updates_after_approval():
    e = outage_engine()
    a = propose_auto(e)
    others = [i for i in e.world.incidents.values() if i.id != a["params"]["incident_id"] and i.status not in ("RESCUED", "FALSE_ALARM")]
    e.inject("PROPOSE_ACTION", {"action": "MANUAL_ASSIGN", "params": {"incident_id": others[0].id, "resource_id": a["params"]["resource_id"]}})
    b = list(e.proposals.values())[-1]
    e.inject("APPROVE_PROPOSAL", {"proposal_id": a["id"]})
    assert not b["preview"]["ok"], "same unit is now busy: the other proposal must show as failing immediately"


def test_frame_lists_proposals():
    e = outage_engine()
    pr = propose_auto(e)
    e.step()
    assert any(p["id"] == pr["id"] for p in e.last_frame()["proposals"])
