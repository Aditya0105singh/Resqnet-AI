"""Reproduce docs/BENCHMARKS.md results: python scripts/run_benchmarks.py [n_seeds]"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.analysis.runs import benchmark  # noqa: E402
from app.simulation.scenarios import get_preset  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
KEYS = [("mean_time_to_service", "mean TTS (min)"), ("deadline_misses", "urgent misses"), ("unmet_people", "unmet people"), ("idle_with_demand_ticks", "idle w/ demand"), ("fairness_jain", "fairness (Jain)"), ("route_violations", "route violations"), ("negotiation_messages", "messages"), ("compute_ms", "coord. ms")]

out = [f"Seeds 1–{N}, 180 ticks each, all strategies share the same seeds, events, cost function and safety shield. Mean ± sd.\n"]
for sc in ["normal", "contradictory", "triple_failure", "resource_shortage"]:
    res = benchmark(get_preset(sc), ["decentralized", "centralized", "greedy"], list(range(1, N + 1)))
    out.append(f"\n### {sc}\n\n| strategy | " + " | ".join(l for _, l in KEYS) + " |\n|---|" + "---|" * len(KEYS))
    for s, summ in res["summary"].items():
        out.append(f"| {s} | " + " | ".join(f"{summ[k]['mean']} ± {summ[k]['std']}" if summ[k]["mean"] is not None else "—" for k, _ in KEYS) + " |")
    p = res["paired_decentralized_minus_centralized"]
    out.append("\nPaired (decentralized − centralized): " + ", ".join(f"{k} {v['mean']:+} ± {v['std']}" for k, v in p.items() if v["mean"] is not None))
    print(sc, "done", flush=True)
path = os.path.join(os.path.dirname(__file__), "..", "docs", "benchmark_results.md")
with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("wrote", path)
