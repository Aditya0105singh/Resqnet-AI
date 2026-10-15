# Message-passing agents (strategy `message_passing`)

The original `decentralized` strategy computes every agent's bids inside one function, and its messages are only a log. The `message_passing` strategy makes the agents genuinely separate:

- Every incident, rescue and shelter agent is its own handler with its own local state.
- Each handler reads only its own inbox.
- Each handler acts only by sending messages through a simulated network: `backend/app/negotiation/transport.py`.

The protocol lives in `backend/app/negotiation/message_passing.py`.

## Protocol

```
incident ──REQUEST(cfp)──▶ every rescue agent         call for proposals (re-sent on version change / after 10 min unanswered)
rescue   ──BID(cfp)──────▶ incident                   top-3 cheapest requests it knows about, on its own believed network
incident ──PROPOSE(pid)──▶ best bidder                one outstanding proposal per incident, with an expiry
rescue   ──RESERVE(pid)──▶ shelter                    or DECLINE(pid) ▶ incident (busy / engaged / infeasible)
shelter  ──ACCEPT_RESERVATION(lease) / REJECT_RESERVATION──▶ rescue
rescue   ── safety shield ── COMMIT ──CONFIRM(pid)──▶ incident
shelter  ──OFFER──▶ every rescue agent                free capacity, sent whenever it changes
incident ──WITHDRAW──▶ every rescue agent             request closed
```

- **Commitment authority.** The rescue agent commits itself (the COMMIT message comes from the unit, not a coordinator). It does so only while it holds a shelter reservation that was granted for that exact proposal id. The shield (S1–S7) must also pass against authoritative state, so stale proposals fail the S5 version check.
- **Exclusivity.** Each shelter agent owns its capacity, so reservations cannot be double-granted. Each rescue agent executes at most one proposal at a time.

## Network model

These settings are in `ScenarioConfig` and are accepted as API overrides.

| Setting | Meaning |
|---|---|
| `msg_latency` | Ticks per hop, from 0 to 10. 0 delivers within the same simulated minute. |
| `msg_loss` | Each message is dropped independently with this probability, from 0 to 0.5. |
| `msg_duplicate` | At-least-once delivery: a message arrives twice with this probability, from 0 to 0.5. |
| `NETWORK_PARTITION` event | `{members: [unit/shelter ids], duration}`. Members can only talk to each other until it heals. |
| `COMM_BLACKOUT` event | Isolates one unit completely. |

The bus has its own seeded RNG, so runs remain deterministic and replay-verifiable.

## Fault handling

| Fault | Mechanism |
|---|---|
| Duplicate delivery | Receivers drop already-processed message ids. A shelter answers each proposal id once. |
| Lost PROPOSE / reply | The proposal expires and the incident moves to its next bidder (`EXPIRE`). |
| Lost reservation grant | The seats are held only as a lease (`pending_until`). An unclaimed lease lapses and the seats are returned. |
| Late grant for a dead proposal | The rescue agent sends `CANCEL_RESERVATION`, which is idempotent. |
| Partition | Messages across the split are lost (`LOST` in the negotiation log). Committed missions continue. **No new commitment is made across the split.** Availability drops, but safety holds. |

The partition rule also applies to the instant strategies:

- Isolated units cannot be bid on or dispatched by the coordinator.
- Isolated shelters make no offers.
- The shield's S7 check rejects commits for isolated units.

## Measured results

These are seeds 1–10 with 180 ticks per run, mean ± sd. They are reproducible with `analysis.runs.benchmark`.

**How to read this:** loss and latency only affect `message_passing`, because the other strategies do not model message transport. So the `lossy_network` rows show how message-passing degrades. They are not a head-to-head comparison.


### normal

| strategy | mean_time_to_service | people_rescued | unmet_people | deadline_misses | negotiation_messages | messages_lost | route_violations |
|---|---|---|---|---|---|---|---|
| decentralized | 26.0 ± 6.0 | 91.8 ± 10.7 | 14.0 ± 5.5 | 2.2 ± 1.5 | 1174.5 ± 320.6 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| message_passing | 25.4 ± 5.8 | 91.2 ± 12.5 | 14.6 ± 8.7 | 2.1 ± 1.2 | 1541.7 ± 305.5 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| centralized | 24.9 ± 5.1 | 90.9 ± 13.1 | 14.9 ± 7.2 | 1.9 ± 1.4 | 1553.4 ± 464.6 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| greedy | 27.5 ± 4.2 | 90.6 ± 11.9 | 15.2 ± 6.9 | 1.4 ± 1.6 | 1663.8 ± 623.0 | 0.0 ± 0.0 | 0.0 ± 0.0 |

### lossy_network

| strategy | mean_time_to_service | people_rescued | unmet_people | deadline_misses | negotiation_messages | messages_lost | route_violations |
|---|---|---|---|---|---|---|---|
| decentralized | 26.0 ± 6.0 | 91.8 ± 10.7 | 14.0 ± 5.5 | 2.2 ± 1.5 | 1174.5 ± 320.6 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| message_passing | 41.4 ± 4.6 | 83.0 ± 8.3 | 22.8 ± 5.4 | 4.9 ± 1.6 | 2016.5 ± 244.2 | 277.1 ± 38.0 | 0.0 ± 0.0 |
| centralized | 24.9 ± 5.1 | 90.9 ± 13.1 | 14.9 ± 7.2 | 1.9 ± 1.4 | 1553.4 ± 464.6 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| greedy | 27.5 ± 4.2 | 90.6 ± 11.9 | 15.2 ± 6.9 | 1.4 ± 1.6 | 1663.8 ± 623.0 | 0.0 ± 0.0 | 0.0 ± 0.0 |

### network_partition

| strategy | mean_time_to_service | people_rescued | unmet_people | deadline_misses | negotiation_messages | messages_lost | route_violations |
|---|---|---|---|---|---|---|---|
| decentralized | 27.3 ± 5.3 | 85.2 ± 11.2 | 20.6 ± 8.8 | 2.0 ± 1.2 | 1214.6 ± 345.8 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| message_passing | 27.5 ± 5.3 | 87.9 ± 8.9 | 17.9 ± 9.2 | 2.4 ± 0.8 | 1691.1 ± 272.3 | 109.6 ± 20.9 | 0.0 ± 0.0 |
| centralized | 26.3 ± 5.1 | 84.4 ± 11.1 | 21.4 ± 8.7 | 1.7 ± 1.3 | 1526.5 ± 410.0 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| greedy | 29.9 ± 5.3 | 87.9 ± 10.5 | 17.9 ± 7.4 | 1.9 ± 1.7 | 1476.5 ± 603.1 | 0.0 ± 0.0 | 0.0 ± 0.0 |

### triple_failure

| strategy | mean_time_to_service | people_rescued | unmet_people | deadline_misses | negotiation_messages | messages_lost | route_violations |
|---|---|---|---|---|---|---|---|
| decentralized | 28.0 ± 4.0 | 77.0 ± 12.9 | 28.8 ± 11.8 | 3.1 ± 1.1 | 1578.7 ± 247.5 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| message_passing | 27.7 ± 2.9 | 79.7 ± 6.9 | 26.1 ± 8.9 | 2.7 ± 1.3 | 1762.7 ± 191.2 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| centralized | 27.2 ± 4.6 | 77.6 ± 10.6 | 28.2 ± 8.0 | 2.6 ± 1.2 | 1704.5 ± 314.0 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| greedy | 31.2 ± 5.8 | 76.8 ± 6.2 | 29.0 ± 6.7 | 2.0 ± 1.6 | 1899.9 ± 343.1 | 0.0 ± 0.0 | 0.0 ± 0.0 |

### What this shows

- **Healthy network.** Message-passing serves about as well as the instant protocol and the centralised optimiser: mean time-to-service is 25.4 vs 26.0 vs 24.9 min, all within one sd. It sends about 30% more messages than the instant protocol, because every offer, decline and confirmation is now an explicit message.
- **15% loss, 10% duplication, 1 min/hop.** Time-to-service rises to about 41 min and roughly 8 more people go unserved. Recovery through timeouts and leases works (0 invariant violations, 0 route violations), but it costs time. This is the price of an unreliable network, and we report it rather than hide it.
- **Network partition.** All strategies lose availability for the isolated units. No strategy commits across the split. Every strategy keeps 0 safety and invariant violations.

The same invariants were checked with a 300-example Hypothesis run. It mixed bridge closures, unit failures, shelter overflows, flood surges and partitions, with 25% loss and duplication, across all four strategies, and found no violations.
