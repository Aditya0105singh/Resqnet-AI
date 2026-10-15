# PS 27 compliance and build checklist

Each requirement is mapped to the code that implements it and the tests that prove it. Status: **✅ done**, **🟡 partial**, **❌ not done**. This page is rendered in the app at `/research`.

## Official PS 27 requirements

| Requirement | Status | Implementation | Evidence (tests) |
|---|---|---|---|
| Dynamic road and water replanning | ✅ | `simulation/flood.py`, `engine._replan`, `_retreat_from_closed_edges`, `routing/router.py` | `test_closed_bridge_forces_reroute_or_cancel`, `test_unit_on_closing_edge_retreats_without_violation`, `test_ground_units_never_use_water_edges_and_boats_never_use_dry_roads` |
| Autonomous agents with partial information | ✅ | `negotiation/decentralized.py` (delayed beliefs), `negotiation/message_passing.py` (independent agents over a lossy network) | `test_decentralized_agents_use_delayed_information`, `test_every_commit_follows_a_reservation_grant_for_that_proposal`, `test_lost_messages_recovered_by_timeouts_and_leases` |
| Resource contention and capacity limits | ✅ | Deferred acceptance; shelter reservations and leases | `test_no_double_booking_ever`, `test_shelter_capacity_never_exceeded_by_reservations`, `test_duplicate_delivery_never_double_reserves`, `test_resource_capacity_respected` |
| Fairness | ✅ | F term in the cost, Jain index, neighbourhood priority policy | `test_metrics_consistency`, published `fairness_jain` with CIs |
| Explicit safety invariants | ✅ | `safety/shield.py` S1–S7 (commit, movement gate, per-tick sweep) | `test_shield_rejects_stale_state_double_booking_and_capacity`, `test_shield_rejects_expired_reservation`, `test_property_safety_invariants_hold_under_random_failures` (Hypothesis, including partitions, loss and duplication) |
| Centralised vs decentralised comparison | ✅ | Hungarian and greedy baselines; paired 10-seed suites with bootstrap CIs | `test_benchmark_is_paired_and_reports_variability`, `test_paired_difference_flags_only_consistent_differences`; [BENCHMARKS.md](BENCHMARKS.md) |
| Recovery from contradictory updates | ✅ | Independent-source fusion, DISPUTED abstain state, dispatcher resolution | `test_contradictory_reports_create_false_alarm_and_cancel`, `test_credible_conflict_abstains_then_verifies`, `test_forwarded_copies_count_once` |
| Simultaneous triple failure | ✅ | `engine._ev_triple_failure` picks its targets from live state | `test_triple_failure_mid_run`, `test_contradictory_scenario_runs_safely_all_strategies` |
| Time-stepped simulation, assignment log, replay | ✅ | Tick engine, SQLite event store, per-tick state hashes | `test_replay_reproduces_history_with_injected_events`, `test_replayed_frames_match_recorded_state`, and replay tests for crew, SOS, proposal and partition events |

## Build checklist (from the 2.0 blueprint)

| Item | Status | Notes |
|---|---|---|
| Real geography with source labelling | ✅ | Real **Aluva (Periyar)** and **Chengannur (Pamba)** maps: OpenStreetMap roads, bridges and rivers, Copernicus 30 m terrain, relief-camp shelters; the app opens on Aluva. A **Kerala 2018 flood replay** scenario drives the river from the real GloFAS discharge and shapes SOS arrivals with real rainfall; the flood model is checked against Sentinel-1 ([flood_validation.md](flood_validation.md): useful on Chengannur, weak on Aluva). Inundation depths, units, incidents and shelter capacities remain simulated or assumed. Sources and terms: [dataset-provenance.md](dataset-provenance.md). Every scenario × approach on both maps finishes with 0 violations (104 runs). Tests: `test_maps.py`, `test_sos_real_maps.py`. |
| Multilingual SOS extraction and verification | ✅ | English, Hindi, Malayalam; never invents a location; 54-case eval. [SOS_INTAKE.md](SOS_INTAKE.md) |
| Dispatcher approval and override | ✅ | Approval queue with side-effect-free previews; manual directives; dispute resolution |
| Crew mobile mission lifecycle | ✅ | `/crew/:unit`, validated idempotent crew events, offline outbox (no service worker). [CREW_APP.md](CREW_APP.md) |
| Live backend-driven map and event stream | ✅ | WebSocket frames, resync on sequence gaps |
| Decision inspector and counterfactual forks | ✅ | Decision Lab; `what_if` in the Mission Commander |
| Atomic reservations and no double booking | ✅ | Shield S1/S2/S6; leases; property test |
| Reproducible benchmarks with raw results | ✅ | `scripts/run_benchmarks.py` → CSVs + `summary.json` |
| Fault-tolerance claims backed by tests | ✅ | Partition, loss, duplication, coordinator outage, triple failure |
| Safety property tests | ✅ | Hypothesis over 4 strategies with failures, partitions, loss (300-example stress run passed) |
| AI output grounded in authoritative state | ✅ | Commander citations checked against records; SOS extractor reports evidence only |
| Dataset provenance and documented limitations | ✅ | [dataset-provenance.md](dataset-provenance.md), [assumptions.md](assumptions.md) |
| Guided judge demonstration | ✅ | `/demo` runs every step live and shows the real result |
| End-to-end browser test | ✅ | `frontend/e2e/demo.spec.ts` (Playwright): SOS → approval → negotiation → triple failure → crew → commander |
| Deployed application | ❌ | Not deployed from this environment |
| Recorded backup demonstration | ❌ | Not recorded |
| Claude paths evaluated on the live API | 🟡 | SOS extraction and the commander are tested with a mocked transport only |
