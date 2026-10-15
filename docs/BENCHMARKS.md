# Benchmarks

The full generated tables are in [`benchmark_results.md`](benchmark_results.md). Raw per-seed rows are in [`data/evaluation/benchmarks/`](../data/evaluation/benchmarks/). The same results are browsable in the app at `/arena` → *Published results*.

## Reproduce

```bash
python scripts/run_benchmarks.py 10            # 10 seeds; --workers N to parallelise (about 1 min on 4 cores)
```

| Output | Contents |
|---|---|
| `data/evaluation/benchmarks/<suite>/<scenario>.csv` | One row per (seed, strategy) with every summary metric. A row can be reproduced exactly by running that scenario, seed and strategy. |
| `data/evaluation/benchmarks/sweeps/<sweep>.csv` | Raw sweep rows, plus the swept parameter. |
| `data/evaluation/benchmarks/summary.json` | Aggregates, CIs and paired comparisons. Served at `GET /api/evaluation`. |
| `docs/benchmark_results.md` | The human-readable tables. |

Everything is deterministic given the seed except `wall_ms` and `compute_ms`, which are wall-clock timings. Those are the only measures of computation cost; every other time is **simulated minutes**.

## Methodology

- **Strategies:**
  - `decentralized`: instant contract-net and deferred acceptance on delayed beliefs.
  - `message_passing`: independent agents over a simulated network; see [MESSAGE_PASSING.md](MESSAGE_PASSING.md).
  - `centralized`: Hungarian optimiser with complete, instant state.
  - `greedy`: most-urgent request first, nearest feasible unit.
- **Paired design.** For each seed, every strategy sees identical incident arrivals, reports and noise, flood and scheduled failures. All strategies use the same cost weights, shelter agents and safety shield. Only information access and the coordination mechanism differ. Nothing in the code favours a strategy.
- **Two questions, kept apart:**
  1. **Optimisation quality (healthy network)**: `normal`, `flash_flood`, `resource_shortage`, `shelter_overflow`, `contradictory`, `viral_sos`. Communications and the coordinator work.
  2. **Failure resilience**: `triple_failure`, `bridge_closure`, `coordinator_outage`, `network_partition`, `lossy_network`.
- **Sweeps** vary one parameter on the `normal` scenario:
  - SOS report noise, for every strategy;
  - message loss at 1 min/hop, for `message_passing` only, since it is the only strategy that models transport.
- **Statistics:**
  - mean, sd, median, IQR;
  - a **95% percentile-bootstrap CI** of the mean (2,000 resamples, seeded, reported only when n ≥ 5);
  - **paired per-seed differences** with their own bootstrap CI.

  A difference is called *significant* only when its CI excludes zero. With 10 seeds that is a modest bar, so treat it as evidence, not proof.

## Metric definitions

| Metric | Definition |
|---|---|
| service rate | People delivered to a shelter ÷ people who truly needed rescue and had appeared by the end of the run (ground truth, never seen by agents). |
| mean time to service | Mean minutes from an incident's first report to its first pickup. |
| unmet people | People who needed rescue but were not delivered by the end. |
| urgent misses | Urgency ≥ 4 incidents whose first pickup came after their deadline. |
| fairness (Jain) | Jain's index over the neighbourhoods' mean waits (1 = perfectly even). |
| recovery (min) | For failures that **break commitments** (bridge closure, unit failure, shelter overflow): minutes from the event until every affected incident is covered by a valid commitment again, or closed. |
| never recovered | Such disruptions still unresolved at the end of the run. |
| uncovered people·min during outage | For **coordinator outages and partitions**, which break no commitment: the per-minute sum, over the outage, of people in eligible requests that no commitment covers. This is the service lost while the network is down. |
| commitments during outage | New commitments made while the outage lasted. For a partition, members of the partition never commit; this is asserted in the tests. |
| backlog clear (min) | Minutes after the outage ends until the uncovered backlog is back at its pre-outage level. |
| messages / msgs lost | Coordination messages sent / lost to loss or partitions (`message_passing`). |

## Results (seeds 1–10, 180 ticks)

See [`benchmark_results.md`](benchmark_results.md) for every cell with its CI. Route violations and invariant violations were **0 in every run, for every strategy, in every scenario**.

### Optimisation quality: the centralised optimiser is at least as good

- On a healthy network the four strategies are close. Most CIs overlap.
- Where a difference is significant, it usually favours **centralised over the agent strategies**:
  - `normal`: decentralised is +1.1 min slower on mean time-to-service;
  - `contradictory`: +3.2 min slower, and it leaves 3.5 more people unserved;
  - `resource_shortage`: message-passing serves 6.5 fewer people.
- Greedy is significantly slower than decentralised in several scenarios.
- This is the expected price of acting on delayed, partial information without a global view.

### Failure resilience: the agent strategies keep working when coordination fails

- **Coordinator outage (60 min).**
  - Both agent strategies keep a service rate of about 0.86. Centralised drops to 0.76 and greedy to 0.79.
  - Decentralised − centralised: **+0.10 service rate [+0.05, +0.16]**, **−19 min mean time-to-service [−22, −16]**, and −1,800 uncovered people·min.
  - Centralised and greedy make 0 commitments during the outage, by design.
  - This holds under the stated assumption that peer communication survives a coordinator failure.
- **Network partition (3 boats and a shelter cut off for 40 min).** Message-passing serves significantly more people than centralised: +0.036 service rate [+0.004, +0.078]. No strategy commits across the split.
- **Lossy network (15% loss, 10% duplicates, 1 min/hop).** Message-passing pays the cost:
  - +16.5 min mean time-to-service vs centralised;
  - −0.07 service rate.
  - The other strategies do not model message transport, so this is a measured cost of an unreliable network, not a like-for-like comparison.
- **Triple failure and bridge closure.**
  - No strategy is significantly better on service rate.
  - Recovery from broken commitments takes 0 min for every strategy after a bridge closure, because every strategy reroutes or reassigns in the same minute. After a triple failure every disruption is recovered in every run, with a mean of 1.4–4.5 min (greedy fastest, decentralised slowest).
  - The difference shows in time-to-service instead: after a bridge closure, centralised is 1.4 min faster than decentralised [0.4, 2.3] and 2.9 min faster than message-passing [0.5, 5.7].

### Sweeps

- **Report noise** (0 → 0.6) barely moves service rate for any strategy, and every CI overlaps. Report reconciliation (noisy-OR merging, reliability-weighted location, physical verification on arrival) absorbs count and urgency noise. Location noise, false alarms and contradictions are tested separately in `contradictory`.
- **Message loss** (0 → 0.3, message-passing) is flat up to about 10% loss, then service falls to 0.74 at 20% loss and 0.68 at 30% loss. Timeouts and leases keep the system safe throughout, but recovery costs time.

### SOS fusion: counting forwards once

On `viral_sos`, half of resident SOS messages are forwarded 2–5 more times, including rumours of victims who do not exist. Turning on forward grouping (`fusion_dedup`), with the same seeds, **significantly reduces trips to non-existent victims for all four strategies**: from about 2.3–2.5 down to 1.7–1.9 per run, with every paired CI excluding zero. Service rate does not change significantly. The remaining trips are deliberate, because a single credible SOS still gets a provisional dispatch (rule E2).

**Trade-off of abstaining.** Disputed incidents now wait for a dispatcher, or for the review window. The automated benchmark has no dispatcher, so it always waits the full 5–10 min. In `contradictory` that cost the centralised optimiser about 3 points of service rate compared with the previous rule, which blended conflicting evidence into a low confidence and dispatched by urgency (0.895 → 0.865). The agent strategies were essentially unchanged. With a dispatcher answering, the review window is an upper bound, not the typical delay.

### The defensible claim

The evidence does not support "multi-agent is better". What it supports is:

> On a healthy network, decentralised negotiation comes within a few minutes of a centralised optimiser. When the central coordinator fails, it keeps serving people (about 10 points more service, about 19 minutes faster), and under every tested failure no strategy violates a safety invariant. The price is sensitivity to message loss above about 10%.

## Not measured (limitations)

- A real radio network: the transport model has independent loss, fixed latency and clean partitions.
- Calibration of the report-confidence heuristic against labelled data.
- Sensitivity to cost weights beyond the four built-in policies. The Decision Lab and Arena can explore this.
- Real geography: Riverbend is synthetic (see the build spec, WP5).
