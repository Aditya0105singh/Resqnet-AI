"""Report fusion: forwarded copies are not independent witnesses; credible conflicts abstain."""
import pytest

from app.analysis.runs import verify_replay
from app.metrics.metrics import compute_metrics
from app.negotiation.common import DISPUTE_REVIEW, DISPUTE_REVIEW_URGENT, is_eligible
from app.simulation import reports as fusion
from app.simulation.engine import Engine, EventError
from app.simulation.scenarios import get_preset
from app.simulation.state import IncidentReport, IncidentStatus


def quiet_engine(**ov):
    """An engine whose generated reports are all in the future, so tests control the evidence."""
    e = Engine(get_preset("normal", seed=4, initial_incidents=0, arrival_incidents=0, **ov), "decentralized", record_frames=False)
    return e


_n = [0]


def report(e, node="N33", source="resident", claim="PRESENT", fingerprint="", derived_from="", people=3, urgency=3):
    _n[0] += 1
    r = IncidentReport(f"T-{_n[0]:04d}", e.world.tick, source, {"resident": 0.6, "sensor": 0.75, "responder": 0.9}[source], node, people, urgency, claim, 0.0, fingerprint=fingerprint, derived_from=derived_from)
    return fusion.ingest(e, r)


def test_forwarded_copies_count_once():
    e = quiet_engine()
    inc = report(e, fingerprint="FP-x")
    single = inc.confidence
    for _ in range(5):
        report(e, fingerprint="FP-x", derived_from="ignored")
    assert inc.confidence == single == 0.6
    assert inc.evidence["present_reports"] == 6 and inc.evidence["present_sources"] == 1 and inc.evidence["forwarded_copies"] == 5
    assert inc.status == IncidentStatus.SUSPECTED


def test_independent_witnesses_still_corroborate():
    e = quiet_engine()
    inc = report(e)
    report(e, fingerprint="FP-a")
    report(e, fingerprint="FP-b")
    assert inc.evidence["present_sources"] == 3
    assert inc.confidence == pytest.approx(1 - 0.4**3, abs=1e-3)
    assert inc.status == IncidentStatus.VERIFIED


def test_fusion_reads_only_the_observable_fingerprint():
    """The hidden derived_from link must not influence fusion: a forward that lost its
    fingerprint (e.g. paraphrased) is, as far as the system can tell, a new witness."""
    e = quiet_engine()
    inc = report(e, fingerprint="FP-y")
    report(e, derived_from="T-hidden")  # no fingerprint
    assert inc.evidence["present_sources"] == 2


def test_ablation_without_dedup_counts_every_copy():
    e = quiet_engine(fusion_dedup=False)
    inc = report(e, fingerprint="FP-z")
    for _ in range(4):
        report(e, fingerprint="FP-z")
    assert inc.confidence > 0.98 and inc.status == IncidentStatus.VERIFIED


def test_credible_conflict_abstains_then_verifies():
    e = quiet_engine()
    inc = report(e, urgency=3)
    report(e, fingerprint="FP-2")  # two independent residents: cp = 0.84
    report(e, source="responder", claim="NO_VICTIMS")  # cn = 0.9: credible, but not > cp + 0.2
    assert inc.status == IncidentStatus.DISPUTED and inc.disputed_since == e.world.tick
    ok, why = is_eligible(e.world, inc)
    assert not ok and "awaiting dispatcher review" in why
    start = e.world.tick
    while e.world.tick < start + DISPUTE_REVIEW - 1:
        e.step()
        assert not any(a.incident_id == inc.id for a in e.world.assignments.values()), "no automatic dispatch while disputed"
    e.step()
    ok, why = is_eligible(e.world, inc)
    assert ok and why.startswith("E5")


def test_urgent_disputes_get_a_shorter_review_window():
    e = quiet_engine()
    inc = report(e, urgency=5)
    report(e, fingerprint="FP-3", urgency=5)
    report(e, source="responder", claim="NO_VICTIMS")
    assert inc.status == IncidentStatus.DISPUTED
    for _ in range(DISPUTE_REVIEW_URGENT):
        e.step()
    assert is_eligible(e.world, inc)[0]


def test_overwhelming_negative_evidence_is_still_a_false_alarm():
    e = quiet_engine()
    inc = report(e)
    report(e, source="responder", claim="NO_VICTIMS")
    assert inc.status == IncidentStatus.FALSE_ALARM and inc.disputed_since is None


@pytest.mark.parametrize("decision,status", [("confirm", IncidentStatus.VERIFIED), ("dismiss", IncidentStatus.FALSE_ALARM)])
def test_dispatcher_resolves_dispute(decision, status):
    e = quiet_engine()
    inc = report(e)
    report(e, fingerprint="FP-4")
    report(e, source="responder", claim="NO_VICTIMS")
    e.inject("RESOLVE_DISPUTE", {"incident_id": inc.id, "decision": decision})
    assert inc.status in (status, IncidentStatus.ASSIGNED) and inc.disputed_since is None
    if decision == "confirm":
        assert inc.confidence >= 0.8 and is_eligible(e.world, inc)[0]


def test_dispatcher_can_order_verification_now():
    e = quiet_engine()
    inc = report(e)
    report(e, fingerprint="FP-5")
    report(e, source="responder", claim="NO_VICTIMS")
    e.inject("RESOLVE_DISPUTE", {"incident_id": inc.id, "decision": "verify"})
    assert is_eligible(e.world, inc)[0]
    for _ in range(2):  # decentralised agents hear the change after comm_delay (1 tick)
        e.step()
    assert any(a.incident_id == inc.id for a in e.world.assignments.values()), "verification visit dispatched well before the review window"


def test_resolve_dispute_validation():
    e = quiet_engine()
    inc = report(e)
    with pytest.raises(EventError):
        e.inject("RESOLVE_DISPUTE", {"incident_id": inc.id, "decision": "maybe"})
    with pytest.raises(EventError):
        e.inject("RESOLVE_DISPUTE", {"incident_id": "I-999", "decision": "confirm"})


def test_viral_scenario_generates_forwards_and_replays():
    e = Engine(get_preset("viral_sos", seed=3), "decentralized")
    forwards = [r for r in e.world.pending_reports if r.derived_from]
    assert forwards and all(r.fingerprint for r in forwards)
    while e.world.tick < 50:
        e.step()
    d = next((i for i in e.world.incidents.values() if i.status == IncidentStatus.DISPUTED), None)
    if d:
        e.inject("RESOLVE_DISPUTE", {"incident_id": d.id, "decision": "verify"})
    for _ in range(20):
        e.step()
    assert verify_replay(e)["identical"]
    assert compute_metrics(e)["invariant_violations"] == 0


def test_dedup_reduces_wasted_trips_to_rumours():
    """Across seeds, counting forwards once must not send more units to non-existent victims."""
    on = off = 0
    for seed in range(1, 6):
        for dedup in (True, False):
            e = Engine(get_preset("viral_sos", seed=seed, fusion_dedup=dedup), "centralized", record_frames=False)
            while not e.finished:
                e.step()
            if dedup:
                on += e.counters["false_alarm_visits"]
            else:
                off += e.counters["false_alarm_visits"]
    assert on <= off
