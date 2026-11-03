"""Score saved typed responses without calling any API or rewriting references."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from repurchase_evaluation import SCHEMA_VERSION, score_response


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new output version")
    questions = read_rows(args.audit / "development-questions-draft.jsonl")
    documents = {d["id"]: d for d in read_rows(args.audit / "development-source-corpus.jsonl")}
    predictions = read_rows(args.predictions)
    ids = [p.get("question_id") for p in predictions]
    if len(ids) != len(set(ids)) or set(ids) - {q["id"] for q in questions}:
        parser.error("Duplicate or unknown prediction question IDs")
    by_id = {p["question_id"]: p for p in predictions}
    records = [{**score_response(q, by_id.get(q["id"]), documents), "stock_code": q["stock_code"],
                "task_family": q["task_family"], "missing_prediction": q["id"] not in by_id} for q in questions]
    def aggregate(rows):
        total = len(rows)
        fields_total = sum(r["fields_total"] for r in rows)
        fields_correct = sum(r["fields_correct"] for r in rows)
        return {"questions": total, "exact_correct": sum(r["exact_answer_correct"] for r in rows),
                "schema_valid": sum(r["schema_valid"] for r in rows), "answered": sum(r["answered"] for r in rows),
                "answer_coverage": sum(r["answered"] for r in rows) / total,
                "fields_correct": fields_correct, "fields_total": fields_total,
                "field_accuracy": fields_correct / fields_total if fields_total else None,
                "missing_predictions": sum(r["missing_prediction"] for r in rows)}
    companies, tasks = defaultdict(list), defaultdict(list)
    for row in records:
        companies[row["stock_code"]].append(row)
        tasks[row["task_family"]].append(row)
    summary = {"all": aggregate(records), "by_company": {k: aggregate(v) for k, v in companies.items()},
        "by_task": {k: aggregate(v) for k, v in tasks.items()}, "additional_model_calls": 0, "schema_version": SCHEMA_VERSION,
        "macro_company_exact_accuracy": sum(sum(r["exact_answer_correct"] for r in rows) / len(rows) for rows in companies.values()) / len(companies),
        "reference_tiers": sorted({q["reference_tier"] for q in questions}),
        "formal_evaluation_ready": all(q.get("formal_evaluation_ready") is True for q in questions),
        "citation_entailment": "not_automatically_judged", "scope": "saved_response_scoring_only"}
    args.out.mkdir(parents=True)
    (args.out / "records.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary["all"], indent=2))


if __name__ == "__main__":
    main()
