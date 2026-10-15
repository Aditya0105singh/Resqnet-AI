"""Evaluate SOS extraction on the labelled synthetic set.

    python scripts/eval_sos.py            # rule extractor (deterministic, offline)
    RESQNET_SOS_LLM=on python scripts/eval_sos.py --llm   # Claude extractor (needs API credentials)

Writes data/evaluation/sos_results.md and prints a summary. Metrics:
  people_count  exact-match accuracy over cases that state a count; "invented" counts
                cases with no stated count where the extractor produced one
  needs / evidence  micro precision / recall over the label sets
  location      geocode status accuracy; exact-node accuracy; "invented" counts
                cases labelled none/area/ambiguous that came back as an exact node
  claim, injection  accuracy; injection recall and false-positive count
"""
import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.intelligence.extract import LLMExtractor, analyse  # noqa: E402
from app.intelligence.geocode import Gazetteer  # noqa: E402
from app.simulation.scenarios import get_preset  # noqa: E402
from app.simulation.world import build_world  # noqa: E402


def load_cases(path=os.path.join(ROOT, "data", "evaluation", "sos_cases.jsonl")):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def evaluate(cases, llm=None):
    gaz = Gazetteer.for_world(build_world(get_preset("normal"), "eval"))
    rows = []
    for c in cases:
        r = analyse(c["text"], gaz, llm=llm)
        rows.append((c, r))
    m = {"n": len(rows)}

    def pr(field_exp, field_got):
        tp = fp = fn = 0
        for c, r in rows:
            e, g = set(c["expected"][field_exp]), set(getattr(r, field_got))
            tp += len(e & g)
            fp += len(g - e)
            fn += len(e - g)
        return {"precision": round(tp / (tp + fp), 3) if tp + fp else 1.0, "recall": round(tp / (tp + fn), 3) if tp + fn else 1.0, "fp": fp, "fn": fn}

    stated = [(c, r) for c, r in rows if c["expected"]["people_count"] is not None]
    m["people_count"] = {"accuracy": round(sum(r.people_count == c["expected"]["people_count"] for c, r in stated) / len(stated), 3), "n": len(stated),
                         "invented": sum(1 for c, r in rows if c["expected"]["people_count"] is None and r.people_count is not None)}
    m["special_needs"] = pr("special_needs", "special_needs")
    m["urgency_evidence"] = pr("urgency_evidence", "urgency_evidence")
    m["location_status"] = {"accuracy": round(sum(r.location.status == c["expected"]["location_status"] for c, r in rows) / len(rows), 3)}
    exact = [(c, r) for c, r in rows if c["expected"]["location_status"] == "exact"]
    m["location_node"] = {"accuracy": round(sum(r.location.node == c["expected"]["node"] for c, r in exact) / len(exact), 3), "n": len(exact),
                          "invented": sum(1 for c, r in rows if c["expected"]["location_status"] != "exact" and r.location.status == "exact")}
    m["claim"] = {"accuracy": round(sum(r.claim == c["expected"]["claim"] for c, r in rows) / len(rows), 3)}
    inj = [(c, r) for c, r in rows if c["expected"]["contains_instructions"]]
    m["injection"] = {"recall": round(sum(r.contains_instructions for c, r in inj) / len(inj), 3), "n": len(inj),
                      "false_positives": sum(1 for c, r in rows if not c["expected"]["contains_instructions"] and r.contains_instructions),
                      "auto_ingest_possible": sum(1 for c, r in inj if not r.requires_human_review)}
    by_lang = {}
    for lang in ("en", "hi", "ml"):
        sub = [(c, r) for c, r in stated if c["lang"] == lang]
        by_lang[lang] = round(sum(r.people_count == c["expected"]["people_count"] for c, r in sub) / len(sub), 3) if sub else None
    m["people_count_by_language"] = by_lang
    m["errors"] = [
        {"id": c["id"], "field": f, "expected": e, "got": g}
        for c, r in rows
        for f, e, g in (
            ("people_count", c["expected"]["people_count"], r.people_count),
            ("special_needs", c["expected"]["special_needs"], sorted(r.special_needs)),
            ("urgency_evidence", c["expected"]["urgency_evidence"], sorted(r.urgency_evidence)),
            ("location", (c["expected"]["location_status"], c["expected"]["node"]), (r.location.status, r.location.node)),
            ("claim", c["expected"]["claim"], r.claim),
            ("injection", c["expected"]["contains_instructions"], r.contains_instructions),
        )
        if (list(e) if isinstance(e, tuple) else e) != (list(g) if isinstance(g, tuple) else g)
    ]
    m["extractor"] = rows[0][1].extractor if rows else ""
    return m


def to_markdown(m):
    out = [
        "# SOS extraction evaluation",
        "",
        f"Extractor: `{m['extractor']}` · {m['n']} labelled synthetic messages (English, Hindi, Malayalam) in `data/evaluation/sos_cases.jsonl`.",
        "Reproduce with `python scripts/eval_sos.py`. Messages are synthetic test cases written for this project, not real SOS data.",
        "",
        "| field | result |",
        "|---|---|",
        f"| head count | accuracy {m['people_count']['accuracy']} on {m['people_count']['n']} messages that state one · **{m['people_count']['invented']} invented** where none was stated · by language {m['people_count_by_language']} |",
        f"| special needs | precision {m['special_needs']['precision']} · recall {m['special_needs']['recall']} |",
        f"| urgency evidence | precision {m['urgency_evidence']['precision']} · recall {m['urgency_evidence']['recall']} |",
        f"| location status (exact / ambiguous / area / none) | accuracy {m['location_status']['accuracy']} |",
        f"| location node (when a single landmark is named) | accuracy {m['location_node']['accuracy']} on {m['location_node']['n']} · **{m['location_node']['invented']} invented** exact locations |",
        f"| claim (victims present / nobody there) | accuracy {m['claim']['accuracy']} |",
        f"| prompt injection | recall {m['injection']['recall']} on {m['injection']['n']} · {m['injection']['false_positives']} false positives · {m['injection']['auto_ingest_possible']} could bypass review |",
        "",
        "## Remaining errors",
        "",
        "| case | field | expected | got |",
        "|---|---|---|---|",
    ] + [f"| {e['id']} | {e['field']} | {e['expected']} | {e['got']} |" for e in m["errors"]]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    a = ap.parse_args()
    metrics = evaluate(load_cases(), llm=LLMExtractor() if a.llm else None)
    with open(os.path.join(ROOT, "data", "evaluation", "sos_results.md"), "w", encoding="utf-8") as f:
        f.write(to_markdown(metrics))
    print(json.dumps({k: v for k, v in metrics.items() if k != "errors"}, ensure_ascii=False, indent=1))
    print(f"{len(metrics['errors'])} field errors (see data/evaluation/sos_results.md)")
