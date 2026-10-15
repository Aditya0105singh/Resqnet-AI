# Modelling assumptions and limitations

RESQNET is a research and teaching simulation. Every number it produces is a modelled outcome under the assumptions below, not a prediction about a real flood.

## World

- **Riverbend is synthetic:** 56 nodes, 92 edges, 5 neighbourhoods, 3 bridges, 3 shelters. The geometry is fixed by seed 2026.
- **The flood model is simplified, not hydraulic.** Each neighbourhood's water level rises on a ramp towards a peak; node depth = level − synthetic elevation. Ground units can use a road while it is shallower than 0.35 m; boats can use a road once it is at least 0.5 m deep. A bridge closes to ground units when the river reaches its clearance.
- **Travel.** Boats move at 16 km/h and ground teams at 28 km/h.
  - Ground teams slow with water depth, to as little as 50% of speed at the 0.35 m limit.
  - Boats run at full speed on the river, 60% on flooded streets and 50% on jetties.
  - Route risk affects the dispatch cost, not travel time.
  - Loading takes 2 minutes and unloading 1 minute. One tick is one simulated minute.

## Information

- **Report reliabilities are heuristic metadata, not calibrated probabilities:** resident 0.6, sensor 0.75, responder 0.9. Confidence is noisy-OR over *independent sources*.
- **Forwards.** Verbatim forwards are detected by a content fingerprint. A paraphrased forward cannot be detected and counts as a new witness.
- **Decentralised agents** see incident publications and network closures `comm_delay` ticks late (1 by default, 3 in the conflicting-information scenario). They discover closures physically.
- **Message-passing agents.** Messages have independent loss, fixed latency per hop, optional duplication and clean partitions. Real radio networks have bursty, correlated loss.

## Coordination

- **Cost weights are proposed starting points, not trained values:** balanced C = 0.35T + 0.25R + 0.20U + 0.20F.
- **Coordinator outage.** Centralised and greedy dispatch have no standby coordinator. Peer communication and local safety stay available to the agent strategies. This favours decentralisation by construction in that one scenario, and the results say so.
- **Partitions** cut members off from incident agents, dispatch and other units. No strategy may commit across the split.
- **SOS urgency** comes from a fixed rule over extracted evidence (base 3, +1 per danger category; life-threatening = 5), not from a model.

## Human roles

- **Dispatcher actions** (approvals, placements, dispute verdicts) are modelled as instantaneous events.
- **Benchmarks run without a dispatcher.** A disputed incident therefore always waits the full 5/10-minute review window, which is an upper bound on that delay.
- **Crew actions** are events from the crew app. A crew-driven unit that is not acknowledged within 5 minutes loses the mission.

## Ground truth

- **People counts and incident existence live in a hidden truth table.** Agents never read it; it is revealed on scene.
- **A citizen SOS** from `/sos` creates a truth record with the stated head count, or 4 if none is stated. "We are safe" messages create none.

## Statistics

- **Paired seeds.** Results use 10 paired seeds and 95% percentile-bootstrap CIs (2,000 resamples, n ≥ 5). A difference is called significant only when its CI excludes zero. That is evidence, not proof.
- **Shared authorship.** The SOS evaluation set and the rule lexicons were written by the same author, so they are a regression guard, not an independent accuracy estimate.

## Not modelled

- Hydraulics: on the Kerala maps the roads, terrain and the 2018 river-discharge timing are real, but inundation depths come from a threshold model, not a hydraulic simulation (see [flood_validation.md](flood_validation.md) and [dataset-provenance.md](dataset-provenance.md)).
- Fuel or endurance limits.
- Multi-stop missions.
- Crew fatigue or shift changes.
- Weather and night operations.
- Medical triage beyond urgency.
- Communication between citizens and crews.
