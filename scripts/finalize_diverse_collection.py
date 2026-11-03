"""Validate raw acquisition and version a stratified split before any annotation."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
from collect_diverse_announcements import ROOT, development_codes


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, required=True)
    args = parser.parse_args()
    folder = args.collection
    target = folder / "split-v2.json"
    if target.exists():
        parser.error("Version already exists; preserve it")
    protocol = load(folder / "protocol.json")
    selected = load(folder / "selected-companies.json")
    candidates = load(folder / "candidates.json")
    corpus = [json.loads(line) for line in (folder / "corpus.jsonl").read_text(encoding="utf-8").splitlines()]
    codes = {r["anchor"]["secCode"] for r in selected}
    assert len(codes) == len(selected) == 80
    assert not codes & set(protocol["excluded_companies"])
    assert len({r["id"] for r in corpus}) == len(corpus)
    for row in corpus:
        assert sha((folder / row["pdf"]).read_bytes()) == row["pdf_sha256"], row["id"]
        assert sha(row["text"].encode()) == row["text_sha256"], row["id"]
    missing_anchors = [r["anchor_id"] for r in candidates if r["anchor_id"] not in {d["id"] for d in corpus}]
    development = development_codes(selected, 20)
    assignment = {code: "development" if code in development else "test_reserved" for code in sorted(codes)}
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "version": 2,
        "reason": "Global hash order left no termination lead in development; stratify before any labels or inference",
        "only_split_changed": True, "source_selection_unchanged": True, "model_calls_before_change": 0,
        "human_labels_before_change": 0, "scheme_identity_status": "unreviewed",
        "algorithm": "Within each title stratum hash-rank companies; round-robin take five per stratum for development",
        "original_selection_sha256": sha((folder / "selected-companies.json").read_bytes()),
        "original_corpus_sha256": sha((folder / "corpus.jsonl").read_bytes()), "assignments": assignment}
    for row in corpus:
        row["acquisition_split_v1"] = row["split_candidate"]
        row["split_candidate"] = assignment[row["stock_code"]]
        row["split_version"] = 2
    v2 = folder / "corpus-split-v2.jsonl"
    v2.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in corpus), encoding="utf-8")
    manifest["versioned_corpus_sha256"] = sha(v2.read_bytes())
    target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    review = [{"stock_code": r["anchor"]["secCode"], "company": r["anchor"]["secName"],
        "anchor_id": "CNINFO_" + str(r["anchor"]["announcementId"]),
        "acquisition_stratum": r["acquisition_stratum"], "split_candidate": assignment[r["anchor"]["secCode"]],
        "review_status": "unreviewed", "reviewer": "", "scheme_ids": [], "source_scheme_links": [],
        "anchor_semantic_type": None, "required_missing_sources": [], "notes": ""} for r in selected]
    (folder / "scheme-review-queue.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in review), encoding="utf-8")
    summary = {"status": "integrity_checked_identity_and_labels_pending", "pdf_and_text_hashes_verified": len(corpus),
        "missing_extracted_anchors": missing_anchors, "no_previous_company_overlap": True,
        "split_version": 2, "model_calls": 0, "human_reviewed": 0, "evaluation_ready_questions": 0,
        "strata_by_split": {split: dict(Counter(r["acquisition_stratum"] for r in review if r["split_candidate"] == split))
                             for split in ("development", "test_reserved")}}
    (folder / "integrity-validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
