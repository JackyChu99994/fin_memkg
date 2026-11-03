"""Recompute saved stage-study metrics against corrected references; no API calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules/l0l4-memory"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(MODULE))
from experiments.complete_study import summarize


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new output directory to preserve original records")
    base = MODULE / "data/experiments"
    references = {e["id"]: e for e in read(base / "source-adjudicated-v4-20261031/episodes.jsonl")}
    records = read(base / "expanded-study-20261031/records.jsonl")
    for row in records:
        gold = references[row["question_id"]]["gold"]
        row["gold"] = gold["repurchase_stage"]
        row["correct"] = row["status"] == "ok" and row["prediction"]["repurchase_stage"] == row["gold"]
        row["grounded_correct"] = bool(row["correct"] and not row.get("invented_evidence_ids")
            and set(gold["evidence_ids"]) <= set(row["prediction"]["evidence_ids"]))
    summary = {"all": summarize(records), "partitions": {
        split: summarize([r for r in records if r["split"] == split])
        for split in ("development", "test_reserved")}, "additional_model_calls": 0,
        "reference_tier": "source_anchored_silver_not_human_gold"}
    args.out.mkdir(parents=True)
    (args.out / "records.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v["correct"] for k, v in summary["partitions"]["test_reserved"]["methods"].items()}))


if __name__ == "__main__":
    main()
