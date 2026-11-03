"""Build an alternative review bank from fixed templates, retaining AI failures."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reserved_source_templates import build_question


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new source-question version")
    base = ROOT / "modules/l0l4-memory/data/experiments"
    corpus = base / "diverse-announcements-20261031/corpus-split-v2.jsonl"
    documents = [d for d in read(corpus) if d["split_candidate"] == "test_reserved"]
    original_plan = base / "reserved-question-drafts-20261101/plan.json"
    work = json.loads(original_plan.read_text(encoding="utf-8"))["work"]
    assert len(work) == 60 and len(documents) == 444
    args.out.mkdir(parents=True)
    hashes = {}
    for name in ("reserved_source_templates.py", "repurchase_catalogue.py", "repurchase_identity.py", "repurchase_evaluation.py", "scripts/build_reserved_source_questions.py"):
        data = (ROOT / name).read_bytes()
        target = args.out / "sources" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    plan = {"created_at": datetime.now(timezone.utc).isoformat(), "scope": "source_question_construction_no_method_evaluation",
            "assignment_plan_sha256": hashlib.sha256(original_plan.read_bytes()).hexdigest(),
            "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest(), "source_sha256": hashes,
            "source_qualification": "pending_semantic_review", "AI_generation_failure_preserved": True, "model_calls": 0}
    (args.out / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    questions, unavailable = [], []
    for item in work:
        docs = [d for d in documents if d["stock_code"] == item["stock_code"]]
        item = {**item, "company": docs[0]["company"]}
        for family in item["assigned_families"]:
            try:
                question, reason = build_question(item, family, docs)
            except (ValueError, AssertionError, KeyError, TypeError) as exc:
                question, reason = None, "source_template_validation_failed:" + type(exc).__name__
            if question:
                questions.append(question)
            else:
                unavailable.append({"stock_code": item["stock_code"], "family": family, "reason": reason})
    for name, values in (("questions-source-candidates.jsonl", questions), ("unavailable-opportunities.jsonl", unavailable)):
        (args.out / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in values), encoding="utf-8")
    summary = {"opportunities": 180, "source_bound_question_candidates": len(questions), "unavailable_opportunities": len(unavailable),
        "candidate_companies": len({q["stock_code"] for q in questions}), "family_counts": dict(Counter(q["benchmark_family"] for q in questions)),
        "stage_class_counts": dict(Counter(q["reference_draft"]["repurchase_stage"] for q in questions if "repurchase_stage" in q["reference_draft"])),
        "formal_evaluation_ready_questions": 0, "source_qualified_questions": 0, "human_reviewed_questions": 0,
        "additional_model_calls": 0, "reference_tier": "source_anchored_silver_pending_semantic_review",
        "not_merged_with_failed_AI_drafts": True, "method_evaluation_started": False}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
