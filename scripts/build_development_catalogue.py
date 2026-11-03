"""Build source-only development catalogue and inspect saved comparison claims."""
import argparse
from collections import Counter
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from repurchase_catalogue import build_catalogue, resolve_source_scheme


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new catalogue version")
    base = ROOT / "modules/l0l4-memory/data/experiments"
    path = base / "development-identity-audit-v3-20261101/development-source-corpus.jsonl"
    documents = read(path)
    assert len(documents) == 158 and all(d["split_candidate"] == "development" for d in documents)
    cutoff = (max(date.fromisoformat(d["disclosure_date"]) for d in documents) + timedelta(days=1)).isoformat() + "T00:00:00+08:00"
    catalogue = build_catalogue(documents, cutoff)
    prompts = {p["question_id"]: json.loads(p["user"]) for p in read(base / "typed-development-contract-v3-20261101/public-prompts.jsonl")}
    claims = read(base / "typed-qwen-development-pilot-v2-20261101/records.jsonl")
    comparisons = []
    for row in claims:
        mapping = row.get("prediction", {}).get("answer", {}).get("source_approval_dates")
        if not isinstance(mapping, dict):
            continue
        public = prompts[row["question_id"]]
        eligible = [d for d in documents if d["id"] in {s["id"] for s in public["documents"]}]
        scoped = build_catalogue(eligible, public["as_of"])
        comparisons.append({"question_id": row["question_id"], "as_of": public["as_of"],
            "raw_model_target": row["prediction"].get("target_scheme"),
            "source_bindings": [resolve_source_scheme(scoped, source, day) for source, day in mapping.items()],
            "original_score": row["score"], "uses_reference_answers": False,
            "scores_unchanged": True, "identity_status": "source_bound_candidates_pending_review"})
    args.out.mkdir(parents=True)
    (args.out / "catalogue.json").write_text(json.dumps(catalogue, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "comparison-bindings.json").write_text(json.dumps(comparisons, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "catalogue-source.py").write_bytes((ROOT / "repurchase_catalogue.py").read_bytes())
    summary = {"development_documents": len(documents), "candidate_groups": len(catalogue["schemes"]),
        "candidate_links": len(catalogue["links"]), "unresolved_primary_documents": len(catalogue["unresolved_primaries"]),
        "candidate_aliases_with_citation": len(catalogue["alias_proofs"]), "comparison_cases": len(comparisons),
        "binding_statuses": dict(Counter(b["status"] for c in comparisons for b in c["source_bindings"])),
        "model_calls": 0, "human_verified_schemes": 0, "unique_real_world_scheme_count": "not_certified",
        "reference_answers_used": False, "old_scores_unchanged": True,
        "source_corpus_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
