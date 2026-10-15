# Simulation

## Riverbend (synthetic)

- An 8 × 6 grid of land nodes, plus 8 river nodes on a meandering channel.
- Five neighbourhoods: Northbank, Hillcrest, Old Quarter, Riverside (lowest), Eastmere.
- Edge kinds: `road` (ground units; boats once flooded deeper than 0.5 m), `bridge` (ground units only; closes when the river reaches its clearance), `river` and `jetty` (boats only).
- Bridges: Mill (BR1, clearance 3.3 m), Central (BR2, 4.2 m), Eastgate (BR3, 3.0 m).
- Shelters sit on raised ground with jetties: S1 Northbank Community School (45), S2 Riverside Civic Arena (60), S3 Hillcrest Sports Hall (40).
- The geometry is fixed (seed 2026), so every run uses the same stable IDs. The scenario seed only changes incidents and reports.

## Tick pipeline (`simulation/engine.py`)

1 scheduled events → 2 flood & graph update → 3–4 report ingest & reconciliation → 5 reservation maintenance → 6 invalidation (retreat, reroute, shelter renegotiation, cancel) → 7–9 negotiation round, shield, atomic commit → 10 movement with the per-edge safety gate → 11 pickup, unload, outcomes → 12 metrics → 13 invariant sweep and recovery tracking → 14 frame and state hash.

User events are applied between ticks, followed by steps 6–9 as a micro-step.

## Flood model (`simulation/flood.py`): simplified, not hydraulic

`level_n(t) = 1.2 + severity · 2.2 · ramp(t) · factor_n + surge_offset`, with `ramp(t) = min(1, 0.35 + 0.65 t / peak)`.

Node depth is `level − elevation`, and edge depth is the mean of its two endpoints. Thresholds:

- Ground units can use an edge while depth < 0.35 m. Their speed falls up to 50% as depth rises.
- Boats can use a street once its depth is ≥ 0.5 m.
- A bridge closes when `river_level ≥ clearance`.
- Edge risk is derived from how close the depth is to the threshold, plus bridge stress.

## Movement and routing

- Each unit gets one minute of travel per tick, interpolated along edges.
- Before a unit enters any edge, the movement gate checks it against the true graph.
- If an edge closes under a unit, the unit turns back. This is the only sanctioned movement on a prohibited edge, and any other such movement is counted as a route violation.
- Units never teleport. Reassignment starts from the unit's current position, including mid-edge, choosing between continuing forward and retreating.

## SOS reports and uncertainty (`simulation/reports.py`)

- Reports come from three sources with reliability metadata: resident 0.6, sensor 0.75, responder 0.9. A report may be noisy, missing fields, delayed, duplicated, contradictory, or a false alarm.
- **Matching:** a report is merged into an existing incident if it falls within max(location uncertainty) + 50 m and arrives within 45 minutes.
- **Confidence (heuristic, uncalibrated):** cp = 1 − Π(1 − r) over PRESENT reports. cn is computed the same way over NO_VICTIMS reports. confidence = cp, or cp²/(cp + cn) when the reports contradict.
- **Status:** VERIFIED at ≥ 0.8, SUSPECTED at ≥ 0.5, otherwise UNVERIFIED. An incident becomes FALSE_ALARM when cn ≥ 0.85 and cn > cp + 0.2, or when a unit on scene finds nobody.
- **Conservative merge:** people = maximum reported (assume 4 if missing), urgency = maximum (assume 3), location = most reliable and most precise report.
- **Dispatch rules:** E1 verified. E2 suspected → provisional. E3 unverified but urgency ≥ 4 → provisional (life safety). E4 unverified for 20+ minutes → verification visit. All provisional dispatches still pass the shield.
- **On scene** the true count is revealed. If there are more people than capacity, the incident stays open for the remainder. If the count is lower, other commitments are cancelled. If nobody is there, the incident is marked a confirmed false alarm. If a loaded unit fails, its passengers become a new urgency-5 incident.

## Safety invariants (`safety/shield.py`)

S1 no double booking · S2 shelter capacity (occupancy + reserved ≤ capacity) · S3 no prohibited edge (commit and movement) · S4 load ≤ transport capacity · S5 no commit from stale resource or incident versions · S6 reservation active, unexpired and bound to the commitment · S7 the unit is operational and connected.

These are checked at commit time, at every edge entry, and in a global sweep every tick. A shelter whose capacity drops revokes reservations most-recent-first until S2 holds again. Affected units renegotiate another shelter, or HOLD if they are already loaded and nowhere has room.

## Fairness

- Neighbourhood wait: time-to-service for served incidents, and current wait for unserved ones.
- **Jain index** J = (Σx)² / (n Σx²) over neighbourhood mean waits. J = 1 means every neighbourhood waits equally.
- In the cost function, F = 1 − W_n / W_max. Requests from the most-starved neighbourhood therefore cost less, which counteracts repeated starvation. Neighbourhood priority weights shift F.

## Metrics (`metrics/metrics.py`)

| Metric | Definition |
|---|---|
| Time to service | First pickup minus first report |
| Deadline misses | Urgency ≥ 4 incidents first picked up after their deadline (30 min for urgency 5, 45 min for urgency 4), or still waiting past it |
| Unmet people | Real people not yet delivered to a shelter, including people in transit and people wrongly dismissed as false alarms |
| Idle with demand | Unit-ticks spent IDLE while any eligible request was uncovered |
| Route violations | Movement on a prohibited edge, excluding sanctioned retreats |
| Recovery time | Ticks from a disruption until every affected request is covered again and no affected unit is HOLDING |

## Known limitations

- The flood model is a simplified threshold model. Shelters and the geography are synthetic.
- Confidence scores are heuristics, not probabilities.
- Agents bid only while idle. There is no pre-emption of committed units unless an operator requests reassignment or a policy change forces renegotiation.
- One resource serves one incident at a time. Large incidents are handled by several units or several trips.
- Benchmarks are bounded to a handful of seeds and scenarios. The adversarial search is a sampled search, not formal verification.
