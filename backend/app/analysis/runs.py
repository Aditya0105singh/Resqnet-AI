"""Replay, counterfactual branching, seeded benchmarks and adversarial search.

Every result here comes from actually running the simulation engine; nothing is
estimated or hard-coded.
"""
from __future__ import annotations

import copy
import random
import statistics
import time
from typing import Any, Callable, Optional

import numpy as np

from ..metrics.metrics import SUMMARY_KEYS, compute_metrics
from ..simulation.engine import Engine, EventError
from ..simulation.scenarios import POLICIES, ScenarioConfig


# ---------------------------------------------------------------- replay

def rebuild(cfg: ScenarioConfig, strategy: str, injected: list[dict[str, Any]], until: int, record_frames: bool = False) -> Engine:
    """Re-run from scratch, re-applying the logged user events at the same (tick, seq)."""
    eng = Engine(copy.deepcopy(cfg), strategy, record_frames=record_frames)
    by_tick: dict[int, list[dict]] = {}
    for ev in sorted(injected, key=lambda e: (e["tick"], e["seq"])):
        by_tick.setdefault(ev["tick"], []).append(ev)

    def apply(t: int) -> None:
        for ev in by_tick.get(t, []):
            try:
                eng.inject(ev["type"], dict(ev["params"]), ev.get("source", "user"))
            except EventError:
                pass

    apply(0)
    while not eng.finished and eng.world.tick < until:
        eng.step()
        apply(eng.world.tick)
    return eng


def verify_replay(engine: Engine) -> dict[str, Any]:
    t0 = time.perf_counter()
    rep = rebuild(engine.base_cfg, engine.strategy, engine.injected, engine.world.tick)
    mismatches = [t for t, h in engine.hashes.items() if rep.hashes.get(t) != h]
    return {
        "ticks_compared": len(engine.hashes),
        "mismatches": mismatches[:20],
        "identical": not mismatches,
        "final_hash": engine.hashes.get(engine.world.tick),
        "replay_final_hash": rep.hashes.get(rep.world.tick),
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


# ---------------------------------------------------------------- counterfactual

def compact_frame(f: dict[str, Any]) -> dict[str, Any]:
    return {
        "tick": f["tick"],
        "resources": [{k: r[k] for k in ("id", "kind", "x", "y", "status", "load", "incident_id", "route")} for r in f["resources"]],
        "incidents": [{k: i[k] for k in ("id", "x", "y", "status", "urgency", "people", "unassigned")} for i in f["incidents"]],
        "shelters": [{k: s[k] for k in ("id", "x", "y", "capacity", "occupancy", "reserved")} for s in f["shelters"]],
        "edges": {k: v[:3] for k, v in f["edges"].items()},
        "depths": f["depths"],
        "metrics": {k: f["metrics"][k] for k in ("people_rescued", "unmet_people", "deadline_misses", "mean_time_to_service")},
    }


def apply_modifications(eng: Engine, mods: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    for _ in range(int(mods.get("extra_boats") or 0)):
        notes += eng._apply_event("ADD_RESOURCE", {"kind": "boat", "node": mods.get("boat_node")} if mods.get("boat_node") else {"kind": "boat"}, "counterfactual").effects
    for _ in range(int(mods.get("extra_ground") or 0)):
        notes += eng._apply_event("ADD_RESOURCE", {"kind": "ground", "node": mods.get("ground_node")} if mods.get("ground_node") else {"kind": "ground"}, "counterfactual").effects
    for eid, state in (mods.get("edges") or {}).items():
        notes += eng._apply_event("OPEN_EDGE" if state == "open" else "CLOSE_EDGE", {"edge_id": eid, "reason": "counterfactual"}, "counterfactual").effects
    for sid, delta in (mods.get("shelter_delta") or {}).items():
        sh = eng.world.shelters.get(sid)
        if sh and int(delta):
            notes += eng._apply_event("SHELTER_CAPACITY", {"shelter_id": sid, "capacity": max(0, sh.capacity + int(delta)), "reason": "counterfactual"}, "counterfactual").effects
    if mods.get("policy") in POLICIES:
        eng.cfg.policy = mods["policy"]
        eng.cfg.weights = dict(POLICIES[mods["policy"]])
        notes.append(f"priority policy → {mods['policy']}")
    if mods.get("comm_delay") is not None and mods.get("comm_delay") != "":
        eng.cfg.comm_delay = int(mods["comm_delay"])
        notes.append(f"communication delay → {eng.cfg.comm_delay} ticks")
    if mods.get("strategy") in ("decentralized", "message_passing", "centralized", "greedy"):
        eng.strategy = mods["strategy"]
        eng.world.strategy = mods["strategy"]
        notes.append(f"strategy → {mods['strategy']}")
    for rid in mods.get("disable") or []:
        try:
            notes += eng._apply_event("RESOURCE_FAILURE", {"resource_id": rid, "reason": "counterfactual removal"}, "counterfactual").effects
        except EventError:
            pass
    return notes


def _assignment_seq(eng: Engine) -> dict[str, list[tuple[int, str]]]:
    seq: dict[str, list[tuple[int, str]]] = {}
    for a in sorted(eng.world.assignments.values(), key=lambda a: (a.created_tick, a.id)):
        seq.setdefault(a.incident_id, []).append((a.created_tick, a.resource_id))
    return seq


def counterfactual(cfg: ScenarioConfig, strategy: str, injected: list[dict[str, Any]], fork_tick: int, mods: dict[str, Any], horizon: Optional[int] = None) -> dict[str, Any]:
    t0 = time.perf_counter()
    base = rebuild(cfg, strategy, [e for e in injected if e["tick"] <= fork_tick], fork_tick)
    branch = base.fork()
    notes = apply_modifications(branch, mods)
    # both branches get the same replanning round at the fork point, so the only
    # difference between them is the modification itself
    for eng in (base, branch):
        eng._microstep("counterfactual fork point")
        eng._snapshot()
    end = min(cfg.duration, horizon or cfg.duration)
    future = sorted([e for e in injected if e["tick"] > fork_tick], key=lambda e: (e["tick"], e["seq"]))
    frames: dict[str, list] = {"baseline": [], "alternative": []}
    for eng, key in ((base, "baseline"), (branch, "alternative")):
        eng.record_frames = False
        frames[key].append(compact_frame(eng.last_frame()))
        while not eng.finished and eng.world.tick < end:
            eng.step()
            for ev in [e for e in future if e["tick"] == eng.world.tick]:
                try:
                    eng.inject(ev["type"], dict(ev["params"]), ev.get("source", "user"))
                except EventError:
                    pass
            if eng.world.tick % 2 == 0 or eng.finished:
                frames[key].append(compact_frame(eng.last_frame()))
    mb, ma = compute_metrics(base), compute_metrics(branch)
    sb, sa = _assignment_seq(base), _assignment_seq(branch)
    diverged = []
    for iid in sorted(set(sb) | set(sa)):
        if sb.get(iid) != sa.get(iid):
            diverged.append({"incident": iid, "baseline": sb.get(iid, []), "alternative": sa.get(iid, [])})
    diverged.sort(key=lambda d: (min([t for t, _ in d["baseline"] + d["alternative"]] or [10**6]), d["incident"]))
    keys = SUMMARY_KEYS + ["fairness_by_neighbourhood", "served_incidents"]
    return {
        "fork_tick": fork_tick,
        "end_tick": base.world.tick,
        "modifications": mods,
        "applied": notes,
        "baseline": {k: mb[k] for k in keys},
        "alternative": {k: ma[k] for k in keys},
        "diverged_decisions": diverged[:25],
        "diverged_count": len(diverged),
        "frames": frames,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


# ---------------------------------------------------------------- benchmarks

def run_one(cfg: ScenarioConfig, strategy: str) -> dict[str, Any]:
    eng = Engine(copy.deepcopy(cfg), strategy, record_frames=False)
    t0 = time.perf_counter()
    while not eng.finished:
        eng.step()
    m = compute_metrics(eng)
    out: dict[str, Any] = {k: m[k] for k in SUMMARY_KEYS}
    out["wall_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    out["fairness_by_neighbourhood"] = m["fairness_by_neighbourhood"]
    return out


BOOTSTRAP_RESAMPLES = 2000
MIN_N_FOR_CI = 5  # below this a bootstrap CI is too unstable to report
PAIRED_KEYS = ("mean_time_to_service", "service_rate", "people_rescued", "deadline_misses", "unmet_people", "fairness_jain", "idle_with_demand_ticks", "negotiation_messages", "mean_recovery_time", "outage_uncovered_people_minutes")
PAIRS = (("decentralized", "centralized"), ("message_passing", "centralized"), ("message_passing", "decentralized"), ("decentralized", "greedy"))


def bootstrap_ci(xs: list[float], level: float = 0.95) -> tuple[Optional[float], Optional[float]]:
    """Percentile bootstrap CI of the mean. Seeded from the data, so it is reproducible.
    With fewer than MIN_N_FOR_CI values a CI is not meaningful and (None, None) is returned."""
    if len(xs) < MIN_N_FOR_CI:
        return None, None
    arr = np.asarray(xs, dtype=float)
    if np.all(arr == arr[0]):
        return float(arr[0]), float(arr[0])
    rng = np.random.default_rng(len(xs) * 7919 + int(abs(arr.sum()) * 1000) % 100_003)
    means = rng.choice(arr, size=(BOOTSTRAP_RESAMPLES, len(arr)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(lo), float(hi)


def aggregate(values: list[Optional[float]]) -> dict[str, Optional[float]]:
    """Mean, sd, median, IQR and a 95% bootstrap CI of the mean. `n` counts the values
    that exist (e.g. recovery time is missing for runs that never recovered)."""
    xs = [float(v) for v in values if v is not None]
    if not xs:
        return {"mean": None, "std": None, "median": None, "q1": None, "q3": None, "ci_low": None, "ci_high": None, "min": None, "max": None, "n": 0}
    q1, med, q3 = (float(x) for x in np.quantile(xs, [0.25, 0.5, 0.75]))
    lo, hi = bootstrap_ci(xs)
    r = lambda v: None if v is None else round(v, 3)  # noqa: E731
    return {
        "mean": r(statistics.fmean(xs)),
        "std": r(statistics.stdev(xs)) if len(xs) > 1 else 0.0,
        "median": r(med),
        "q1": r(q1),
        "q3": r(q3),
        "ci_low": r(lo),
        "ci_high": r(hi),
        "min": r(min(xs)),
        "max": r(max(xs)),
        "n": len(xs),
    }


def paired_difference(runs: list[dict[str, Any]], a: str, b: str, key: str, seeds: list[int]) -> dict[str, Any]:
    """Per-seed difference a − b on the same seed and event schedule. `significant` is true
    when the 95% CI of the mean difference excludes zero (needs n ≥ MIN_N_FOR_CI)."""
    diffs = []
    for seed in seeds:
        ra = next((r for r in runs if r["seed"] == seed and r["strategy"] == a), None)
        rb = next((r for r in runs if r["seed"] == seed and r["strategy"] == b), None)
        if ra and rb and ra.get(key) is not None and rb.get(key) is not None:
            diffs.append(ra[key] - rb[key])
    agg = aggregate(diffs)
    agg["significant"] = agg["ci_low"] is not None and (agg["ci_low"] > 0 or agg["ci_high"] < 0)
    agg["n_negative"] = sum(1 for d in diffs if d < 0)  # seeds where a < b
    agg["n_positive"] = sum(1 for d in diffs if d > 0)  # seeds where a > b
    return agg


def benchmark(cfg: ScenarioConfig, strategies: list[str], seeds: list[int], progress: Optional[Callable[[float], None]] = None) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    total = len(strategies) * len(seeds)
    done = 0
    for seed in seeds:
        for strat in strategies:
            c = copy.deepcopy(cfg)
            c.seed = seed
            r = run_one(c, strat)
            r.update({"seed": seed, "strategy": strat})
            runs.append(r)
            done += 1
            if progress:
                progress(done / total)
    return summarise(cfg.key, strategies, seeds, runs)


def summarise(scenario: str, strategies: list[str], seeds: list[int], runs: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {s: {k: aggregate([r.get(k) for r in runs if r["strategy"] == s]) for k in SUMMARY_KEYS + ["wall_ms"]} for s in strategies}
    pairs: dict[str, dict[str, Any]] = {}
    for a, b in PAIRS:
        if a in strategies and b in strategies:
            pairs[f"{a}-{b}"] = {k: paired_difference(runs, a, b, k, seeds) for k in PAIRED_KEYS}
    legacy = pairs.get("decentralized-centralized", {})
    return {
        "scenario": scenario,
        "seeds": seeds,
        "strategies": strategies,
        "runs": runs,
        "summary": summary,
        "paired": pairs,
        "paired_decentralized_minus_centralized": {k: v for k, v in legacy.items() if k in ("mean_time_to_service", "deadline_misses", "unmet_people", "fairness_jain", "idle_with_demand_ticks", "negotiation_messages")},
    }


# ---------------------------------------------------------------- adversarial

FAILURE_POOL: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "bridge": [("CLOSE_EDGE", {"edge_id": b, "reason": "adversarial: bridge failure"}) for b in ("BR1", "BR2", "BR3")],
    "boat": [("RESOURCE_FAILURE", {"resource_id": f"B{i}", "reason": "adversarial: engine failure"}) for i in range(1, 6)],
    "ground": [("RESOURCE_FAILURE", {"resource_id": f"G{i}", "reason": "adversarial: vehicle failure"}) for i in range(1, 5)],
    "shelter": [("SHELTER_CAPACITY", {"shelter_id": s, "capacity": "occupancy", "reason": "adversarial: overflow"}) for s in ("S1", "S2", "S3")],
    "surge": [("FLOOD_SURGE", {"delta": 0.6})],
    "blackout": [("COMM_BLACKOUT", {"resource_id": f"B{i}", "duration": 25}) for i in range(1, 6)],
}


def adversarial(cfg: ScenarioConfig, strategy: str, n_failures: int, categories: list[str], trials: int, seed: int, progress: Optional[Callable[[float], None]] = None) -> dict[str, Any]:
    rng = random.Random(seed)
    pool = [(cat, t, p) for cat in categories for t, p in FAILURE_POOL.get(cat, [])]
    if not pool:
        raise ValueError("no failure categories selected")
    baseline = run_one(cfg, strategy)
    results = []
    seen: set = set()
    for k in range(trials):
        picks = rng.sample(pool, min(n_failures, len(pool)))
        sched = sorted(
            ({"tick": rng.randint(10, max(11, min(70, cfg.duration - 10))), "type": t, "params": dict(p), "category": cat} for cat, t, p in picks),
            key=lambda e: (e["tick"], e["type"]),
        )
        key = tuple((e["tick"], e["type"], tuple(sorted(e["params"].items()))) for e in sched)
        if key in seen:
            continue
        seen.add(key)
        c = copy.deepcopy(cfg)
        c.schedule = list(cfg.schedule) + [{"tick": e["tick"], "type": e["type"], "params": e["params"]} for e in sched]
        m = run_one(c, strategy)
        score = (m["unmet_people"] or 0) * 3 + (m["deadline_misses"] or 0) * 5 + (m["mean_time_to_service"] or 0) * 0.2
        results.append({"trial": k + 1, "failures": sched, "metrics": m, "score": round(score, 2)})
        if progress:
            progress((k + 1) / trials)
    results.sort(key=lambda r: (-r["score"], r["trial"]))
    return {
        "scenario": cfg.key,
        "strategy": strategy,
        "trials_run": len(results),
        "pool_size": len(pool),
        "search_space_note": f"Seeded random sample of {len(results)} combinations ({n_failures} failures each) drawn from a pool of {len(pool)} single failures, injected at ticks 10–70. Bounded search — not exhaustive verification.",
        "score_formula": "3 × unmet people + 5 × urgent deadline misses + 0.2 × mean time-to-service",
        "baseline": baseline,
        "worst": results[:6],
        "all_scores": [{"trial": r["trial"], "score": r["score"], "unmet": r["metrics"]["unmet_people"], "misses": r["metrics"]["deadline_misses"]} for r in results],
    }
