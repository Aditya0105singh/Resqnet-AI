"""Reproduce every published benchmark number.

    python scripts/run_benchmarks.py [n_seeds] [--workers N]

Runs the optimisation-quality suite, the failure-resilience suite and the parameter
sweeps over seeds 1..n_seeds (default 10) for every strategy, then writes:

    data/evaluation/benchmarks/<suite>/<scenario>.csv   raw per-seed rows
    data/evaluation/benchmarks/sweeps/<sweep>.csv       raw per-seed sweep rows
    data/evaluation/benchmarks/summary.json             aggregates + CIs (served at /api/evaluation)
    docs/benchmark_results.md                           human-readable tables
"""
import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.analysis.evaluation import run_all  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("n_seeds", nargs="?", type=int, default=10)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    run_all(list(range(1, a.n_seeds + 1)), ROOT, workers=a.workers)
