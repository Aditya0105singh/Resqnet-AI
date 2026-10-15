# Architecture

```
 React UI (Vite, Zustand)                     FastAPI backend (authoritative)
 ┌───────────────────────────┐   REST    ┌──────────────────────────────────────────┐
 │ pages: command, dispatch, │ ───────▶  │ api/main.py  sessions · jobs · reports    │
 │ agents, chaos, decision   │           │   │                                       │
 │ lab, arena, replay, safety│ ◀──────── │   ▼                                       │
 │ reports                   │ WebSocket │ simulation/engine.py  (tick pipeline)     │
 │                           │  frames + │   ├─ flood.py        synthetic flood      │
 │ store/sim.ts  (selection, │  audit +  │   ├─ reports.py      SOS reconciliation   │
 │   synced frame, feed)     │  rounds   │   ├─ negotiation/    decentralised + cost │
 │ hooks/useSimSocket.ts     │           │   ├─ optimization/   centralised, greedy  │
 │  (reconnect + resync)     │           │   ├─ routing/        NetworkX Dijkstra    │
 └───────────────────────────┘           │   ├─ safety/         shield               │
                                         │   └─ metrics/        metrics              │
                                         │ analysis/  replay · fork · bench · adv.   │
                                         │ persistence/  SQLite (event-sourced)      │
                                         └──────────────────────────────────────────┘
```

## Principles

1. **One authoritative state.** The `Engine` owns `WorldState`. The UI never invents outcomes: it renders frames and sends events. A failed request shows a toast, never a fake animation.
2. **Everything is an event.** User actions such as closing a road, disabling a unit, a manual directive or a policy change are validated events, applied between ticks and logged as `(tick, seq, type, params)`. Together with the scenario config, seed and strategy, that log is enough to reproduce a run exactly.
3. **Same rules for every strategy.** All three strategies share the cost function (`negotiation/common.py`), the shelter agents (`request_reservation`) and the commit path (`try_commit` → shield). Only the information model and the conflict-resolution mechanism differ.
4. **Determinism.** All randomness is seeded. Iteration order is always sorted by ID. A state hash is recorded every tick, and `analysis.verify_replay` rebuilds the run and compares hashes tick by tick.

## Data model (`simulation/state.py`)

The entities are `WorldState`, `GraphNode`, `GraphEdge`, `Neighbourhood`, `IncidentReport`, `Incident`, `RescueResource`, `Shelter`, `CapacityReservation`, `Assignment`, `SimulationEvent` and `AuditRecord`, plus `NegotiationRound`, `Message` and `Candidate` in `negotiation/common.py` and decision records (dicts) in the engine. Every mutable entity carries a `version` that is bumped on each transition. Statuses are explicit string enums: `ResourceStatus`, `IncidentStatus`, `AssignmentStatus` and `ReservationStatus`.

Ground truth (true people counts, whether an incident exists at all) lives in `world.truth`. Agents never read it. It is revealed physically when a unit arrives on scene.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health`, `/api/scenarios`, `/api/world` | meta, presets, static geometry |
| POST | `/api/simulations` | create `{scenario, strategy, seed?, overrides}` |
| GET | `/api/simulations[/{id}]` | list / summary + current frame |
| POST | `/api/simulations/{id}/start · pause · step · reset · speed` | playback |
| POST/GET | `/api/simulations/{id}/events` | inject validated event / list events |
| GET | `/api/simulations/{id}/crew/{unit}` | crew app view: mission, route with blocked segments, valid actions. Crew actions go through `/events` as `CREW_UPDATE` |
| POST | `/api/simulations/{id}/ask` | Mission Commander `{question}` → grounded answer, checked citations, queued proposals |
| POST | `/api/simulations/{id}/sos` | citizen SOS `{text, shared_node?, people?, needs[]}` → extraction + ingested or queued |
| GET | `/api/simulations/{id}/sos/{receipt}` | sender status by message fingerprint |
| GET | `/api/simulations/{id}/proposals[?status=pending]` | approval queue. Create, approve and reject through `/events` with `PROPOSE_ACTION` / `APPROVE_PROPOSAL` / `REJECT_PROPOSAL` |
| GET | `/api/simulations/{id}/agents · assignments · negotiations[/{round}] · decisions[/{id}] · metrics · audit · safety · frames` | views |
| GET | `/api/simulations/{id}/replay/verify` | rebuild from event log and compare hashes |
| POST | `/api/simulations/{id}/fork` | counterfactual `{tick, modifications, horizon?}` |
| POST/GET | `/api/benchmarks[/{job}]` | seeded multi-strategy benchmark job |
| POST/GET | `/api/adversarial[/{job}]` | bounded worst-case search job |
| GET | `/api/reports/{id}?format=json\|pdf` | after-action report |
| WS | `/ws/simulations/{id}` | `hello` (full) → `frame`/`event`/`status` deltas with `seq`, `state_version`, `event_id`; client `resync`/`ping` |

Errors are structured as `{"error": {"code", "message"}}`. Inputs are validated by Pydantic and then by the engine: unknown IDs, out-of-range capacities and infeasible directives all return `422 EVENT_REJECTED` with the reason.

## Persistence

`persistence/store.py` stores each run as config + strategy + injected-event log + tick in SQLite. After a restart, `GET /api/simulations/{id}` rebuilds the run by replaying that log. Benchmark and adversarial results are stored as jobs.

## Frontend

- `store/sim.ts` holds the synced frame, the audit feed, the negotiation rounds, the current selection, layer toggles and toasts. It dedupes by record ID.
- `hooks/useSimSocket.ts` reconnects with exponential backoff and requests a full `resync` whenever it detects a sequence gap.
- `components/CityMap.tsx` is a custom SVG GIS view. It shows flood depth, closures, flooded roads that boats can navigate, routes, shelters with capacity and reservation bars, incidents styled by urgency, provisional state and confidence, and units. It supports zoom and pan, close-road mode and add-SOS mode. Unit movement is interpolated with CSS transitions between the positions the backend provides.
- `components/DecisionInspector.tsx` is an investigation-style drawer modelled on the neatlogs "investigation report" layout: Outcome, Evidence and reasoning, Candidate bids, Verification, What would change.
