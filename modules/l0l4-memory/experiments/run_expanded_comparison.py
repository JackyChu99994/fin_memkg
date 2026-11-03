"""Run a frozen multi-company lifecycle comparison after reference review.

No reference draft or held-out result can silently become a reviewed benchmark.
Cutoffs remain clustered by whole company/scheme for reporting.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics

from experiments.common import LiveClient, manifest, read_jsonl, save_run
from experiments.eval_memory import eligible_documents, evaluate_episode

METHODS = ["tfidf_rag", "append_memory_archive", "state_memory_archive"]


def validate_episodes(episodes, allow_draft):
    if not episodes:
        raise ValueError("No eligible episodes")
    company_splits = {}
    for episode in episodes:
        split = episode.get("split")
        if split not in {"development", "test_reserved"}:
            raise ValueError("Missing frozen partition")
        company_splits.setdefault(episode["stock_code"], set()).add(split)
        if episode.get("task") != "repurchase_lifecycle":
            raise ValueError("Unexpected task contract")
        if allow_draft and split != "development":
            raise ValueError("Drafts are forbidden for reserved test evaluation")
        if not allow_draft and (episode.get("review_status") != "reviewed" or not episode.get("reviewer", "").strip()):
            raise ValueError("Reference review is required before evaluation")
        gold = episode.get("gold", {})
        if gold.get("repurchase_stage") not in {"NO_EXECUTION_DISCLOSED", "STARTED", "COMPLETED"} or gold.get("cancellation_stage") not in {"INTENDED", "COMPLETED", "NOT_DISCLOSED"}:
            raise ValueError("Unresolved reference state")
        if not set(gold.get("evidence_ids", [])) <= {doc["id"] for doc in eligible_documents(episode)} or not gold.get("evidence_ids"):
            raise ValueError("Missing or future reference evidence")
    if any(len(splits) != 1 for splits in company_splits.values()):
        raise ValueError("Company appears in multiple partitions")
    if len({episode["split"] for episode in episodes}) != 1:
        raise ValueError("Run partitions separately")


def summary(records, episodes):
    result = {"independent_groups": len({episode["independence_group"] for episode in episodes}),
              "cutoffs": len(episodes), "methods": {},
              "inference_limit": "No confidence interval treats cutoffs as independent observations"}
    for method in METHODS:
        rows = [row for row in records if row["method"] == method]
        grouped = {}
        for row in rows:
            grouped.setdefault(row["independence_group"], []).append(row)
        result["methods"][method] = {"answers": len(rows), "correct": sum(row["correct"] for row in rows),
            "accuracy_including_failures": sum(row["correct"] for row in rows) / len(rows),
            "macro_group_accuracy": statistics.mean(sum(r["correct"] for r in group) / len(group) for group in grouped.values()),
            "grounded_correct": sum(row.get("grounded_correct", False) for row in rows),
            "failures": sum(row["status"] != "ok" for row in rows),
            "input_tokens": sum(row["usage"].get("input_tokens", 0) for row in rows),
            "output_tokens": sum(row["usage"].get("output_tokens", 0) for row in rows),
            "groups": {key: {"correct": sum(row["correct"] for row in group), "cutoffs": len(group)} for key, group in grouped.items()}}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--allow-draft", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or args.out.with_suffix(".plan.json").exists():
        parser.error("Use a new output name")
    episodes = read_jsonl(args.episodes)
    validate_episodes(episodes, args.allow_draft)
    frozen = manifest([args.episodes], task="multi_company_lifecycle_comparison", provider="qwen", model="qwen-plus",
        temperature=0, top_k=3, repeats=1, methods=METHODS,
        independent_groups=len({episode["independence_group"] for episode in episodes}),
        split=episodes[0]["split"], human_reviewed=not args.allow_draft,
        costs="cold_start_per_cutoff_including_memory_construction", reference_values_enter_model_prompts=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.with_suffix(".plan.json").write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    client = LiveClient("qwen", "qwen-plus")
    records = []
    for index, episode in enumerate(episodes):
        for method in METHODS[index % 3:] + METHODS[:index % 3]:
            row = evaluate_episode(episode, method, client, top_k=3)
            row["independence_group"] = episode["independence_group"]
            records.append(row)
            with args.out.with_suffix(".progress.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            args.out.with_suffix(".calls.json").write_text(json.dumps(client.calls, ensure_ascii=False), encoding="utf-8")
            print(episode["id"], method, row["status"], flush=True)
    result = summary(records, episodes)
    result["scope"] = "AI_draft_development_only" if args.allow_draft else "reviewed_frozen_partition"
    save_run(args.out, records, result, {**frozen, "calls": client.calls})
    print(json.dumps({"groups": result["independent_groups"], "cutoffs": len(episodes), "calls": len(client.calls)}))


if __name__ == "__main__":
    main()
