"""Inventory existing sources for a harder benchmark without generating labels."""
from pathlib import Path
import argparse
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "completion_title": r"实施完毕|实施完成|回购完成",
    "termination_title": r"终止|取消",
    "correction_title": r"更正|修订|补充",
    "first_purchase_title": r"首次",
    "cancellation_title_not_execution_completion": r"注销",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new directory; inventory versions must be preserved")
    base = ROOT / "modules/l0l4-memory/data/experiments"
    corpus_path = base / "lifecycle-expanded40-20261030/corpus.jsonl"
    rows = [json.loads(line) for line in corpus_path.read_text(encoding="utf-8").splitlines()]
    episode_path = base / "source-adjudicated-v4-20261031/episodes.jsonl"
    episodes = [json.loads(line) for line in episode_path.read_text(encoding="utf-8").splitlines()]
    inventory = {}
    for name, pattern in PATTERNS.items():
        candidates = [row for row in rows if re.search(pattern, row["title"])]
        inventory[name] = [{key: row[key] for key in
            ("id", "stock_code", "company", "title", "disclosure_date", "source_url")}
            | {"qualification": "title_candidate_not_adjudicated_reference"} for row in candidates]
    reserved = [e for e in episodes if e["split"] == "test_reserved"]
    summary = {
        "source_documents": len(rows), "source_companies": len({r["stock_code"] for r in rows}),
        "existing_questions": len(episodes), "existing_reserved_questions": len(reserved),
        "reserved_class_counts": {label: sum(e["gold"]["repurchase_stage"] == label for e in reserved)
            for label in ("NO_EXECUTION_DISCLOSED", "STARTED", "COMPLETED")},
        "title_candidate_counts": {name: len(values) for name, values in inventory.items()},
        "network_calls": 0, "new_questions_labeled": 0,
        "reuse_policy": "all 40 existing companies are development or diagnostics only for a new benchmark",
        "warning": "Title matches are acquisition leads, not verified events or ground truth",
        "input_sha256": {"corpus": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
                         "episodes": hashlib.sha256(episode_path.read_bytes()).hexdigest()},
    }
    args.out.mkdir(parents=True)
    (args.out / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "exclude-existing-companies.json").write_text(json.dumps(sorted({r["stock_code"] for r in rows}), indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
