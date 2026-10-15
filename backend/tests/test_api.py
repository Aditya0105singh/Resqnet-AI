"""API and WebSocket contract tests."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def _create(**kw):
    r = client.post("/api/simulations", json={"scenario": "triple_failure", "strategy": "decentralized", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_health_and_scenarios():
    assert client.get("/api/health").json()["status"] == "ok"
    sc = client.get("/api/scenarios").json()
    assert {s["key"] for s in sc["scenarios"]} >= {"normal", "contradictory", "triple_failure"}
    w = client.get("/api/world").json()
    assert 30 <= len(w["nodes"]) <= 60 and 50 <= len(w["edges"]) <= 100


def test_lifecycle_events_and_errors():
    sim = _create()
    sid = sim["id"]
    assert sim["frame"]["tick"] == 0
    r = client.post(f"/api/simulations/{sid}/step", json={"ticks": 5}).json()
    assert r["tick"] == 5
    bad = client.post(f"/api/simulations/{sid}/events", json={"type": "CLOSE_EDGE", "params": {"edge_id": "XX"}})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "EVENT_REJECTED"
    ok = client.post(f"/api/simulations/{sid}/events", json={"type": "CLOSE_EDGE", "params": {"edge_id": "BR1", "reason": "test"}})
    assert ok.status_code == 200 and ok.json()["event"]["effects"]
    for path in ("agents", "assignments", "negotiations", "decisions", "metrics", "audit", "safety", "frames"):
        assert client.get(f"/api/simulations/{sid}/{path}").status_code == 200, path
    rounds = client.get(f"/api/simulations/{sid}/negotiations").json()["rounds"]
    detail = client.get(f"/api/simulations/{sid}/negotiations/{rounds[-1]['id']}").json()
    assert detail["messages"]
    assert client.get(f"/api/simulations/{sid}/replay/verify").json()["identical"]
    fork = client.post(f"/api/simulations/{sid}/fork", json={"tick": 3, "modifications": {"extra_boats": 1}, "horizon": 40}).json()
    assert fork["applied"] and fork["frames"]["alternative"]
    rep = client.get(f"/api/reports/{sid}").json()
    assert rep["strategy_comparison"] and rep["limitations"]
    pdf = client.get(f"/api/reports/{sid}?format=pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert client.post(f"/api/simulations/{sid}/reset").json()["tick"] == 0
    assert client.get("/api/simulations/doesnotexist").status_code == 404


def test_invalid_config_rejected():
    r = client.post("/api/simulations", json={"scenario": "normal", "overrides": {"boats": 99}})
    assert r.status_code == 422
    r = client.post("/api/simulations", json={"scenario": "normal", "overrides": {"hack": 1}})
    assert r.status_code == 400


def test_websocket_hello_and_resync():
    sid = _create()["id"]
    with client.websocket_connect(f"/ws/simulations/{sid}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["frame"]["tick"] == 0 and "state_version" in hello
        client.post(f"/api/simulations/{sid}/step", json={"ticks": 2})
        msg = ws.receive_json()
        assert msg["type"] == "frame" and msg["frame"]["tick"] == 2 and msg["seq"] >= 1
        ws.send_json({"type": "resync"})
        assert ws.receive_json()["type"] == "resync"


def test_benchmark_job():
    with TestClient(app) as c:  # keep one event loop alive for the background job
        _bench(c)


def _bench(client):
    job = client.post("/api/benchmarks", json={"scenario": "normal", "seeds": [1], "strategies": ["decentralized", "centralized"], "overrides": {"duration": 40}}).json()
    for _ in range(100):
        j = client.get(f"/api/benchmarks/{job['id']}").json()
        if j["status"] != "running":
            break
        time.sleep(0.1)
    assert j["status"] == "done" and len(j["result"]["runs"]) == 2
