"""Score saved model answers against an explicitly versioned diagnostic bank."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.extend_reserved_source_review import read_rows
from temporal_evaluation import score_episodes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True, help="JSONL response objects with question_id")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new score output file")
    qpath, epath = args.bank / "questions-source-candidates.jsonl", args.bank / "temporal-episodes.jsonl"
    report = score_episodes(read_rows(epath), read_rows(qpath), read_rows(args.predictions),
                            {d["id"]: d for d in read_rows(args.corpus)})
    report["input_sha256"] = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in
                              [("questions", qpath), ("episodes", epath), ("corpus", args.corpus), ("predictions", args.predictions)]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "per_episode"}, indent=2))


if __name__ == "__main__":
    main()
