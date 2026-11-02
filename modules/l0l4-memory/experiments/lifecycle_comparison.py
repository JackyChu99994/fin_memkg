"""Known-chain development comparison using original BYD repurchase filings.

AI-drafted references require a new user review; old annotation approval does
not apply. Four cutoffs of one chain are correlated, not four independent events.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from experiments.common import LiveClient, manifest, save_run, sha256, write_jsonl
from experiments.eval_memory import eligible_documents, evaluate_episode

STAGES = [
    ("1219697440", "NO_EXECUTION_DISCLOSED", "INTENDED"),
    ("1219825342", "STARTED", "INTENDED"),
    ("1219909909", "COMPLETED", "INTENDED"),
    ("1220039687", "COMPLETED", "COMPLETED"),
]
METHODS = ["tfidf_rag", "append_memory_archive", "state_memory_archive"]
QUERY = "For 比亚迪's 2024年回购股份方案, what repurchase execution stage and share-cancellation stage have been explicitly disclosed by as_of? Distinguish 拟回购、首次回购、回购实施完毕、股份注销完成. Historical proposed terms do not override later results."


def episodes(cache):
    metadata = json.loads((cache / "official-metadata.json").read_text(encoding="utf-8"))
    by_id = {row["announcementId"]: row for row in metadata}
    docs = []
    for ident, _, _ in STAGES:
        row = by_id[ident]
        disclosure = row["adjunctUrl"].split("/")[1]
        bound = (date.fromisoformat(disclosure) + timedelta(days=1)).isoformat() + "T00:00:00+08:00"
        text = (cache / (ident + ".txt")).read_text(encoding="utf-8")
        if "比亚迪" not in text or len(text) < 500:
            raise ValueError("Invalid extracted source text")
        docs.append({"id": "BYD_" + ident, "stock_code": "002594", "text": text,
            "published_at": bound, "timestamp_semantics": "conservative_date_only_availability_bound_not_first_release",
            "disclosure_date": disclosure, "source_url": "https://static.cninfo.com.cn/" + row["adjunctUrl"],
            "source_sha256": sha256(cache / (ident + ".PDF"))})
    result = []
    for index, (ident, purchase, cancellation) in enumerate(STAGES):
        result.append({"id": "BYD_CUTOFF_" + str(index + 1), "task": "repurchase_lifecycle",
            "memory_protocol": "factual-lifecycle-v2-admission", "answer_protocol": "lifecycle-explicit-intent-v2",
            "event_key": "比亚迪 2024年4亿元A股回购用于注销方案（2024-048）",
            "stock_code": "002594", "query": QUERY, "as_of": docs[index]["published_at"],
            "documents": docs, "review_status": "ai_draft_pending_user_review",
            "reference_origin": "assistant_source_reading_not_independent_human_annotation",
            "gold": {"repurchase_stage": purchase, "cancellation_stage": cancellation,
                     "evidence_ids": ["BYD_" + ident]},
            "independence_group": "BYD_2024_REPURCHASE_SINGLE_CHAIN"})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.out.exists() or args.out.with_suffix(".plan.json").exists():
        parser.error("Use a new output name; never overwrite a frozen run")
    cases = episodes(args.cache)
    for index, case in enumerate(cases):
        if len(eligible_documents(case)) != index + 1:
            raise ValueError("Incorrect point-in-time document eligibility")
    dataset = args.out.with_suffix(".episodes.jsonl")
    if dataset.exists():
        parser.error("Dataset snapshot already exists")
    write_jsonl(dataset, cases)
    inputs = [dataset, args.cache / "official-metadata.json"]
    inputs += [args.cache / (ident + suffix) for ident, _, _ in STAGES for suffix in (".PDF", ".txt")]
    frozen = manifest(inputs, task="repurchase_lifecycle_development", methods=METHODS,
        model="qwen-plus", provider="qwen", temperature=0, top_k=3, repeats=1,
        independent_chains=1, correlated_cutoffs=4, heldout=False, human_reviewed=False,
        memory_protocol="factual-lifecycle-v2-admission", answer_protocol="lifecycle-explicit-intent-v2",
        costs="cold_start_includes_all_model_memory_building_calls", no_return_labels=True)
    args.out.with_suffix(".plan.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.prepare_only:
        print("Prepared four cutoffs of one chain; no model calls")
        return
    client = LiveClient("qwen", "qwen-plus")
    records = []
    progress = args.out.with_suffix(".progress.jsonl")
    for index, case in enumerate(cases):
        ordered = METHODS[index % 3:] + METHODS[:index % 3]
        for method in ordered:
            row = evaluate_episode(case, method, client, top_k=3)
            records.append(row)
            with progress.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            args.out.with_suffix(".calls.json").write_text(json.dumps(client.calls, ensure_ascii=False, indent=2), encoding="utf-8")
            print(case["id"], method, row["status"], row["correct"], flush=True)
    summary = {"scope": "AI_draft_known_chain_development_only", "independent_chains": 1,
               "correlated_cutoffs": 4, "total_calls": len(client.calls), "methods": {}}
    for method in METHODS:
        rows = [row for row in records if row["method"] == method]
        summary["methods"][method] = {"answers": len(rows), "correct_both_stages": sum(row["correct"] for row in rows),
            "grounded_correct": sum(row.get("grounded_correct", False) for row in rows),
            "failures": sum(row["status"] != "ok" for row in rows),
            "input_tokens": sum(row["usage"].get("input_tokens", 0) for row in rows),
            "output_tokens": sum(row["usage"].get("output_tokens", 0) for row in rows)}
    save_run(args.out, records, summary, {**frozen, "calls": client.calls})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
