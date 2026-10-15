# resqnet — Multi-Agent Flood Rescue Coordination Digital Twin

**Code-E-Manipal 2.0 · PS 27 · Multi-Agent Systems / Logistics**
*Flood Rescue Dispatch Where Boats, Shelters and Roads Negotiate in Real Time*

> ⚠️ Research and educational simulation. Riverbend is a synthetic city; all incidents, reports and floods are generated from a seed. This is **not** an operational emergency-dispatch system.

Most emergency dashboards show you where the crisis is. resqnet shows how autonomous rescue resources negotiate, recover and coordinate after the original rescue plan stops working, and it lets you check whether a different decision would have done better.

## What it does

| | |
|---|---|
| **Deterministic digital twin** | Tick-based engine (1 tick = 1 simulated minute). Riverbend has 56 nodes, 92 road/river/bridge/jetty edges, 5 neighbourhoods, 3 bridges, 3 shelters, 5 boats and 4 ground teams. The flood rises and closes roads as it goes. |
| **Message-passing agents** | A fourth strategy runs each agent as a separate handler that only reads its own inbox. Messages travel over a simulated network with latency, loss, duplicates and partitions, and are recovered by proposal timeouts, reservation leases and idempotent handlers. See [docs/MESSAGE_PASSING.md](docs/MESSAGE_PASSING.md). |
| **Real multi-agent negotiation** | Incident, rescue, shelter and route agents work through contract-net bidding and deferred acceptance (Gale–Shapley). The protocol runs REQUEST → BID → PROVISIONAL_ACCEPT → RESERVE → SAFETY → COMMIT. Every message is logged. |
| **Partial information** | Decentralised agents get broadcasts after a comms delay and plan on their own, possibly stale, view of the network. They find closures physically and can lose comms completely during a blackout. |
| **Safety shield** | An independent validator checks every commit and every move against the true world state. It enforces invariants S1–S7: double booking, shelter capacity, prohibited edges, transport capacity, stale versions, reservation validity and operational status. |
| **Human approval queue** | Suggested actions (the recommender today; SOS intake and an AI assistant later) become *proposals*. Each one is previewed by running the exact action on a throwaway copy of the engine, including every safety-shield check, and is re-validated at approval. Only a dispatcher can approve: an AI source can propose but never approve. Proposals, approvals and rejections are events, so they replay. |
| **Fault injection mid-run** | You can close a bridge, disable a boat, overflow a shelter, trigger a surge, black out a unit's comms, send contradictory SOS reports, or fire a one-click **triple failure** that picks its targets from live state. |
| **Uncertainty-aware SOS** | Duplicate, delayed, contradictory and false-alarm reports are merged using noisy-OR evidence over *independent sources*: verbatim forwards of one SOS count once. When credible reports conflict, the system abstains (DISPUTED) and asks the dispatcher to confirm, dismiss or verify, instead of guessing. Low-confidence reports can still be dispatched provisionally under explicit rules E1–E5. |
| **Explainable decisions** | Each decision is stored as a structured record: evidence, candidate bids with their cost breakdown, rejections, the shelter negotiation, safety checks, and what would have changed the outcome. The explanation text is generated from that record. |
| **Counterfactual Decision Lab** | Fork the run at any past tick and change boats, bridges, shelter capacity, policy, comms delay or strategy. The lab then runs both futures under identical future events. |
| **Fair baseline** | A centralised Hungarian optimiser and a greedy dispatcher use the same cost function, the same shelters and the same shield as the multi-agent strategy. Benchmarks run over multiple paired seeds. |
| **Adversarial explorer** | A seeded, bounded search over failure combinations. It reports the worst cases it finds and opens any of them in the simulator. |
| **Event-sourced replay** | Any run can be rebuilt from scenario + seed + strategy + injected-event log, with hashes checked tick by tick. |
| **After-action report** | JSON and PDF export, including a strategy comparison on the same seed and the same events. |

## Quick start

Requirements: Python 3.11+ and Node 18+.

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.api.main:app --port 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. On Windows, `scripts/start.ps1` launches both. The app needs no paid APIs and no LLM.

### Tests and build

```bash
cd backend && python -m pytest tests -q -p no:asyncio
```

```bash
cd frontend && npx tsc -b && npx vite build
```

The suite has 102 tests: determinism, replay, rerouting, retreat on a closing edge, unreachable requests, double booking, stale state, expired reservations, capacity limits, boat failure, stranded passengers, shelter overflow, triple failure under all three strategies, contradictory and duplicate reports, delayed information, benchmarks, counterfactual sanity checks, policy-change renegotiation, the API, WebSocket resync and PDF export. It also covers message transport: loss, duplicate delivery, timeouts, lease expiry and partitions. Hypothesis property tests check the safety invariants under random failure sequences.

### Reproduce benchmarks

```bash
python scripts/run_benchmarks.py 10
```

This runs the optimisation-quality and failure-resilience suites, plus the noise and message-loss sweeps, over 10 paired seeds (about 1 min on 4 cores). It writes raw per-seed CSVs and `summary.json` to `data/evaluation/benchmarks/`, and the tables, with 95% bootstrap CIs, to `docs/benchmark_results.md`. The `/arena` page shows the same published results. See [docs/BENCHMARKS.md](docs/BENCHMARKS.md) for definitions and the honest reading.

## Pages

| Route | Page |
|---|---|
| `/command` | Live Command Center: map, incident queue, agent activity, inspector, KPIs, one-click chaos |
| `/dispatch` | Fleet & Dispatch: unit cards, manual directives (validated by the shield), assignment log |
| `/agents` | Negotiation Lab: message graph per round, full message trace, agent knowledge, policy changes |
| `/scenarios` | Scenario & Chaos Lab: scenario editor, presets, scheduled events, targeted injection, recovery tracking |
| `/decision-lab` | Counterfactual Decision Lab: fork, change, run both futures, synchronised maps, measured deltas |
| `/arena` | Strategy Arena: multi-seed paired benchmarks with mean ± sd and per-seed runs |
| `/replay` | Mission Replay & Audit: timeline scrubber, before/after diffs, event filters, replay verification |
| `/safety` | Safety Shield log and Adversarial Explorer |
| `/reports` | After-Action Report, JSON/PDF export, run comparison |

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): system design, data flow, API
- [docs/AGENTS.md](docs/AGENTS.md): agents, negotiation protocol, tie-breaking, information model
- [docs/SIMULATION.md](docs/SIMULATION.md): tick pipeline, flood model, reconciliation, safety, fairness, metrics
- [docs/BENCHMARKS.md](docs/BENCHMARKS.md): methodology and measured results
- [docs/MESSAGE_PASSING.md](docs/MESSAGE_PASSING.md): message-passing agents, network faults and their measured cost
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md): 5-minute judge demo

## Repository layout

```
resqnet/
  backend/app/
    simulation/   state, Riverbend world, flood model, report reconciliation, engine, serialisation
    routing/      NetworkX resource-specific routing + believed-network planning
    negotiation/  shared cost/commit machinery + decentralised protocol
    optimization/ centralised Hungarian + greedy baselines
    safety/       safety shield (commit + movement + invariant sweep)
    metrics/      metrics definitions
    analysis/     replay, counterfactual, benchmark, adversarial search
    persistence/  SQLite event-sourced store
    api/          FastAPI REST + WebSocket, report builder (JSON/PDF)
  backend/tests/
  frontend/src/   React + TS + Tailwind + Zustand + React Flow + Recharts
  docs/  scripts/
```
