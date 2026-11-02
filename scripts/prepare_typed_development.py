"""Prepare blind prompts and synthetic scorer probes, without model inference."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from repurchase_evaluation import DATE_FIELDS, SHARE_FIELDS, SCHEMA_VERSION, score_response, serialize_prompt


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new directory to preserve versions")
    questions = read_rows(args.audit / "development-questions-draft.jsonl")
    documents = {d["id"]: d for d in read_rows(args.audit / "development-source-corpus.jsonl")}
    assert len(questions) == 23 and all(q["split"] == "development" for q in questions)
    prompts, probes = [], []
    for question in questions:
        system, user = serialize_prompt(question, documents)
        public = json.loads(user)
        assert not {"reference_draft", "reference_proofs", "target_scheme", "task_family", "split"} & public.keys()
        prompts.append({"question_id": question["id"], "system": system, "user": user,
                        "status": "prepared_not_called", "schema_version": SCHEMA_VERSION})
        oracle = {"question_id": question["id"], "status": "answered", "target_scheme": question["target_scheme"],
                  "answer": deepcopy(question["reference_draft"]), "evidence_ids": sorted({p["source_id"] for p in question["reference_proofs"]})}
        result = score_response(question, oracle, documents)
        assert result["exact_answer_correct"], (question["id"], result)
        probes.append({"question_id": question["id"], "probe": "reference_round_trip_not_model_prediction", "prediction": oracle,
                       "should_pass": True, "score": result})
        variants = []
        wrong_scheme = deepcopy(oracle)
        wrong_scheme["target_scheme"] = question["stock_code"] + "_BOARD_2000-01-01"
        variants.append(("wrong_original_scheme", wrong_scheme))
        future = next(d["id"] for d in documents.values() if d["disclosure_date"] >= question["as_of"][:10])
        future_answer = deepcopy(oracle)
        future_answer["evidence_ids"] = [future]
        variants.append(("future_source", future_answer))
        wrong_id = deepcopy(oracle)
        wrong_id["evidence_ids"] = ["CNINFO_INVENTED"]
        variants.append(("invented_source", wrong_id))
        wrong_fact = deepcopy(oracle)
        key = next(iter(wrong_fact["answer"]))
        value = wrong_fact["answer"][key]
        if type(value) is bool:
            replacement = not value
        elif key in DATE_FIELDS:
            replacement = "2000-01-01"
        elif isinstance(value, dict):
            replacement = {k: "2000-01-01" for k in value}
        elif isinstance(value, (int, float)):
            replacement = value + 1
        else:
            replacement = str(value) + "__WRONG"
        wrong_fact["answer"][key] = replacement
        variants.append(("changed_fact", wrong_fact))
        for key in set(oracle["answer"]) & SHARE_FIELDS:
            scale_error = deepcopy(oracle)
            scale_error["answer"][key] = int(oracle["answer"][key]) * 10000
            variants.append(("ten_thousand_fold_share_error:" + key, scale_error))
        for kind, prediction in variants:
            result = score_response(question, prediction, documents)
            assert not result["exact_answer_correct"], (question["id"], kind)
            probes.append({"question_id": question["id"], "probe": kind, "prediction": prediction,
                           "should_pass": False, "score": result})
    args.out.mkdir(parents=True)
    write_rows(args.out / "public-prompts.jsonl", prompts)
    write_rows(args.out / "synthetic-scorer-probes.jsonl", probes)
    summary = {"schema_version": SCHEMA_VERSION, "development_questions": len(questions), "blind_prompts_prepared": len(prompts),
        "reference_round_trips": sum(p["should_pass"] for p in probes), "negative_synthetic_probes_rejected": sum(not p["should_pass"] for p in probes),
        "model_calls": 0, "real_model_predictions": 0, "formal_reference_ready": 0,
        "warning": "Synthetic reference round-trips and perturbations test scorer behavior, not extraction or model accuracy",
        "reference_tier": "assistant_source_anchored_development_draft", "citation_entailment": "not_automatically_judged",
        "input_hashes": {name: hashlib.sha256((args.audit / name).read_bytes()).hexdigest()
                         for name in ("development-questions-draft.jsonl", "development-source-corpus.jsonl")}}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (args.out / "scoring-source.py").write_bytes((ROOT / "repurchase_evaluation.py").read_bytes())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
