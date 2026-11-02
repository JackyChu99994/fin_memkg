"""Analyze retained one-shot answers with company clusters and explicit costs."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matched_disclosure import METHODS
from scripts.complete_stage5_study import cohort
from scripts.extend_reserved_source_review import read_rows
from temporal_evaluation import score_episodes


def company_rates(rows):
    grouped = defaultdict(list)
    for r in rows:
        grouped[r["stock_code"]].append(int(r["score"]["exact_answer_correct"]))
    return {code: statistics.mean(vals) for code, vals in grouped.items()}


def bootstrap(values):
    rng = random.Random(20261102)
    samples = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(5000))
    return [samples[124], samples[4874]]


def analyze(run):
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    questions, docs, _, _ = cohort(summary["partition"])
    qmap = {q["id"]: q for q in questions}
    rows = read_rows(run / "records.jsonl")
    assert len(rows) == len(questions)*5
    assert len({(r["question_id"], r["method"]) for r in rows}) == len(rows)
    result = {"partition": summary["partition"], "questions": len(questions), "companies": summary["companies"],
              "eligible_sources": summary["unique_sources"], "reference_tier": "AI_silver", "methods": {},
              "shared_extraction": summary["usage"]["shared_extraction"], "source_calls": summary["source_calls"],
              "answer_calls": summary["answer_calls"], "extraction_statuses": summary["extraction_statuses"],
              "accepted_observations": summary["accepted_observations"], "quarantined_observations": summary["quarantined_observations"],
              "citation_semantic_entailment": "not_automatically_judged", "results_sha256": hashlib.sha256((run / "records.jsonl").read_bytes()).hexdigest()}
    rates = {}
    for method in METHODS:
        rs = [r for r in rows if r["method"] == method]
        rates[method] = company_rates(rs)
        vals = list(rates[method].values())
        groups = defaultdict(list)
        for r in rs:
            q = qmap[r["question_id"]]
            groups[q.get("benchmark_family", q.get("task_family", "development"))].append(r)
        memory = method in METHODS[2:]
        mean_coverage = statistics.mean(r["score"]["reference_designated_source_coverage"] or 0 for r in rs)
        result["methods"][method] = {"n": len(rs), "correct": sum(r["score"]["exact_answer_correct"] for r in rs),
            "accuracy": sum(r["score"]["exact_answer_correct"] for r in rs)/len(rs),
            "company_macro_accuracy": statistics.mean(vals), "company_bootstrap95_macro": bootstrap(vals),
            "statuses": dict(Counter(r["status"] for r in rs)), "schema_valid": sum(r["score"]["schema_valid"] for r in rs),
            "wrong_scheme_when_answered": sum(r["score"]["answered"] and not r["score"]["scheme_correct"] for r in rs),
            "false_abstention_on_answerable": sum(qmap[r["question_id"]].get("reference_answerability") != "insufficient" and r.get("result", {}).get("status") == "insufficient" for r in rs),
            "negative_verdict_correct": sum(qmap[r["question_id"]].get("reference_answerability") == "insufficient" and r["score"]["exact_answer_correct"] for r in rs),
            "mean_designated_source_coverage_not_entailment": mean_coverage,
            "warm_answer_input_tokens": sum(r["usage"].get("input_tokens", 0) for r in rs),
            "warm_answer_output_tokens": sum(r["usage"].get("output_tokens", 0) for r in rs),
            "cold_input_tokens": sum(r["usage"].get("input_tokens", 0) for r in rs) + (summary["usage"]["shared_extraction"]["input_tokens"] if memory else 0),
            "cold_output_tokens": sum(r["usage"].get("output_tokens", 0) for r in rs) + (summary["usage"]["shared_extraction"]["output_tokens"] if memory else 0),
            "mean_answer_seconds_among_attempted": statistics.mean(r["elapsed_seconds"] for r in rs if r["api_attempted"]) if any(r["api_attempted"] for r in rs) else None,
            "family_counts": {g: {"n": len(items), "correct": sum(r["score"]["exact_answer_correct"] for r in items)} for g, items in groups.items()}}
    baseline = rates["tfidf_rag"]
    result["paired_company_macro_differences_vs_rag"] = {}
    for method in METHODS:
        values = [rates[method][code] - baseline[code] for code in sorted(baseline)]
        result["paired_company_macro_differences_vs_rag"][method] = {"mean": statistics.mean(values), "bootstrap95": bootstrap(values)}
    common = [qid for qid in qmap if all(r["api_attempted"] for r in rows if r["question_id"] == qid)]
    result["all_five_available_subset"] = {"question_ids": common, "n": len(common),
        "correct": {m: sum(r["score"]["exact_answer_correct"] for r in rows if r["method"] == m and r["question_id"] in common) for m in METHODS},
        "scope": "secondary_availability_subset_not_primary_and_not_posthoc_question_deletion"}
    if summary["partition"] == "test_reserved":
        episodes = read_rows(ROOT / "modules/l0l4-memory/data/experiments/reserved-source-questions-v7-20261102/temporal-episodes.jsonl")
        result["temporal_diagnostics"] = {m: score_episodes(episodes, questions, [r.get("result", {"question_id": r["question_id"]}) for r in rows if r["method"] == m], docs) for m in METHODS}
    result["reported_physical_tokens_once"] = {key: sum(summary["usage"][phase][key] for phase in ["shared_extraction", "answers"]) for key in ["input_tokens", "output_tokens"]}
    result["provider_usage_missing_calls"] = sum(not r["usage"] for r in read_rows(run / "extraction-records.jsonl")) + sum(r["api_attempted"] and not r["usage"] for r in rows)
    failures = [{"question_id": r["question_id"], "method": r["method"], "status": r["status"],
                 "reference": qmap[r["question_id"]]["reference_draft"], "reference_scheme": qmap[r["question_id"]]["target_scheme"],
                 "prediction": r.get("result"), "validation_issues": r["score"]["validation_issues"],
                 "field_matches": r["score"]["field_matches"], "extraction_failures": r["extraction_failures"]}
                for r in rows if not r["score"]["exact_answer_correct"]]
    return result, failures


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error("New analysis directory required")
    result, failures = analyze(a.run)
    a.out.mkdir(parents=True)
    (a.out / "analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (a.out / "failure-cases.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    with (a.out / "methods.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["method", "n", "correct", "accuracy", "company_macro", "macro_ci_low", "macro_ci_high", "warm_input_tokens", "cold_input_tokens"])
        for m, r in result["methods"].items():
            writer.writerow([m, r["n"], r["correct"], r["accuracy"], r["company_macro_accuracy"], *r["company_bootstrap95_macro"], r["warm_answer_input_tokens"], r["cold_input_tokens"]])
    print(json.dumps({"partition": result["partition"], "questions": result["questions"], "methods": {m: r["correct"] for m, r in result["methods"].items()}, "failure_rows": len(failures)}, indent=2))


if __name__ == "__main__":
    main()
