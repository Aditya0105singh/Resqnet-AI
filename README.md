# resqnet — Multi-Agent Flood Rescue Coordination Digital Twin

**Code-E-Manipal 2.0 · PS 27 · Multi-Agent Systems / Logistics**
*Flood Rescue Dispatch Where Boats, Shelters and Roads Negotiate in Real Time*

> ⚠️ Research and educational simulation. Riverbend is a synthetic city, and the Aluva, Kerala map uses real OpenStreetMap roads; on both, all incidents, reports and floods are generated from a seed. This is **not** an operational emergency-dispatch system.

Most emergency dashboards show you where the crisis is. resqnet shows how autonomous rescue resources negotiate, recover and coordinate after the original rescue plan stops working, and it lets you check whether a different decision would have done better.

## What it does

| | |
|---|---|
| **Deterministic digital twin** | Tick-based engine (1 tick = 1 simulated minute). Riverbend has 56 nodes, 92 road/river/bridge/jetty edges, 5 neighbourhoods, 3 bridges, 3 shelters, 5 boats and 4 ground teams. The flood rises and closes roads as it goes. |
| **Message-passing agents** | A fourth strategy runs each agent as a separate handler that only reads its own inbox. Messages travel over a simulated network with latency, loss, duplicates and partitions, and are recovered by proposal timeouts, reservation leases and idempotent handlers. See [docs/MESSAGE_PASSING.md](docs/MESSAGE_PASSING.md). |
| **Real multi-agent negotiation** | Incident, rescue, shelter and route agents work through contract-net bidding and deferred acceptance (Gale–Shapley). The protocol runs REQUEST → BID → PROVISIONAL_ACCEPT → RESERVE → SAFETY → COMMIT. Every message is logged. |
| **Partial information** | Decentralised agents get broadcasts after a comms delay and plan on their own, possibly stale, view of the network. They find closures physically and can lose comms completely during a blackout. |
| **Safety shield** | An independent validator checks every commit and every move against the true world state. It enforces invariants S1–S7: double booking, shelter capacity, prohibited edges, transport capacity, stale versions, reservation validity and operational status. |
| **Rescue crew app** | `/crew/:unit` is a phone-first app for a unit's crew: accept, depart, arrived, boarded (with the crew's count), hand-over, plus "unsafe segment" and "cannot continue" escalations. Each tap is a validated, idempotent engine event. Updates queued without signal are reconciled on sync: a resent update is ignored, and one for a mission cancelled meanwhile is rejected with the reason. See [docs/CREW_APP.md](docs/CREW_APP.md). |
| **Mission Commander** | An **Ask** drawer answers dispatcher questions ("Why was I-004 reassigned?", "Which shelters can take 5 more people?", "What if B2 fails?") from the run's own records. Every claim is cited and every citation is checked. It can only *propose* actions, which a dispatcher must approve. It runs on offline rules by default, or on Claude with tools if opted in. See [docs/COMMANDER.md](docs/COMMANDER.md). |
| **Real-city pipeline** | `scripts/build_geo.py` turns an OpenStreetMap extract (a file, or a bounding box via Overpass) into a city file that any run can use. It produces roads simplified to junctions, OSM bridges, a resampled river with scenario-assumed jetties, named neighbourhoods, hypothetical shelters and a multilingual landmark gazetteer for SOS. Provenance is tagged per element and OSM attribution is shown on the map. **Aluva, Kerala** (central Aluva and the Periyar) ships built: pick it in New run. Riverbend stays the default. |
| **Citizen SOS intake** | `/sos` accepts free text in English, Hindi or Malayalam. Rules (or Claude, opt-in) extract only *evidence*. Urgency comes from a fixed rule, and location from a gazetteer that answers exact, ambiguous, area or none and never invents coordinates. Only a location the sender shared is auto-ingested; everything else goes to the dispatcher's approval queue. Prompt-injection text is flagged and treated as data. See [docs/SOS_INTAKE.md](docs/SOS_INTAKE.md). |
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

End-to-end browser tests (Playwright) start the backend and frontend themselves. They cover the guided demo, citizen SOS → dispatcher placement, offline crew reconciliation and the evidence page:

```bash
cd frontend && npm run e2e      # elsewhere first: npx playwright install chromium
```

The suite has 149 tests: determinism, replay, rerouting, retreat on a closing edge, unreachable requests, double booking, stale state, expired reservations, capacity limits, boat failure, stranded passengers, shelter overflow, triple failure under all three strategies, contradictory and duplicate reports, delayed information, benchmarks, counterfactual sanity checks, policy-change renegotiation, the API, WebSocket resync and PDF export. It also covers message transport: loss, duplicate delivery, timeouts, lease expiry and partitions. Hypothesis property tests check the safety invariants under random failure sequences.

### Reproduce benchmarks

```bash
python scripts/run_benchmarks.py 10
```

This runs the optimisation-quality and failure-resilience suites, plus the noise and message-loss sweeps, over 10 paired seeds (about 1 min on 4 cores). It writes raw per-seed CSVs and `summary.json` to `data/evaluation/benchmarks/`, and the tables, with 95% bootstrap CIs, to `docs/benchmark_results.md`. The `/arena` page shows the same published results. See [docs/BENCHMARKS.md](docs/BENCHMARKS.md) for definitions and the honest reading.

### Run as one container

```bash
docker compose up --build        # → http://localhost:8000 (app, API and WebSocket on one port)
```

The image builds the frontend and serves it from FastAPI. Runs are kept in a volume, so they survive restarts. Claude features stay off unless `RESQNET_SOS_LLM=on` / `RESQNET_COMMANDER_LLM=on` and `ANTHROPIC_API_KEY` are set. Without Docker, `cd frontend && npx vite build` and then starting the backend serves the built app on port 8000.

## Pages

| Route | Page |
|---|---|
| `/demo` | Guided demonstration: 8 live steps with the engine's actual results |
| `/research` | Evidence: PS 27 compliance, benchmarks, assumptions, data provenance (rendered from `docs/`) |
| `/command` | Live Command Center: map, incident queue, agent activity, inspector, approval queue, KPIs, one-click chaos |
| `/crew/:unit` | Rescue crew app (phone): mission, route, escalation, offline outbox |
| `/sos` | Citizen SOS (simulation): multilingual message, what the system understood, live status |
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
- [docs/CREW_APP.md](docs/CREW_APP.md): crew-driven missions, offline outbox and reconciliation
- [docs/COMMANDER.md](docs/COMMANDER.md): grounded question answering, citation checks, no-authority design
- [docs/SOS_INTAKE.md](docs/SOS_INTAKE.md): multilingual SOS pipeline, safety design and evaluation
- [docs/MESSAGE_PASSING.md](docs/MESSAGE_PASSING.md): message-passing agents, network faults and their measured cost
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md): 3- and 6-minute demo scripts
- [docs/ps27-compliance.md](docs/ps27-compliance.md): requirement → code → test evidence
- [docs/assumptions.md](docs/assumptions.md) · [docs/dataset-provenance.md](docs/dataset-provenance.md)

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
