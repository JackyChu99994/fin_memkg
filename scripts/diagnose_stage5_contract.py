"""Post-hoc decomposition of frozen scores; never rewrites primary criteria."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matched_disclosure import METHODS
from scripts.complete_stage5_study import cohort
from scripts.extend_reserved_source_review import read_rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--analysis", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error("New output path required")
    questions, _, _, _ = cohort("test_reserved")
    qs = {q["id"]: q for q in questions}
    rows = read_rows(a.run / "records.jsonl")
    analysis = json.loads(a.analysis.read_text(encoding="utf-8"))
    common = set(analysis["all_five_available_subset"]["question_ids"])
    result = {"scope": "posthoc_descriptive_score_decomposition_not_replacement_or_new_inference",
              "positive_cards": 66, "negative_cards": 25, "common_available_cards": len(common), "methods": {}}
    for method in METHODS:
        rs = [r for r in rows if r["method"] == method]
        neg = [r for r in rs if qs[r["question_id"]]["reference_answerability"] == "insufficient"]
        pos = [r for r in rs if qs[r["question_id"]]["reference_answerability"] != "insufficient"]
        multi = [r for r in rs if qs[r["question_id"]]["benchmark_family"] == "multi_scheme"]
        result["methods"][method] = {
            "positive_all_field_values_correct_without_schema_or_target_gate": sum(bool(r["score"]["field_matches"]) and all(r["score"]["field_matches"].values()) and r.get("result", {}).get("status") == "answered" for r in pos),
            "negative_insufficient_verdict_without_payload_shape_gate": sum(r.get("result", {}).get("status") == "insufficient" for r in neg),
            "negative_insufficient_with_nonempty_answer_object": sum(r.get("result", {}).get("status") == "insufficient" and bool(r.get("result", {}).get("answer")) for r in neg),
            "multi_scheme_mapping_values_correct_without_target_gate": sum(bool(r["score"]["field_matches"]) and all(r["score"]["field_matches"].values()) for r in multi),
            "common_subset_answer_input_tokens": sum(r["usage"].get("input_tokens", 0) for r in rs if r["question_id"] in common)}
    a.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
