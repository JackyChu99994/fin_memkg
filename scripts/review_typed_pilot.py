"""Review both frozen pilots and apply public-only admission, without API calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from repurchase_admission import project_machine_claim
from repurchase_evaluation import score_response


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new review directory")
    base = ROOT / "modules/l0l4-memory/data/experiments"
    audit = base / "development-identity-audit-v3-20261101"
    questions = {q["id"]: q for q in read(audit / "development-questions-draft.jsonl")}
    docs = {d["id"]: d for d in read(audit / "development-source-corpus.jsonl")}
    inputs = {}
    reviews = []
    for name in ("typed-qwen-development-pilot-20261101", "typed-qwen-development-pilot-v2-20261101"):
        records_path = base / name / "records.jsonl"
        inputs[name] = hashlib.sha256(records_path.read_bytes()).hexdigest()
        rows = read(records_path)
        problems = []
        for row in rows:
            q = questions[row["question_id"]]
            prediction = row.get("prediction")
            score = score_response(q, prediction, docs)
            if not row["score"]["exact_answer_correct"]:
                if prediction and isinstance(prediction.get("target_scheme"), str) and prediction["target_scheme"].startswith("CODE_"):
                    cause = "literal_placeholder_format_failure"
                elif "answer_field_set_mismatch" in row["score"]["validation_issues"]:
                    cause = "answer_structure_failure_values_may_be_present_in_other_structure"
                elif all(row["score"]["field_matches"].values()) and not row["score"]["scheme_correct"]:
                    cause = "comparison_facts_match_but_common_target_selection_breaks_protocol"
                elif "primary_issuer_source" in row["score"]["field_matches"] and not row["score"]["field_matches"]["primary_issuer_source"]:
                    cause = "wrong_primary_source"
                else:
                    cause = "other_failure_requires_source_review"
                problems.append({"question_id": row["question_id"], "cause": cause, "raw_prediction": prediction,
                                 "reference_draft": q["reference_draft"], "recorded_score": row["score"], "common_v3_score": score})
        reviews.append({"run": name, "calls": len(rows), "recorded_exact": sum(r["score"]["exact_answer_correct"] for r in rows),
            "recorded_schema_valid": sum(r["score"]["schema_valid"] for r in rows),
            "recorded_fields_correct": sum(r["score"]["fields_correct"] for r in rows),
            "common_v3_exact": sum(score_response(questions[r["question_id"]], r.get("prediction"), docs)["exact_answer_correct"] for r in rows),
            "common_v3_fields_correct": sum(score_response(questions[r["question_id"]], r.get("prediction"), docs)["fields_correct"] for r in rows),
            "problems": problems, "usage": {key: sum(r["usage"].get(key, 0) for r in rows) for key in ("input_tokens", "output_tokens")}})
    latest = read(base / "typed-qwen-development-pilot-v2-20261101/records.jsonl")
    prompts = {p["question_id"]: json.loads(p["user"]) for p in read(base / "typed-development-contract-v3-20261101/public-prompts.jsonl")}
    projections = [{"question_id": r["question_id"], **project_machine_claim(prompts[r["question_id"]], r.get("prediction"))} for r in latest]
    assert len(projections) == 23
    summary = {"physical_model_calls_in_both_pilots": sum(r["calls"] for r in reviews),
        "usage": {key: sum(r["usage"][key] for r in reviews) for key in ("input_tokens", "output_tokens")},
        "latest_recorded_schema_valid": reviews[-1]["recorded_schema_valid"],
        "latest_recorded_exact_against_drafts": reviews[-1]["recorded_exact"],
        "latest_fields_correct": reviews[-1]["recorded_fields_correct"], "fields_total": 69,
        "failure_categories": dict(Counter(p["cause"] for p in reviews[-1]["problems"])),
        "public_only_admission": dict(Counter(p["status"] for p in projections)),
        "admission_issues": dict(Counter(issue for p in projections for issue in p["issues"])),
        "comparison_metadata_warnings": sum(bool(p.get("warnings")) for p in projections),
        "reference_tier": "assistant_source_anchored_development_draft", "additional_model_calls": 0,
        "formal_heldout_result": False, "RAG_memory_comparison": False, "machine_claims_are_not_verified_facts": True,
        "raw_responses_and_original_scores_unchanged": True, "input_sha256": inputs}
    args.out.mkdir(parents=True)
    for name, data in (("error-review.json", reviews), ("summary.json", summary)):
        (args.out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "machine-claim-projections.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in projections), encoding="utf-8")
    (args.out / "admission-source.py").write_bytes((ROOT / "repurchase_admission.py").read_bytes())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
