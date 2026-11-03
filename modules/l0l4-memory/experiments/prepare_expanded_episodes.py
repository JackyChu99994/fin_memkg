"""Freeze expanded lifecycle episodes with a human-review gate for reserved test.

Draft preparation is permitted only for the development partition. Scheme
exclusions are explicit and must be frozen before effectiveness inference.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path

from experiments.common import manifest, read_jsonl, write_jsonl


def prepare(corpus, references, split, allow_draft=False):
    if split == "test_reserved" and allow_draft:
        raise ValueError("Reserved test requires reviewed references")
    labels = {row["id"]: row for row in references}
    grouped = {}
    for doc in corpus:
        if doc["split"] == split:
            grouped.setdefault(doc["candidate_id"], []).append(doc)
    episodes, exclusions = [], []
    for candidate, documents in sorted(grouped.items()):
        first = next(doc for doc in documents if doc["role"] == "initial_candidate")
        eligible = []
        for doc in sorted(documents, key=lambda item: (item["disclosure_date"], item["id"])):
            label = labels.get(doc["id"])
            if label is None:
                raise ValueError("Missing reference: " + doc["id"])
            if label.get("text_sha256") != doc["text_sha256"] or label.get("split") != split:
                raise ValueError("Source hash or partition mismatch")
            if not allow_draft and (label.get("review_status") != "reviewed" or not label.get("reviewer", "").strip()):
                raise ValueError("Human review required: " + doc["id"])
            values = label.get("adjudicated") or label.get("draft") or {}
            reason = None
            if values.get("scheme_relation") != "SAME_SCHEME":
                reason = "different_or_uncertain_scheme"
            elif values.get("initial_approval_year") != 2024:
                reason = "original_approval_not_confirmed_in_2024"
            elif values.get("repurchase_stage") not in {"NO_EXECUTION_DISCLOSED", "STARTED", "COMPLETED"} or values.get("cancellation_stage") not in {"INTENDED", "COMPLETED", "NOT_DISCLOSED"}:
                reason = "unresolved_state_reference"
            elif allow_draft and label.get("validation_errors"):
                reason = "draft_source_span_validation_requires_adjudication"
            if reason:
                exclusions.append({"id": doc["id"], "candidate_id": candidate, "reason": reason})
                continue
            eligible.append((doc, label, values))
        # All raw candidate sources remain chronological inputs, including sources
        # whose reference needs review; a confirmed different scheme is removed.
        input_docs = []
        for doc in documents:
            values = (labels[doc["id"]].get("adjudicated") or labels[doc["id"]].get("draft") or {})
            if values.get("scheme_relation") == "DIFFERENT_SCHEME":
                continue
            bound = (date.fromisoformat(doc["disclosure_date"]) + timedelta(days=1)).isoformat() + "T00:00:00+08:00"
            input_docs.append({"id": doc["id"], "stock_code": doc["stock_code"], "text": doc["text"],
                "published_at": bound, "disclosure_date": doc["disclosure_date"], "source_url": doc["source_url"],
                "timestamp_semantics": "conservative_date_only_availability_bound_not_first_release"})
        raw_ids = {doc["id"] for doc in input_docs}
        for doc, label, values in eligible:
            bound = (date.fromisoformat(doc["disclosure_date"]) + timedelta(days=1)).isoformat() + "T00:00:00+08:00"
            evidence = values.get("evidence", [])
            citations = {item["document_id"] for item in evidence if isinstance(item, dict)
                         and item.get("field") in {"repurchase_stage", "cancellation_stage"}
                         and item.get("document_id") in raw_ids}
            citations.add(doc["id"])
            available = {item["id"] for item in input_docs if item["published_at"] <= bound}
            if not citations <= available:
                raise ValueError("Reference cites unavailable future evidence")
            episodes.append({"id": candidate + "_AT_" + doc["id"], "task": "repurchase_lifecycle",
                "memory_protocol": "factual-lifecycle-v2-admission", "answer_protocol": "lifecycle-explicit-intent-v2",
                "stock_code": doc["stock_code"], "independence_group": candidate, "split": split,
                "event_key": first["company"] + " " + first["title"] + " (" + first["id"] + ")",
                "as_of": bound, "documents": input_docs,
                "query": "For " + first["company"] + " " + first["title"] + " (" + first["id"] + "), report the latest explicitly disclosed repurchase stage and share-cancellation stage by as_of. Distinguish approvals, actual purchases, implementation completion, and completed share cancellation. Do not predict returns.",
                "review_status": "development_ai_draft" if allow_draft else "reviewed",
                "reviewer": label.get("reviewer", ""),
                "reference_origin": "source_grounded_AI_draft" if allow_draft else "source_grounded_draft_with_recorded_user_review",
                "gold": {"repurchase_stage": values["repurchase_stage"], "cancellation_stage": values["cancellation_stage"], "evidence_ids": sorted(citations)}})
    return episodes, exclusions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--split", choices=["development", "test_reserved"], required=True)
    parser.add_argument("--allow-draft", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new output directory")
    episodes, exclusions = prepare(read_jsonl(args.corpus), read_jsonl(args.references), args.split, args.allow_draft)
    args.out.mkdir(parents=True)
    write_jsonl(args.out / "episodes.jsonl", episodes)
    write_jsonl(args.out / "exclusions.jsonl", exclusions)
    frozen = manifest([args.corpus, args.references], task="expanded_episode_preparation", split=args.split,
        episodes=len(episodes), candidate_groups=len({row["independence_group"] for row in episodes}),
        exclusions=len(exclusions), human_review_required_for_test=True, allow_draft=args.allow_draft,
        effectiveness_calls=0)
    (args.out / "manifest.json").write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    print(json.dumps({"episodes": len(episodes), "exclusions": len(exclusions), "split": args.split}))


if __name__ == "__main__":
    main()
