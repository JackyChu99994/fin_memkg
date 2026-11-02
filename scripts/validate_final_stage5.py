"""Offline integrity verification of complete frozen studies, not factual truth."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.complete_stage5_study import cohort
from scripts.extend_reserved_source_review import read_rows
from repurchase_identity import validate_span


def main():
    base = ROOT / "modules/l0l4-memory/data/experiments"
    checks = []
    for partition, folder, expected in [("development", "stage5-complete-development-20261102", 23),
                                         ("test_reserved", "stage5-complete-reserved-20261102", 91)]:
        run = base / folder
        questions, docs, qpath, cpath = cohort(partition)
        plan = json.loads((run / "plan.json").read_text(encoding="utf-8"))
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        assert len(questions) == expected
        assert plan["questions_sha256"] == hashlib.sha256(qpath.read_bytes()).hexdigest()
        assert plan["source_corpus_sha256"] == hashlib.sha256(cpath.read_bytes()).hexdigest()
        for path, digest in plan["protocol"]["code_hashes"].items():
            assert hashlib.sha256((run / "sources" / path).read_bytes()).hexdigest() == digest
        records = read_rows(run / "records.jsonl")
        prompts = read_rows(run / "prompts.jsonl")
        assert len(records) == len(prompts) == expected*5
        assert len({(r["question_id"], r["method"]) for r in records}) == expected*5
        qmap = {q["id"]: q for q in questions}
        for prompt in prompts:
            if prompt["status"] != "prepared":
                continue
            q = qmap[prompt["question_id"]]
            public = json.loads(prompt["user"])
            assert not {"reference_draft", "reference_proofs", "target_scheme", "reference_tier", "benchmark_family"} & set(public)
            for raw in public["evidence"]["raw_sources"]:
                sid = raw.get("id", raw.get("source_id"))
                assert sid in q["source_ids"] and docs[sid]["disclosure_date"] < q["as_of"][:10]
                text = docs[sid]["text"] if "id" in raw else docs[sid]["text"][raw["start"]:raw["end"]]
                assert raw["text"] == text
            for note in public["evidence"]["machine_observations"]:
                sid = note["source_id"]
                assert sid in q["source_ids"] and note["available_at"] <= q["as_of"]
                assert note["quote"] in docs[sid]["text"] and note["identity_quote"] in docs[sid]["text"]
        observations = read_rows(run / "observations.jsonl")
        for o in observations:
            assert validate_span(docs[o["source_id"]], o["span"]) and validate_span(docs[o["source_id"]], o["identity_span"])
        assert summary["protocol_hashes_unchanged"]
        checks.append({"partition": partition, "question_cards": expected, "answer_slots": len(records),
                       "source_calls": summary["source_calls"], "answer_calls": summary["answer_calls"],
                       "observations_hash_checked": len(observations), "prompt_cutoff_and_no_reference_leak_checks": "passed"})
    reserved = base / "stage5-complete-reserved-20261102"
    rp = json.loads((reserved / "plan.json").read_text(encoding="utf-8"))
    frozen = base / "stage5-frozen-protocol-20261102/freeze-with-analysis.json"
    assert rp["frozen_manifest_sha256"] == hashlib.sha256(frozen.read_bytes()).hexdigest()
    print(json.dumps({"status": "passed", "studies": checks, "frozen_manifest_verified": True,
                      "network_calls": 0, "independent_human_gold_certified": False,
                      "semantic_entailment_certified": False}, indent=2))


if __name__ == "__main__":
    main()
