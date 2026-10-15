# SOS extraction evaluation

Extractor: `rules` · 54 labelled synthetic messages (English, Hindi, Malayalam) in `data/evaluation/sos_cases.jsonl`.
Reproduce with `python scripts/eval_sos.py`. Messages are synthetic test cases written for this project, not real SOS data.

| field | result |
|---|---|
| head count | accuracy 0.974 on 38 messages that state one · **0 invented** where none was stated · by language {'en': 0.917, 'hi': 1.0, 'ml': 1.0} |
| special needs | precision 1.0 · recall 1.0 |
| urgency evidence | precision 0.973 · recall 1.0 |
| location status (exact / ambiguous / area / none) | accuracy 1.0 |
| location node (when a single landmark is named) | accuracy 1.0 on 37 · **0 invented** exact locations |
| claim (victims present / nobody there) | accuracy 1.0 |
| prompt injection | recall 1.0 on 4 · 0 false positives · 0 could bypass review |

## Remaining errors

| case | field | expected | got |
|---|---|---|---|
| en-01 | urgency_evidence | ['rising_water', 'trapped', 'upper_floor_or_roof'] | ['medical_emergency', 'rising_water', 'trapped', 'upper_floor_or_roof'] |
| en-11 | urgency_evidence | ['rising_water', 'trapped', 'upper_floor_or_roof'] | ['medical_emergency', 'rising_water', 'trapped', 'upper_floor_or_roof'] |
| en-16 | people_count | 4 | 3 |
