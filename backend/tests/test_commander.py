"""Mission Commander: grounded answers, checked citations, no authority, LLM loop (mocked)."""
import json

import pytest
from fastapi.testclient import TestClient

from app.api import main as api
from app.intelligence.commander import ask, check_citations, norm_ids
from app.simulation.engine import Engine
from app.simulation.scenarios import get_preset


@pytest.fixture(scope="module")
def snap():
    e = Engine(get_preset("triple_failure", seed=3), "decentralized")
    while e.world.tick < 40:
        e.step()
    return e.read_snapshot()


def cited(r):
    return {c["id"] for c in r["citations"]}


def test_reassignment_question_is_answered_from_records(snap):
    r = ask("Why was I-004 reassigned?", snap)
    assert r["engine"] == "rules" and not r["warnings"]
    assert "**not** reassigned" in r["answer"], "the record shows a reroute, not a reassignment: say so"
    assert {"I-004", "EV-0001", "AU-00050"} <= cited(r)
    assert all(c["exists"] and c["from_tools"] for c in r["citations"])


def test_shelter_capacity_question(snap):
    r = ask("Which shelters can accept 5 more people?", snap)
    free = {s.id: s.effective_free(snap.world) for s in snap.world.shelters.values()}
    headline = r["answer"].split("\n")[0]
    for sid, f in free.items():
        assert f"[{sid}]" in r["answer"]
        assert (f >= 5) == (sid in headline), "the headline lists exactly the shelters with 5+ free seats"


def test_what_if_runs_a_real_counterfactual(snap):
    r = ask("What happens if B2 becomes unavailable?", snap)
    assert r["tool_calls"][0]["tool"] == "what_if" and r["tool_calls"][0]["input"]["disable"] == ["B2"]
    assert "modelled outcome" in r["answer"] and not r["warnings"]
    assert snap.world.resources["B2"].status != "DISABLED", "the snapshot itself is untouched"


def test_neighbourhood_and_unit_and_status(snap):
    assert "Longest waits first" in ask("Which neighbourhoods have the longest waiting times?", snap)["answer"]
    r = ask("Where is G1?", snap)
    assert "[G1]" in r["answer"] and not r["warnings"]
    assert "rescued" in ask("status", snap)["answer"]


def test_faster_route_question_explains_the_decision(snap):
    r = ask("Why was the faster route rejected for I-004?", snap)
    assert any(c["kind"] == "decision" for c in r["citations"]) and "What would change it" in r["answer"]


def test_action_requests_only_create_proposals(snap):
    r = ask("Send B4 to I-010", snap)
    assert "**not** sent" in r["answer"] and r["proposals"] == [{"action": "MANUAL_ASSIGN", "params": {"resource_id": "B4", "incident_id": "I-010"}, "rationale": r["proposals"][0]["rationale"]}]
    assert not snap.proposals, "nothing is queued on the snapshot"


def test_unknown_question_gets_help_without_citations(snap):
    r = ask("what is the weather like", snap)
    assert "I answer from this run's records" in r["answer"] and not r["citations"]


def test_citation_checker_flags_invented_and_ungrounded_ids(snap):
    cites, warns = check_citations("See [D-99999] and [I-004] and bare I-005.", snap, from_tools={"I-004"})
    assert {c["id"] for c in cites} == {"D-99999", "I-004"}
    assert any("D-99999" in w and "does not exist" in w for w in warns)
    cites, warns = check_citations("[I-005]", snap, from_tools=set())
    assert any("no tool returned" in w for w in warns)


def test_id_normalisation():
    ids = norm_ids("why was incident 4 reassigned, and send boat b2 to i12; see d-12 and A-007")
    assert ids["incidents"] == ["I-004", "I-012"] and ids["units"] == ["B2"] and ids["decisions"] == ["D-00012"] and ids["assignments"] == ["A-007"]


# ------------------------------------------------------------------ API


def test_api_queues_ai_proposal_that_ai_cannot_approve():
    client = TestClient(api.app)
    sid = client.post("/api/simulations", json={"scenario": "coordinator_outage", "strategy": "centralized", "seed": 2}).json()["id"]
    client.post(f"/api/simulations/{sid}/step", json={"ticks": 22})
    frame = client.get(f"/api/simulations/{sid}").json()["frame"]
    inc = next(i["id"] for i in frame["incidents"] if i["unassigned"] > 0)
    idle = next(r["id"] for r in frame["resources"] if r["status"] == "IDLE")
    r = client.post(f"/api/simulations/{sid}/ask", json={"question": f"Send {idle} to {inc}"}).json()
    assert len(r["queued_proposals"]) == 1
    pid = r["queued_proposals"][0]
    p = next(p for p in client.get(f"/api/simulations/{sid}/proposals").json()["proposals"] if p["id"] == pid)
    assert p["source"] == "ai-commander" and p["status"] == "PENDING"
    denied = client.post(f"/api/simulations/{sid}/events", json={"type": "APPROVE_PROPOSAL", "params": {"proposal_id": pid, "by": "ai-commander"}})
    assert denied.status_code == 422


# ------------------------------------------------------------------ Claude loop (mocked transport)


def _client(script, seen):
    import anthropic
    import httpx2

    def handler(request):
        seen.append(json.loads(request.content))
        step = script[len(seen) - 1]
        return httpx2.Response(200, json={"id": f"msg_{len(seen)}", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": step["content"],
                                          "stop_reason": step["stop"], "stop_sequence": None, "usage": {"input_tokens": 5, "output_tokens": 5}})

    return anthropic.Anthropic(api_key="test-key", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)), max_retries=0)


def test_llm_loop_uses_tools_and_cannot_act(snap):
    seen = []
    script = [
        {"stop": "tool_use", "content": [{"type": "tool_use", "id": "tu_1", "name": "get_incident", "input": {"incident_id": "I-004"}},
                                          {"type": "tool_use", "id": "tu_2", "name": "propose_action", "input": {"action": "MANUAL_ASSIGN", "params": {"resource_id": "B4", "incident_id": "I-004", "assignment_id": None, "decision": None}, "rationale": "test"}}]},
        {"stop": "end_turn", "content": [{"type": "text", "text": "[I-004] was rerouted, not reassigned [AU-00050]. I queued a proposal for B4; a dispatcher must approve it. Also see [D-99999]."}]},
    ]
    r = ask("Why was I-004 reassigned?", snap, client=_client(script, seen))
    assert r["engine"] == "llm:claude-opus-5-5"
    first = seen[0]
    assert first["model"] == "claude-opus-5-5" and first["fallbacks"] == "default"
    assert all(t["strict"] and t["input_schema"]["additionalProperties"] is False for t in first["tools"])
    assert "tool_choice" not in first, "forced tool choice is not allowed on this model"
    second = seen[1]["messages"]
    assert second[1]["role"] == "assistant" and second[2]["content"][0]["type"] == "tool_result" and len(second[2]["content"]) == 2
    assert [c["tool"] for c in r["tool_calls"]] == ["get_incident", "propose_action"]
    assert len(r["proposals"]) == 1 and not snap.proposals
    assert any("D-99999" in w for w in r["warnings"]), "invented citation is surfaced"


def test_llm_failure_falls_back_to_router(snap):
    seen = []
    r = ask("Where is G1?", snap, client=_client([{"stop": "refusal", "content": []}], seen))
    assert r["engine"].startswith("rules (llm unavailable") and "[G1]" in r["answer"]
