# Benchmarks

## Methodology

- **Strategies:** decentralised multi-agent negotiation, centralised Hungarian optimiser, and greedy nearest-feasible dispatch.
- **Paired design:** for each seed, every strategy sees identical incident arrivals, reports and noise, flood, and scheduled failures. All three use the same cost weights (balanced: T 0.35, R 0.25, U 0.20, F 0.20), the same shelter agents and the same safety shield.
- **What differs:** information access and coordination mechanism only. Decentralised agents plan on beliefs that are `comm_delay` ticks old and resolve conflicts by deferred acceptance. The centralised coordinator sees everything instantly and solves a global assignment.
- **Reported:** mean ± standard deviation across seeds, every individual run (Strategy Arena page), and paired differences (decentralised − centralised, same seed).
- **No hand-tuning toward a winner.** Nothing in the code favours either strategy.

To reproduce:

```bash
python scripts/run_benchmarks.py 10
```

This writes [`benchmark_results.md`](benchmark_results.md). You can run the same experiment interactively at `/arena`.

## Results (seeds 1–10, 180 ticks)

These are the full tables from the latest run in [`benchmark_results.md`](benchmark_results.md). Summary:

| Scenario | Mean TTS (min) dec / cen / greedy | Unmet people dec / cen | Fairness dec / cen | Messages dec / cen |
|---|---|---|---|---|
| Normal | 26.0 / 24.9 / 27.5 | 14.0 / 14.9 | 0.795 / 0.764 | 1175 / 1553 |
| Conflicting information | 24.0 / 20.8 / 24.6 | 14.4 / 10.9 | 0.776 / 0.750 | 1329 / 1705 |
| Triple failure | 28.0 / 27.2 / 31.2 | 28.8 / 28.2 | 0.792 / 0.791 | 1579 / 1705 |
| Resource shortage | 44.0 / 42.1 / 46.0 | 34.7 / 29.8 | 0.821 / 0.791 | 1164 / 1180 |

Route violations and invariant violations were **0** in every run, for every strategy.

## Honest reading

- **The centralised optimiser is faster on mean time-to-service in every scenario**, by about 1–3 minutes. That is the expected price of the decentralised information model: agents act on news that is `comm_delay` ticks old and must re-bid after every version change. Under conflicting information, where the delay is 3 ticks, the gap is largest (+3.2 ± 3.5 min) and centralised also leaves fewer people unmet.
- **Decentralised negotiation uses fewer coordination messages** than the centralised baseline in these runs, because centralised coordination needs a status report from every unit every round. It also shows **slightly higher Jain fairness** in all four scenarios. Both differences are small compared with their standard deviations.
- **Greedy** is the slowest on time-to-service but often the fairest and has the fewest deadline misses. It always serves the most urgent request first, at the cost of efficiency.
- Most paired differences fall **within one standard deviation**. With 10 seeds we cannot claim either coordination mechanism is significantly better on throughput.

The defensible claim is therefore narrower than "multi-agent is better": decentralised negotiation reaches near-centralised service with no global coordinator, delayed and partial information, and zero safety violations, while recovering from injected failures. That is the property that matters when the central coordinator or its communications are themselves at risk.

## Not measured (limitations)

- Wall-clock robustness to a real network, and message loss beyond blackouts.
- Calibration of the report-confidence heuristic.
- Sensitivity to cost weights beyond the four built-in policies. Use the Decision Lab or Arena to explore this.
