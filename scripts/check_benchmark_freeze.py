"""Inventory reserved readiness and prepare blank source-review queues; no calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_readiness import check_readiness


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--questions", type=Path)
    parser.add_argument("--protocol", type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new readiness snapshot")
    folder = ROOT / "modules/l0l4-memory/data/experiments/diverse-announcements-20261031"
    corpus = folder / "corpus-split-v2.jsonl"
    documents = read(corpus)
    assignments = json.loads((folder / "split-v2.json").read_text(encoding="utf-8"))["assignments"]
    assert all(hashlib.sha256(d["text"].encode()).hexdigest() == d["text_sha256"] for d in documents)
    questions = read(args.questions) if args.questions else []
    protocol = json.loads(args.protocol.read_text(encoding="utf-8")) if args.protocol else None
    report = check_readiness(documents, assignments, questions, protocol)
    reserved = [d for d in documents if assignments[d["stock_code"]] == "test_reserved"]
    report.update(reserved_source_documents=len(reserved), corpus_sha256=hashlib.sha256(corpus.read_bytes()).hexdigest(),
                  source_hash_checks_passed=len(documents), freeze_manifest_created=False)
    queue = []
    for code in sorted({d["stock_code"] for d in reserved}):
        docs = [d for d in reserved if d["stock_code"] == code]
        queue.append({"stock_code": code, "company": docs[0]["company"], "split": "test_reserved", "split_version": 2,
            "source_ids": [d["id"] for d in docs], "acquisition_stratum": docs[0]["acquisition_stratum"],
            "review_status": "unreviewed", "source_qualification": "pending", "qualified_questions": [],
            "reference_tier": None, "reviewers": [], "missing_sources": [], "notes": ""})
    args.out.mkdir(parents=True)
    (args.out / "readiness.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.out / "reserved-reference-queue.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in queue), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
