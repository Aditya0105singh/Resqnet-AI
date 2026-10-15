# Resilience demonstration

## Pitch

RESQNET explores the tradeoff between efficient central optimisation and continuity
of dispatch when the coordinator fails. These are synthetic, reproducible experiments,
not evidence of production emergency readiness or universally superior dispatch.

## Live walkthrough

Open `/judge`. Start the bridge mission and advance in five-minute steps until
a ground team's live route crosses a bridge. Trigger the triple failure. The button
refuses to inject if no live bridge route exists. Rose dashed paths show the actual
pre-closure routes for 15 simulated minutes; current paths retain their usual colours.
Inspect a decision, then open Decision Lab to test another future.

Load Coordinator Outage, then open Arena. Run all three strategies with seeds 1-5.
Also run Normal Flood as a control. All outcomes are computed by the engine.

## Outage model

`COORDINATOR_OUTAGE` takes an integer `duration` from 1 to 300 minutes.
The preset disables central dispatch at t=15 and restores it at t=75 (exclusive end).
Centralized and greedy strategies cannot create new assignments in that interval.
Previously committed missions, local movement, route safety and shelter handling
continue. Decentralized peer communications remain available. There is no standby
coordinator. This is not a total network partition or a distributed backend outage;
all agents are simulated inside one authoritative process.

Repeated outages extend the deadline and never shorten an existing outage.
Availability is included in frames and in the replay hash.
The existing disruption-recovery metric does not measure coordinator uptime;
use coordinator status for the outage window, not the generic recovery metric.

## Measured results

Five paired seeds (1-5), preset duration 180 minutes, default resources and costs.
Values below are the means across runs, measured after this feature was implemented.

| Metric | Decentralized | Centralized | Greedy |
| --- | ---: | ---: | ---: |
| People rescued | 88.0 | 78.0 | 79.4 |
| Mean time to service (min) | 23.990 | 47.058 | 47.902 |
| Deadline misses | 2.2 | 4.8 | 4.0 |
| Unmet people | 15.6 | 25.6 | 24.2 |
| Jain fairness | 0.796 | 0.860 | 0.859 |
| Route violations | 0 | 0 | 0 |

The centralized result has better measured fairness in this experiment.
Five seeds are preliminary evidence, not a statistical significance claim.
Do not describe the result as superiority under every outage or communications model.

## Verification and remaining release work

Core simulation suite: 37 tests passed. New outage and bridge suite: 11 tests passed.
Frontend TypeScript and production build passed. Browser layout and interaction QA,
full API suite diagnosis, deployment, backup recording and pitch deck remain release
work. The large main JavaScript bundle warning remains.
