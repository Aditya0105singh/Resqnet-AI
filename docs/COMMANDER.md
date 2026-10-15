# Mission Commander

The **Ask** button opens a drawer on every page. A dispatcher can ask questions in plain English and get answers built only from the current run's records, with every claim linked to the record it came from.

```
question ─▶ read-only snapshot of the engine (taken on the engine's thread)
             ─▶ tools: get_incident · get_unit · get_decision · list_open_incidents
                       list_shelters · get_metrics · what_if (counterfactual fork)
                       propose_action  ← the only write path: queues a proposal
             ─▶ answer with [ID] citations ─▶ citation check ─▶ proposals applied to
                                                                 the live approval queue
```

## Guarantees

| Guarantee | How it is enforced |
|---|---|
| **Grounded.** Answers come from the run's records. | Tools read a deep-copied snapshot (`Engine.read_snapshot`) of decisions, audit log, assignments, shelters and metrics. A question never reads the engine mid-tick. |
| **Checked citations.** | A citation is a record ID in square brackets: `[D-00012]`, `[AU-00031]`, `[EV-0001]`, `[I-004]`, `[A-007]`, `[B2]`, `[S1]`, `[PR-003]`. Each one is checked: an ID that does not exist, or that no tool returned for this question, is shown as a warning beside the answer, and an invalid chip is struck through. |
| **No authority.** | The only write tool is `propose_action`, which adds a proposal from `ai-commander` to the WP4 approval queue. The engine refuses approvals from any source starting with `ai`. Suggested actions are previewed on the snapshot, so the live run is untouched until a dispatcher approves. |
| **What-if is modelled, not predicted.** | `what_if` runs the existing counterfactual engine from the current tick with identical future events. Answers say "modelled outcome of the simulation". Incidents that exist only in the forked future are counted, not cited. |
| **Honest negatives.** | "Why was I-004 reassigned?" answers "It was **not** reassigned" when no commitment was cancelled. It then lists the disruptions and reroutes that actually touched the incident. |

## Two engines, same tools

- **Offline rules (default).** A deterministic question router handles the blueprint's questions with templated text. These include: why an incident was reassigned, which shelters can take N more people, what happens if a unit fails, which neighbourhoods wait longest, why a faster unit was rejected, where a unit is, overall status, and "send X to Y". Anything else gets a list of supported questions. It answers in about a millisecond, except what-if, which takes about 300 ms.
- **Claude (opt-in).** Set `RESQNET_COMMANDER_LLM=on`. It uses `claude-opus-5-5` in a capped manual tool-use loop (8 iterations) over the same tools. Tools use strict JSON schemas, there is no forced `tool_choice`, the response content is passed back unchanged so thinking blocks stay valid, and `fallbacks: "default"` is set. Tool results are passed as data, and the system prompt requires citations and says the model cannot act. Any API error or refusal falls back to the offline router, and the answer says so.

## API

`POST /api/simulations/{id}/ask {question}` returns:

```
{answer, citations[{id, kind, exists, from_tools}], tool_calls[{tool, input, ok}],
 engine, warnings[], queued_proposals[], tick, elapsed_ms}
```

## Tests

`backend/tests/test_commander.py` covers:

- every example question against a triple-failure run, with zero citation warnings;
- what-if leaving the snapshot untouched;
- action requests that only create proposals;
- the citation checker flagging invented and ungrounded IDs;
- the API refusing an AI approval;
- a mocked Claude tool-use loop: request shape, tool results returned together, an invented citation surfaced, and fallback on refusal.

The Claude path has not been run against the live API in this repository.

## Limitations

- **English questions only.** The router recognises a fixed set of question shapes.
- **Single turn.** Each question is answered on its own; there is no conversation memory.
- **What-if scope.** The what-if tool covers disabling units, adding boats and closing or opening edges. It does not cover policy or strategy changes; those are in the Decision Lab.
