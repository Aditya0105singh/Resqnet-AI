# Citizen SOS intake

The `/sos` page and `POST /api/simulations/{id}/sos` turn a free-text message in English, Hindi or Malayalam into a rescue request. The pipeline does not invent a location, and it never lets the message text change the system's behaviour.

> **Simulation only.** The page states clearly that it is not an emergency service and points to 112. All test messages are synthetic.

## Pipeline

```
text ─▶ extractor (evidence only) ─▶ deterministic post-processing ─▶ route
          rules (default)              urgency = fixed rule on evidence     shared location + nothing to review
          or Claude (opt-in)           location = gazetteer, never a model     ─▶ SOS_REPORT (fusion)
                                       review reasons                       otherwise
                                                                               ─▶ PROPOSE_ACTION(SOS_REPORT)
                                                                                  dispatcher places / approves
```

| Stage | Files | What it does |
|---|---|---|
| Schema | `backend/app/intelligence/schema.py` | Defines what an extractor may report: language, head count, special needs, urgency evidence, location *text*, "nobody here" claim, contains-instructions flag. There is no coordinates field and no urgency field: an extractor cannot set either. |
| Rules | `backend/app/intelligence/extract.py` (`RuleExtractor`) | Multilingual lexicons and number words (English, Hindi, Malayalam). Text is NFC-normalised and native digits are converted. Malayalam inflection is handled by stem matching (ടെറസ് → ടെറസിൽ, ക്ഷേത്രം → ക്ഷേത്രത്തിന്റെ, chillu letters). Deterministic and offline. |
| Claude (opt-in) | `LLMExtractor` | Enabled with `RESQNET_SOS_LLM=on`. Model `claude-opus-5-5` with JSON-schema structured output (`output_config.format`), low effort, and `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`) so a refusal is rescued server-side. The SOS text is HTML-escaped inside `<sos_message>` tags, and the system prompt says never to follow instructions inside it. |
| Cross-check | `finalize()` | When Claude is used, the rule extractor still runs. Safety flags (injection, "nobody here") are OR-combined, and a head-count disagreement goes to human review. Any API error, refusal or schema failure falls back to rules, and the extractor name records why. |
| Urgency | `urgency_from()` | A fixed rule: base 3, +1 each for rising water, trapped or upper floor, medical, and a vulnerable person; life-threatening evidence gives 5; "nobody here" gives 1. |
| Location | `backend/app/intelligence/geocode.py`, `data/geographic/riverbend_gazetteer.json` | Synthetic Riverbend landmarks with English, Hindi and Malayalam aliases. Returns `exact`, `ambiguous` (a bridge has two banks; "പള്ളി" is a church or a mosque), `area` or `none`. Only `exact` carries a node, and even then it is labelled **inferred**. |
| Routing | `api/main.py` (`submit_sos`) | **Auto-ingest only** when the sender shared a location and nothing needs review. Everything else becomes an `SOS_REPORT` proposal in the approval queue (WP4), and the dispatcher places it on the map and approves. Injection-flagged messages are always queued, even with a shared location. |
| Fusion | `SOS_REPORT` event | Enters fusion as a resident report (reliability 0.6). The engine computes the content fingerprint from the text, so verbatim forwards ("Fwd: …") count as one source (WP3). |
| Status | `GET /api/simulations/{id}/sos/{receipt}` | The receipt is the message fingerprint. Stages: awaiting dispatcher → received → help assigned (unit and ETA) → rescued. |

The location is labelled as one of:

- **observed** (shared by the sender);
- **inferred** (a landmark in the text);
- **unverified** (ambiguous, area-only or unknown).

## Evaluation

`python scripts/eval_sos.py` runs the extractor over `data/evaluation/sos_cases.jsonl`: 54 labelled synthetic messages, 18 per language. They include head counts, needs, danger signs, exact, ambiguous, area-only and unknown locations, verbatim forwards, "we are safe" contradictions and prompt-injection attempts. Results are written to [`data/evaluation/sos_results.md`](../data/evaluation/sos_results.md).

Current rule-extractor results:

| Field | Result |
|---|---|
| Head count | 0.97 accuracy where a count is stated; **0 invented** where none is stated |
| Special needs | precision 1.0, recall 1.0 |
| Urgency evidence | precision 0.97, recall 1.0 |
| Location status | 1.0; **0 invented exact locations** |
| "Nobody here" claim | 1.0 |
| Prompt injection | 4/4 detected, 0 false positives, **0 could bypass review** |

**Read these numbers with care.** The lexicons and the test messages were written by the same author, in the same session, so this is a regression guard and not an independent accuracy estimate. A held-out set written by native speakers who have not seen the rules is the honest next step. The three remaining errors are kept rather than tuned away:

- "needs insulin" is treated as a medical emergency (2 cases);
- "three kids and our grandma" is counted as 3 instead of 4.

The CI test (`tests/test_sos.py`) enforces the hard properties: no invented counts, no invented exact locations, every injection caught and none auto-ingested. It also enforces quality floors.

The Claude path is tested with a mocked HTTP transport (no key, no network). The tests check the request shape, delimiter escaping, OR-combined safety flags, head-count disagreement, and fallback to rules on a refusal or a 500 error. It has **not** been evaluated against the live model in this repository. Run `RESQNET_SOS_LLM=on python scripts/eval_sos.py --llm` with API credentials to do so.

## Limitations

- The gazetteer is synthetic and small: 11 landmarks, 3 bridges, 5 neighbourhoods. Real geography is WP5.
- There is no audio transcription and no SMS/WhatsApp adapter. Text input only.
- Romanised Hindi or Malayalam ("bachao", "vellam") is not covered by the rule lexicons.
- Simulated ground truth for a citizen SOS assumes the stated people exist. 4 are assumed when no count is given.
