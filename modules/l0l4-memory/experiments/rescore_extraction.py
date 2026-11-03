"""Rescore saved model outputs against a frozen user-reviewed reference, without API calls."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from experiments.common import (counts, event_sets, extraction_summary, manifest,
    prf, read_jsonl, reviewed_labels, save_run, strict_events)


def rescore(corpus, labels, records):
    references = reviewed_labels(corpus, labels)
    if {row["id"] for row in records} != set(references):
        raise ValueError("Saved records must cover exactly the reviewed corpus")
    result = []
    for original in records:
        row = copy.deepcopy(original)
        expected = event_sets(references[row["id"]]["events"])
        accepted = event_sets(row.get("events", []))
        row["counts"] = {kind: counts(accepted[kind], expected[kind]) for kind in expected}
        row["exact"] = row["status"] == "ok" and accepted["states"] == expected["states"]
        if row["status"] == "ok" and row.get("raw"):
            candidates = strict_events(row["raw"])
        else:
            candidates = [] if row["status"] != "ok" else row.get("events", [])
        valid = [event for event in candidates if all(event.get(key) for key in ("source", "relation", "target"))]
        raw = counts(event_sets(valid)["relations"], expected["relations"])
        raw["fp"] += len(candidates) - len(valid)
        row["raw_relation_counts"] = raw
        result.append(row)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new output directory; original model outputs are preserved")
    corpus, labels = read_jsonl(args.corpus), read_jsonl(args.labels)
    source_records = args.run / "records.jsonl"
    source_manifest = args.run / "manifest.json"
    original = json.loads(source_manifest.read_text(encoding="utf-8"))
    records = rescore(corpus, labels, read_jsonl(source_records))
    summary = extraction_summary(records)
    totals = {key: sum(row["raw_relation_counts"][key] for row in records) for key in ("tp", "fp", "fn")}
    summary.update(raw_relations_micro=prf(**totals),
        evidence_scope="user_reviewed_reference_on_development_set",
        reference_origins=sorted({row.get("annotation_origin", "unspecified") for row in labels}),
        human_reviewed_documents=len(labels), live_calls_this_rescore=0,
        note="Usage belongs to saved original calls. User review does not make development prompts held-out or independently annotated.")
    run_manifest = manifest([args.corpus, args.labels, source_records, source_manifest],
        task="rescore_saved_extraction", inference_mode="RESCORE_SAVED_LIVE_OUTPUTS",
        model=original.get("model"), provider=original.get("provider"),
        original_task_version=original.get("task_version", "legacy_contract"),
        original_run=str(args.run.resolve()), calls=[], live_calls_this_rescore=0)
    save_run(args.out, records, summary, run_manifest)
    print(json.dumps({"out": str(args.out), "documents": len(records),
        "relation_f1": summary["micro"]["relations"]["f1"], "human_reviewed_documents": len(labels), "new_api_calls": 0}))


if __name__ == "__main__":
    main()
