"""Evaluation statistics, outage metrics and the published-results pipeline."""
import csv
import json
import os

from fastapi.testclient import TestClient

from app.analysis import evaluation
from app.analysis.runs import aggregate, paired_difference
from app.api import main as api
from app.metrics.metrics import compute_metrics
from app.simulation.engine import Engine
from app.simulation.scenarios import get_preset


def finish(scenario, strategy, seed=2):
    e = Engine(get_preset(scenario, seed=seed), strategy, record_frames=False)
    while not e.finished:
        e.step()
    return e


def test_aggregate_reports_robust_stats_and_ci():
    xs = [3.0, 5.0, 4.0, 10.0, 6.0, 5.0, 4.0, 7.0]
    a = aggregate(xs)
    assert a["n"] == 8 and a["median"] == 5.0 and a["q1"] <= a["median"] <= a["q3"]
    assert a["ci_low"] <= a["mean"] <= a["ci_high"]
    assert aggregate(xs) == a, "bootstrap must be reproducible"
    assert aggregate([1.0, 2.0, 3.0])["ci_low"] is None, "no CI below 5 values"
    assert aggregate([None, None])["mean"] is None
    assert aggregate([2.0] * 6)["ci_low"] == 2.0


def test_paired_difference_flags_only_consistent_differences():
    seeds = list(range(8))
    runs = [{"seed": s, "strategy": "a", "x": 10 + s} for s in seeds] + [{"seed": s, "strategy": "b", "x": 12 + s} for s in seeds]
    d = paired_difference(runs, "a", "b", "x", seeds)
    assert d["mean"] == -2.0 and d["significant"] and d["n_negative"] == 8
    noisy = [{"seed": s, "strategy": "b", "x": 10 + s + (1 if s % 2 else -1)} for s in seeds]
    d2 = paired_difference(runs[:8] + noisy, "a", "b", "x", seeds)
    assert not d2["significant"]


def test_coordinator_outage_metrics_separate_the_strategies():
    c = compute_metrics(finish("coordinator_outage", "centralized"))
    d = compute_metrics(finish("coordinator_outage", "decentralized"))
    assert c["outages"] == d["outages"] == 1
    assert c["commitments_during_outage"] == 0, "no coordinator, no central dispatch"
    assert d["commitments_during_outage"] > 0
    assert c["outage_uncovered_people_minutes"] > d["outage_uncovered_people_minutes"]


def test_partition_members_never_commit_during_partition():
    for st in ("decentralized", "message_passing", "centralized", "greedy"):
        e = finish("network_partition", st)
        (o,) = e.outages
        assert o["member_commitments"] == 0, st
        assert compute_metrics(e)["invariant_violations"] == 0


def test_service_rate_is_a_fraction():
    m = compute_metrics(finish("normal", "greedy"))
    assert 0 < m["service_rate"] <= 1


def test_suite_writes_traceable_csv_and_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, "SUITES", {"quality": {**evaluation.SUITES["quality"], "scenarios": ["normal"]}, "resilience": {**evaluation.SUITES["resilience"], "scenarios": ["coordinator_outage"]}})
    monkeypatch.setattr(evaluation, "SWEEPS", {"message_loss": {**evaluation.SWEEPS["message_loss"], "values": [0.0, 0.2]}})
    os.makedirs(tmp_path / "docs")
    rep = evaluation.run_all([1, 2], str(tmp_path), workers=1, log=lambda _m: None)
    base = tmp_path / "data" / "evaluation" / "benchmarks"
    rows = list(csv.DictReader(open(base / "quality" / "normal.csv")))
    assert len(rows) == 2 * 4 and {r["strategy"] for r in rows} == {"decentralized", "message_passing", "centralized", "greedy"}
    # a CSV row is exactly the run it came from
    again = evaluation._job((get_preset("normal").to_dict(), "greedy", 2))
    row = next(r for r in rows if r["strategy"] == "greedy" and r["seed"] == "2")
    assert float(row["mean_time_to_service"]) == again["mean_time_to_service"]
    summary = json.load(open(base / "summary.json"))
    assert "runs" not in summary["suites"]["quality"]["scenarios"]["normal"]
    assert summary["sweeps"]["message_loss"]["points"][0]["service_rate"]["mean"] is not None
    md = (tmp_path / "docs" / "benchmark_results.md").read_text()
    assert "Optimisation quality" in md and "Failure resilience" in md and rep["seeds"] == [1, 2]
    assert len(list(csv.DictReader(open(base / "sweeps" / "message_loss.csv")))) == 4


def test_evaluation_endpoint(tmp_path, monkeypatch):
    client = TestClient(api.app)
    monkeypatch.setattr(api, "EVALUATION_SUMMARY", str(tmp_path / "missing.json"))
    r = client.get("/api/evaluation")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NO_EVALUATION"
    p = tmp_path / "summary.json"
    p.write_text(json.dumps({"seeds": [1], "suites": {}, "sweeps": {}}))
    monkeypatch.setattr(api, "EVALUATION_SUMMARY", str(p))
    assert client.get("/api/evaluation").json()["seeds"] == [1]
