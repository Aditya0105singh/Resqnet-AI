# Agents and negotiation protocol

## Agent types

| Agent | Knows | Decides |
|---|---|---|
| **Incident agent** (one per reconciled incident) | Its own reports, evidence and current version | Publishes the request (people, urgency, deadline, confidence). Ranks bids, proposes to its best bidder and rejects stale bids. |
| **Rescue agent** (boat / ground team) | Its own state exactly. Incident publications and network state as of `t − comm_delay`. Closures it discovered itself. | Plans routes on its *believed* network, evaluates options and bids on its top 3. When holding several proposals it keeps the one with the lowest cost. |
| **Shelter agent** | Its own capacity, occupancy and reservations | Broadcasts capacity offers and accepts or rejects reservations. Revokes reservations, latest first (LIFO), when its capacity drops. Renews reservations held by connected units. |
| **Route agent** | Authoritative graph and flood state | Decides edge traversability per mode. The shield uses it to validate routes and moves. |
| **Coordination / safety** | Authoritative state | Runs rounds, applies the safety shield and records commitments. It does **not** choose assignments in decentralised mode. |

## Decentralised protocol (`negotiation/decentralized.py`)

```
REQUEST ─▶ BID ─▶ PROVISIONAL_ACCEPT ─▶ RESERVE ─▶ ACCEPT_RESERVATION ─▶ (shield) ─▶ COMMIT
                 └▶ REJECT (agent prefers another)  └▶ REJECT_RESERVATION   └▶ SAFETY_REJECT
later: CANCEL · RENEGOTIATE · EXPIRE
```

1. **REQUEST.** Each open incident's latest publication that is at least `comm_delay` ticks old is broadcast. Shelter agents broadcast OFFERs.
2. **BID.** Each idle, connected agent runs Dijkstra on its believed network from its position, which may be mid-edge. For each visible request it computes: pickup ETA; the best shelter that is reachable and offers enough seats; and the cost C = 0.35T + 0.25R + 0.20U + 0.20F. It then bids on its 3 cheapest requests.
3. **Bid screening.** An incident agent rejects any bid made against an outdated version of itself (stale bid).
4. **Deferred acceptance.** Incidents, in priority order, propose to their best remaining bidder. An agent holding two proposals keeps the cheaper one and rejects the other with the reason. This repeats until the matching is stable.
5. **RESERVE.** The matched agent requests seats from its preferred shelter, then tries the next shelters in order.
6. **SAFETY.** The shield validates S1–S7. On failure the reservation is released, the agent learns the bad edge, and the pair is excluded for the rest of the round.
7. **COMMIT.** A versioned `Assignment` is created. Up to 3 passes per tick let agents that failed find another match.

### Deterministic tie-breaking

- Incident priority: (urgency ↓, deadline ↑, confidence ↓, id ↑)
- Agent preference: (cost ↑, incident priority)
- Bid ranking at an incident: (cost ↑, resource id ↑)
- All dictionaries are iterated in sorted ID order.

### Partial information, in concrete terms

- `comm_delay` (default 1, 3 in scenario B): requests and network closures reach agents late.
- `COMM_BLACKOUT`: the agent cannot bid, cannot renew reservations and does not hear about closures. It keeps executing its last valid commitment and its reservation may expire. When it reconnects, it reconciles.
- Closures nobody has told the agent about are found at the edge by the movement gate. The agent records the edge and replans.

## Message-passing protocol (`negotiation/message_passing.py`)

The instant protocol above runs every agent inside one function. The `message_passing` strategy instead runs each agent as a separate handler with its own state. Agents talk only through a simulated network with latency, loss, duplicate delivery and partitions. Rescue agents commit only while holding a shelter lease granted for that proposal id, and only after the safety shield passes. Lost messages are recovered by proposal timeouts and lease expiry. The full protocol, fault handling and measured results are in [MESSAGE_PASSING.md](MESSAGE_PASSING.md).

## Centralised baseline (`optimization/centralized.py`)

A coordinator with instant, complete state builds the cost matrix (idle units × open requests) using the *same* `evaluate()` function. It solves the matrix with the Hungarian algorithm (`scipy.optimize.linear_sum_assignment`), then reserves and commits through the same shelter agents and shield. If a commit fails, the solver reruns without that pair, up to 3 passes. The **greedy** baseline handles requests in priority order and gives each the idle unit with the smallest pickup ETA.

## What the agents are not

There is no LLM in the control loop. Every message is produced by the deterministic protocol above, and the UI never presents these messages as free-form conversation. Natural-language explanations are templated from structured decision records.
