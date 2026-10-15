# resqnet — Multi-Agent Flood Rescue Coordination Digital Twin

**Code-E-Manipal 2.0 · PS 27 · Multi-Agent Systems / Logistics**
*Flood Rescue Dispatch Where Boats, Shelters and Roads Negotiate in Real Time*

> ⚠️ Research and educational simulation. Riverbend is a synthetic city; the Kerala maps use real OpenStreetMap roads and Copernicus terrain, and the 2018 scenario replays the real river discharge. On every map the incidents, reports and inundation depths are simulated. This is **not** an operational emergency-dispatch system.

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
| **Real-city pipeline** | `scripts/build_geo.py` turns an OpenStreetMap extract (a file, or a bounding box via Overpass) into a city file that any run can use. It produces roads simplified to junctions, OSM bridges, a resampled river with scenario-assumed jetties, named neighbourhoods, hypothetical shelters and a multilingual landmark gazetteer for SOS. Provenance is tagged per element and OSM attribution is shown on the map. The app and the guided demo open on the richer Kerala snapshot of Aluva (below). Its OSM extract of central Aluva (`data/geographic/sources/aluva.osm`) is also the source of the named places and Hindi/Malayalam aliases that SOS uses on the Kerala snapshot (`scripts/build_landmarks.py`). |
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

### Put it online (Render)

The app is one container, so any host that runs a Docker container works. `render.yaml` is a ready blueprint for [Render](https://render.com): sign in with GitHub, choose **New → Blueprint**, pick this repository and apply. The first build takes several minutes; the site is then at `https://resqnet-ai.onrender.com` (or the name you give it). The free plan sleeps after about 15 minutes idle and takes up to a minute to wake, so open it a few minutes before a demo, or use the *starter* plan for always-on. Runs are kept in a SQLite file that resets on each deploy on the free plan.

**Website on Vercel, server on Render (optional).** Vercel can host the website only; the server must stay on Render. Import the repository as a single project with **Root Directory `frontend`**, framework Vite, and set one environment variable, `VITE_BACKEND_URL` = your Render address (no trailing slash, e.g. `https://resqnet-ai.onrender.com`). `frontend/vercel.json` handles the page routes. The website then calls the Render server for everything, including the WebSocket. Leave it unset for the single-container build, where the page and the server share one address. Do not use Vercel's "Services" preset or its backend import: simulations live in server memory and stream over a WebSocket, which Vercel's serverless functions do not support.

## Real maps (Kerala)

Besides the synthetic Riverbend grid, the simulator runs on real geography: OpenStreetMap roads, bridges and rivers plus the 30 m Copernicus DEM (GLO-30) for terrain. Two snapshots ship in `backend/app/data/maps/`: **Aluva · Periyar River** and **Chengannur · Pamba River**. Pick one under *New run → Map*. The app opens on Aluva; Riverbend is used by the tests and benchmarks.

Snapshots are committed JSON, so runs are deterministic and work offline. To rebuild or add an area (needs network access):

```bash
python scripts/build_map.py aluva        # areas are defined at the top of the script
```

The builder simplifies the road graph, samples the river channel, ranks bridges by criticality, picks shelters near people and water, and scales elevation into the simulator's water-level frame. Incidents are weighted by building density. Flood depths remain simulated.

### Kerala 2018 flood replay

The **Kerala 2018 · real flood replay** scenario drives the river level from the real August 2018 river-discharge curve (GloFAS reanalysis) and shapes SOS arrivals with real rainfall (IMD gauge-based daily totals, hourly shape from ERA5), time-compressed onto 180 ticks. Data comes from the free Open-Meteo APIs and is stored as committed snapshots in `backend/app/data/events/`:

```bash
python scripts/build_flood_event.py kerala_aluva
```

Discharge and rainfall are real; inundation depths are still produced by the simulator's threshold model, so this is a replay of the flood's timing and intensity, not a reconstruction of observed flood extent. `scripts/validate_flood.py` compares the modelled flood footprint with a Sentinel-1 water mask from 21 Aug 2018; results and caveats are in `docs/flood_validation.md`.

### Demo

**Judge Mode** (`/judge`) tells the Aluva 2018 flood in five chapters, and each chapter drives the live engine:

1. The map opens on 14 Aug.
2. The river rises (15 Aug).
3. Three failures hit at the flood peak (16 Aug).
4. A decision record explains why the agents chose that plan.
5. The final count (17 Aug).

The camera flies to each failure. The run is seeded, so it ends the same way every time.

**Offline:** a service worker keeps every map tile and font the browser has loaded, so do one full rehearsal on wifi and the demo then works without a connection. It never bulk-downloads tiles, which the OpenStreetMap tile policy forbids. Views you have not opened before stay blank when offline. The backend runs locally and needs no internet.

## Pages

The top menu has **Live console**, **Citizen SOS** and **Crew app**, plus two dropdowns, **Labs** and **Results**. **Watch demo** sits on the right. On phones the menu collapses into a hamburger.

| Route | Menu | Page |
|---|---|---|
| `/` | Home | Product overview: the problem, how it works, measured results, links to everything |
| `/demo` | Watch demo | Guided demonstration: 8 live steps with the engine's actual results |
| `/command` | Live console | Map, rescue requests, activity, details, approvals, key numbers, "Simulate failure" menu, "New run" dialog |
| `/sos` | Citizen SOS | Multilingual SOS (simulation): what the system understood, live status |
| `/crew/:unit` | Crew app | Phone app for a rescue crew: mission, route, escalation, offline outbox |
| `/chaos` | Labs | Scenario & failure lab: scenario editor, presets, scheduled events, live failures, recovery tracking |
| `/judge` | Labs | Judge Mode: the Aluva August 2018 flood in five chapters on the real map, camera following each failure |
| `/decision-lab` | Labs | What-if lab: fork, change one decision, run both futures, measured differences |
| `/agents` | Labs | Agent negotiation: message graph per round, full message trace, agent knowledge |
| `/dispatch` | Labs | Rescue fleet: unit cards, manual orders (safety-checked), mission log |
| `/arena` | Results | Benchmarks: published paired results with 95% CIs, or run your own |
| `/safety` | Results | Safety tests: the seven rules, blocked actions, stress-test search |
| `/audit` | Results | Mission replay: timeline scrubber, diffs, event filters, replay verification |
| `/reports` | Results | After-action report, JSON/PDF export, strategy comparison |
| `/research` | Results | Evidence: PS 27 compliance, benchmarks, assumptions, data provenance (rendered from `docs/`) |

Old addresses redirect: `/scenarios` → `/chaos`, `/replay` → `/audit`. `/judge` is Judge Mode, the five-chapter 2018 story (under Labs).

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
