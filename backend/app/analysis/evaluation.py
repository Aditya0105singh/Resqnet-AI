"""Reproducible evaluation suites: optimisation quality, failure resilience, and sweeps.

The PS asks for a centralised-vs-decentralised comparison. A single "who wins" table
mixes two different questions, so the evaluation keeps them apart:

1. **Optimisation quality** (healthy network): every strategy has working
   communications and a working coordinator. How well does each one dispatch?
2. **Failure resilience**: infrastructure, coordinator or network failures. How much
   service is lost, how fast does it recover, and does safety hold?

Sweeps vary one parameter (report noise, message loss) to produce degradation curves.

Every run is a full simulation from (scenario, seed, strategy). Raw per-seed rows are
written to CSV next to the summary, so any number shown can be traced and re-run.
`wall_ms` / `compute_ms` are wall-clock timings and the only non-deterministic fields.
"""
from __future__ import annotations

import copy
import csv
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable, Iterable, Optional

from ..metrics.metrics import SUMMARY_KEYS
from ..simulation.scenarios import STRATEGIES, ScenarioConfig, get_preset
from .runs import aggregate, paired_difference, run_one, summarise

SUITES: dict[str, dict[str, Any]] = {
    "quality": {
        "title": "Optimisation quality (healthy network)",
        "question": "With working communications and a working coordinator, how well does each strategy dispatch?",
        "scenarios": ["normal", "flash_flood", "resource_shortage", "shelter_overflow", "contradictory", "viral_sos"],
    },
    "resilience": {
        "title": "Failure resilience",
        "question": "Under infrastructure, coordinator and network failures: how much service is lost, how fast is it recovered, and does safety hold?",
        "scenarios": ["triple_failure", "bridge_closure", "coordinator_outage", "network_partition", "lossy_network"],
    },
}

SWEEPS: dict[str, dict[str, Any]] = {
    "report_noise": {
        "title": "Service vs SOS report noise",
        "question": "How does dispatch quality degrade as reports become noisier (wrong counts, urgency, location)?",
        "base": "normal",
        "param": "report_noise",
        "values": [0.0, 0.15, 0.3, 0.45, 0.6],
        "strategies": list(STRATEGIES),
        "fixed": {},
    },
    "message_loss": {
        "title": "Service vs message loss (message-passing agents, 1 min/hop)",
        "question": "How much service does the message-passing protocol lose as the radio network drops more messages?",
        "base": "normal",
        "param": "msg_loss",
        "values": [0.0, 0.05, 0.1, 0.2, 0.3],
        "strategies": ["message_passing"],
        "fixed": {"msg_latency": 1},
    },
}

ABLATIONS: dict[str, dict[str, Any]] = {
    "fusion_dedup": {
        "title": "Ablation: counting forwarded SOS copies once",
        "question": "Does grouping verbatim forwards into one source reduce wasted trips to rumoured victims, without costing service?",
        "base": "viral_sos",
        "param": "fusion_dedup",
        "variants": [["off", False], ["on", True]],
        "strategies": list(STRATEGIES),
        "keys": ["false_alarm_visits", "service_rate", "mean_time_to_service", "deadline_misses"],
    },
}

SWEEP_KEYS = ["service_rate", "mean_time_to_service", "deadline_misses", "unmet_people"]
CSV_KEYS = ["seed", "strategy"] + SUMMARY_KEYS + ["wall_ms"]


def _job(args: tuple[dict[str, Any], str, int]) -> dict[str, Any]:
    cfg_d, strategy, seed = args
    cfg = ScenarioConfig.from_dict(cfg_d)
    cfg.seed = seed
    r = run_one(cfg, strategy)
    r.update({"seed": seed, "strategy": strategy})
    return r


def _run_all(jobs: list[tuple[dict[str, Any], str, int]], workers: int, progress: Optional[Callable[[int, int], None]] = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if workers <= 1:
        for i, j in enumerate(jobs):
            out.append(_job(j))
            if progress:
                progress(i + 1, len(jobs))
        return out
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, r in enumerate(ex.map(_job, jobs, chunksize=2)):
            out.append(r)
            if progress:
                progress(i + 1, len(jobs))
    return out


def run_suite(name: str, seeds: list[int], strategies: Iterable[str] = STRATEGIES, workers: int = 1, scenarios: Optional[list[str]] = None, progress: Optional[Callable[[int, int], None]] = None) -> dict[str, Any]:
    spec = SUITES[name]
    strategies = list(strategies)
    scs = scenarios or spec["scenarios"]
    jobs = [(get_preset(sc).to_dict(), st, seed) for sc in scs for seed in seeds for st in strategies]
    rows = _run_all(jobs, workers, progress)
    per = len(seeds) * len(strategies)
    results = {}
    for i, sc in enumerate(scs):
        results[sc] = summarise(sc, strategies, seeds, rows[i * per:(i + 1) * per])
        results[sc]["description"] = get_preset(sc).description
    return {"title": spec["title"], "question": spec["question"], "scenarios": results}


def run_ablation(name: str, seeds: list[int], workers: int = 1, progress: Optional[Callable[[int, int], None]] = None) -> dict[str, Any]:
    """Same seeds, same strategy, one switch flipped: per-strategy paired difference (on − off)."""
    spec = ABLATIONS[name]
    jobs, tags = [], []
    for label, value in spec["variants"]:
        cfg = get_preset(spec["base"], **{spec["param"]: value})
        for seed in seeds:
            for st in spec["strategies"]:
                jobs.append((cfg.to_dict(), st, seed))
                tags.append(label)
    rows = _run_all(jobs, workers, progress)
    for r, label in zip(rows, tags):
        r["variant"] = label
    (off, _), (on, _) = spec["variants"]
    per_strategy = {}
    for st in spec["strategies"]:
        rs = [dict(r, strategy=r["variant"]) for r in rows if r["strategy"] == st]
        per_strategy[st] = {
            "summary": {v: {k: aggregate([r.get(k) for r in rs if r["strategy"] == v]) for k in spec["keys"]} for v, _ in spec["variants"]},
            "paired": {k: paired_difference(rs, on, off, k, seeds) for k in spec["keys"]},
        }
    return {**{k: spec[k] for k in ("title", "question", "base", "param", "variants", "strategies", "keys")}, "results": per_strategy, "runs": rows}


def run_sweep(name: str, seeds: list[int], workers: int = 1, progress: Optional[Callable[[int, int], None]] = None) -> dict[str, Any]:
    spec = SWEEPS[name]
    jobs, keys = [], []
    for v in spec["values"]:
        cfg = get_preset(spec["base"], **spec["fixed"], **{spec["param"]: v})
        for seed in seeds:
            for st in spec["strategies"]:
                jobs.append((cfg.to_dict(), st, seed))
                keys.append(v)
    rows = _run_all(jobs, workers, progress)
    for r, v in zip(rows, keys):
        r[spec["param"]] = v
    points = []
    for v in spec["values"]:
        for st in spec["strategies"]:
            sel = [r for r in rows if r[spec["param"]] == v and r["strategy"] == st]
            points.append({"value": v, "strategy": st, **{k: aggregate([r.get(k) for r in sel]) for k in SWEEP_KEYS}})
    return {**{k: spec[k] for k in ("title", "question", "base", "param", "values", "strategies", "fixed")}, "points": points, "runs": rows}


# ---------------------------------------------------------------- writers


def write_csv(path: str, rows: list[dict[str, Any]], extra: Optional[list[str]] = None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols = (extra or []) + CSV_KEYS
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})


def _fmt_ci(a: dict[str, Any], d: int = 1) -> str:
    if a.get("mean") is None:
        return "—"
    s = f"{a['mean']:.{d}f}"
    if a.get("ci_low") is not None:
        s += f" [{a['ci_low']:.{d}f}, {a['ci_high']:.{d}f}]"
    return s


MD_KEYS = [
    ("service_rate", "service rate", 3),
    ("mean_time_to_service", "mean TTS (min)", 1),
    ("deadline_misses", "urgent misses", 1),
    ("unmet_people", "unmet people", 1),
    ("fairness_jain", "fairness (Jain)", 3),
    ("route_violations", "route violations", 0),
    ("negotiation_messages", "messages", 0),
]
RESILIENCE_MD_KEYS = [
    ("mean_recovery_time", "recovery (min)", 1),
    ("unresolved_disruptions", "never recovered", 1),
    ("outage_uncovered_people_minutes", "uncovered people·min in outage", 0),
    ("commitments_during_outage", "commits during outage", 1),
    ("mean_outage_backlog_clear", "backlog clear (min)", 1),
    ("messages_lost", "msgs lost", 0),
]


def to_markdown(report: dict[str, Any]) -> str:
    seeds = report["seeds"]
    out = [
        "# Benchmark results",
        "",
        f"Generated by `python scripts/run_benchmarks.py {len(seeds)}`. Seeds {seeds[0]}–{seeds[-1]} ({len(seeds)} per cell), 180 ticks per run.",
        "All strategies share each seed's incidents, reports, failure schedule, cost function, shelter agents and safety shield.",
        "Cells show **mean [95% bootstrap CI]**. Raw per-seed rows are in `data/evaluation/benchmarks/`.",
        "",
        f"A paired difference is marked **significant** when the 95% CI of the per-seed difference excludes zero. With {len(seeds)} seeds that is a modest bar: treat it as evidence, not proof. CIs are omitted below 5 seeds.",
        "",
    ]
    for sname, suite in report["suites"].items():
        out += [f"## {suite['title']}", "", f"_{suite['question']}_", ""]
        keys = MD_KEYS + (RESILIENCE_MD_KEYS if sname == "resilience" else [])
        for sc, res in suite["scenarios"].items():
            out += [f"### {sc}", "", f"{res.get('description', '')}", "", "| strategy | " + " | ".join(l for _, l, _ in keys) + " |", "|---|" + "---|" * len(keys)]
            for st in res["strategies"]:
                out.append(f"| {st} | " + " | ".join(_fmt_ci(res["summary"][st][k], d) for k, _, d in keys) + " |")
            sig = []
            for pair, metrics in res["paired"].items():
                for k in ("service_rate", "mean_time_to_service", "unmet_people"):
                    m = metrics[k]
                    if m.get("significant"):
                        sig.append(f"{pair.replace('-', ' − ')} on {k}: {m['mean']:+.3g} [{m['ci_low']:+.3g}, {m['ci_high']:+.3g}]")
            out += ["", "Significant paired differences: " + ("; ".join(sig) if sig else "none (all CIs include zero)"), ""]
    for sw in report["sweeps"].values():
        out += [f"## {sw['title']}", "", f"_{sw['question']}_ Base scenario `{sw['base']}`{', with ' + ', '.join(f'{k}={v}' for k, v in sw['fixed'].items()) if sw['fixed'] else ''}.", ""]
        out += ["| " + sw["param"] + " | " + " | ".join(sw["strategies"]) + " |", "|---|" + "---|" * len(sw["strategies"])]
        for v in sw["values"]:
            cells = []
            for st in sw["strategies"]:
                p = next(p for p in sw["points"] if p["value"] == v and p["strategy"] == st)
                cells.append(_fmt_ci(p["service_rate"], 3))
            out.append(f"| {v} | " + " | ".join(cells) + " |")
        out += ["", "Cells: service rate (people delivered ÷ people who needed rescue), mean [95% CI].", ""]
    for ab in report.get("ablations", {}).values():
        (off, _), (on, _) = ab["variants"]
        out += [f"## {ab['title']}", "", f"_{ab['question']}_ Base scenario `{ab['base']}`; same seeds, only `{ab['param']}` changes.", ""]
        out += ["| strategy | " + " | ".join(f"{k}: {off} → {on} (paired Δ [95% CI])" for k in ab["keys"]) + " |", "|---|" + "---|" * len(ab["keys"])]
        for st in ab["strategies"]:
            res = ab["results"][st]
            cells = []
            for k in ab["keys"]:
                a, b, d = res["summary"][off][k], res["summary"][on][k], res["paired"][k]
                if a["mean"] is None or b["mean"] is None:
                    cells.append("—")
                    continue
                ci = f" [{d['ci_low']:+.3g}, {d['ci_high']:+.3g}]" if d.get("ci_low") is not None else ""
                cells.append(f"{a['mean']:.3g} → {b['mean']:.3g} ({d['mean']:+.3g}{ci}{', significant' if d.get('significant') else ''})")
            out.append(f"| {st} | " + " | ".join(cells) + " |")
        out.append("")
    return "\n".join(out) + "\n"


def run_all(seeds: list[int], root: str, workers: int = 1, log: Callable[[str], None] = print) -> dict[str, Any]:
    t0 = time.time()
    report: dict[str, Any] = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seeds": seeds, "strategies": list(STRATEGIES), "suites": {}, "sweeps": {}}
    out_dir = os.path.join(root, "data", "evaluation", "benchmarks")
    for name in SUITES:
        log(f"suite {name} …")
        suite = run_suite(name, seeds, workers=workers)
        for sc, res in suite["scenarios"].items():
            write_csv(os.path.join(out_dir, name, f"{sc}.csv"), res["runs"])
        report["suites"][name] = suite
    for name, spec in SWEEPS.items():
        log(f"sweep {name} …")
        sw = run_sweep(name, seeds, workers=workers)
        write_csv(os.path.join(out_dir, "sweeps", f"{name}.csv"), sw["runs"], extra=[spec["param"]])
        report["sweeps"][name] = sw
    report["ablations"] = {}
    for name, spec in ABLATIONS.items():
        log(f"ablation {name} …")
        ab = run_ablation(name, seeds, workers=workers)
        write_csv(os.path.join(out_dir, "ablations", f"{name}.csv"), ab["runs"], extra=["variant"])
        report["ablations"][name] = ab
    report["elapsed_s"] = round(time.time() - t0, 1)
    slim = copy.deepcopy(report)
    for suite in slim["suites"].values():
        for res in suite["scenarios"].values():
            res.pop("runs", None)  # raw rows live in the CSVs
    for sw in list(slim["sweeps"].values()) + list(slim["ablations"].values()):
        sw.pop("runs", None)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=1, default=float)
    with open(os.path.join(root, "docs", "benchmark_results.md"), "w", encoding="utf-8") as f:
        f.write(to_markdown(report))
    log(f"done in {report['elapsed_s']} s → {out_dir}")
    return report
