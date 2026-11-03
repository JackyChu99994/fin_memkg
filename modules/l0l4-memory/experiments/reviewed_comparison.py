"""Repeated RAG comparison with references mechanically derived from reviewed facts.

Derivation is explicit and checked before any model calls. It is not an
independently annotated or held-out episode benchmark.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from experiments.common import LiveClient, manifest, read_jsonl, reviewed_labels, save_run, sha256, write_jsonl
from experiments.eval_memory import MEMORY_PROTOCOL, evaluate_episode

SPECS = {
    "300750": {"name": "宁德时代", "reference_doc": "NEWS_e8631978f487a3b6", "targets": None,
        "query": "For 宁德时代, does its latest explicit 回购 disclosure express a positive repurchase/shareholder-return intention? BULLISH means explicit positive intention; BEARISH means explicit cancellation or contrary business change; NEUTRAL means insufficient or conflicting business evidence. Ignore share-price and fund-flow statistics. Distinguish planned cancellation from completion. Do not predict returns."},
    "002594": {"name": "比亚迪", "reference_doc": "NEWS_51457e0845fb96b6", "targets": None,
        "query": "For 比亚迪, consider the disclosed 国内动力电池市占率 and 海外装车量 business signals. Return NEUTRAL if positive and negative changes coexist, BULLISH if only positive signals exist, BEARISH if only negative signals exist. Ignore pure prices and other companies' financial results. Do not predict returns."},
    "300308": {"name": "中际旭创", "reference_doc": "NEWS_1669d1d12450237d", "targets": None,
        "query": "What does the latest provided 中际旭创 business announcement explicitly say about 客户订单需求 and 在手订单? Strong/full demand is BULLISH, explicit falling orders are BEARISH, and absent evidence is NEUTRAL. Ignore financing balances, share prices and trading turnover. Do not predict returns."},
    "300502": {"name": "新易盛", "reference_doc": "NEWS_a2552e208f0bf2f5", "targets": None,
        "query": "Has 新易盛 explicitly disclosed a positive 回购 plan or proposal in the provided evidence? A clear repurchase intention is BULLISH; an explicit cancellation is BEARISH; absent or conflicting evidence is NEUTRAL. Distinguish proposals, announced plans and actual execution. Do not infer from share-price changes or predict returns."},
    "002466": {"name": "天齐锂业", "reference_doc": "NEWS_c2b9870ed8decdb9",
        "targets": ["第三季度净利润同比增长", "第三季度净利润环比下降"],
        "query": "In the latest provided 天齐锂业 第三季度 financial results, do 利润同比 and 利润环比 changes have the same sign? Positive and negative changes together mean NEUTRAL; only positive means BULLISH; only negative means BEARISH. Ignore earlier forecasts, holdings and prices. Different comparison bases do not invalidate each other. Do not predict returns."},
}


def direction_from_relations(relations):
    signs = set(relations)
    if not signs or not signs <= {"利好事件", "利空事件"}:
        raise ValueError("Reference requires reviewed positive/negative event facts")
    return "NEUTRAL" if len(signs) == 2 else "BULLISH" if "利好事件" in signs else "BEARISH"


def fact_key(event):
    return (event["source"], event["relation"], event["target"], event.get("event_phase", "reported"))


def derive_episodes(corpus, annotations):
    reviewed = reviewed_labels(corpus, annotations)
    documents = {doc["id"]: doc for doc in corpus}
    episodes = []
    for code, spec in sorted(SPECS.items()):
        ref = reviewed[spec["reference_doc"]]
        facts = [event for event in ref["events"] if event["source"] == spec["name"]
                 and (spec["targets"] is None or event["target"] in spec["targets"])]
        direction = direction_from_relations(event["relation"] for event in facts)
        groups = []
        for fact in facts:
            same_event = ref.get("event_group", ref["id"])
            supporting = sorted(label["id"] for label in annotations
                if label.get("event_group", label["id"]) == same_event
                and any(fact_key(event) == fact_key(fact) for event in label["events"]))
            if not supporting:
                raise ValueError("A derived fact has no supporting reviewed source")
            if supporting not in groups:
                groups.append(supporting)
        docs = []
        for doc in corpus:
            if doc["stock_code"] != code:
                continue
            stamp = datetime.fromisoformat(doc["published_at"])
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
            docs.append({"id": doc["id"], "text": doc["text"], "published_at": stamp.isoformat(),
                         "stock_code": code, "source_url": doc["source_url"]})
        docs.sort(key=lambda doc: (doc["published_at"], doc["id"]))
        if not docs or not set().union(*(set(group) for group in groups)) <= {doc["id"] for doc in docs}:
            raise ValueError("Derived evidence must exist in the episode's raw documents")
        episodes.append({"id": f"DERIVED_EP_{code}", "stock_code": code, "query": spec["query"],
            "as_of": docs[-1]["published_at"], "documents": docs,
            "reference_origin": "deterministically_derived_from_user_reviewed_extraction",
            "review_status": "derived_reference_not_independent_episode_annotation",
            "reference_fact_document": spec["reference_doc"], "reference_facts": facts,
            "gold": {"direction": direction, "evidence_groups": groups,
                     "evidence_ids": sorted({group[0] for group in groups})}})
    return episodes


def wilson(correct, total):
    if not total:
        return None
    z = 1.959963984540054
    proportion = correct / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    half = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return [max(0, center - half), min(1, center + half)]


def summarize(records):
    methods = sorted({row["method"] for row in records})
    episode_ids = sorted({row["id"] for row in records})
    result = {"unique_episodes": len(episode_ids), "methods": {}, "paired_majority": {},
              "scope": "development_set_with_mechanically_derived_reviewed_fact_references"}
    majority = {}
    for method in methods:
        rows = [row for row in records if row["method"] == method]
        repeats = sorted({row["repeat"] for row in rows})
        per_repeat = [sum(row["correct"] for row in rows if row["repeat"] == repeat) /
                      sum(row["repeat"] == repeat for row in rows) for repeat in repeats]
        voted = {}
        for episode in episode_ids:
            subset = [row for row in rows if row["id"] == episode]
            votes = [row.get("prediction", {}).get("direction") for row in subset]
            candidates = [direction for direction in ("BULLISH", "BEARISH", "NEUTRAL") if votes.count(direction) > len(votes) / 2]
            direction = candidates[0] if candidates else None
            voted[episode] = {"direction": direction,
                "correct": direction is not None and direction == subset[0]["reference_direction"]}
        majority[method] = voted
        correct = sum(row["correct"] for row in voted.values())
        evidence_rows = [row for row in rows if row.get("required_evidence_recall") is not None]
        input_tokens = sum(row["usage"]["input_tokens"] for row in rows)
        output_tokens = sum(row["usage"]["output_tokens"] for row in rows)
        result["methods"][method] = {
            "predictions": len(rows), "failures": sum(row["status"] != "ok" for row in rows),
            "per_repeat_accuracy": per_repeat, "mean_accuracy": statistics.mean(per_repeat),
            "sample_std_accuracy": statistics.stdev(per_repeat) if len(per_repeat) > 1 else None,
            "majority_correct": correct, "majority_total": len(episode_ids),
            "majority_accuracy": correct / len(episode_ids),
            "majority_wilson95_descriptive": wilson(correct, len(episode_ids)),
            "majority_predictions": voted,
            "grounded_correct_predictions": sum(bool(row.get("grounded_correct")) for row in rows),
            "mean_required_evidence_recall": statistics.mean(row["required_evidence_recall"] for row in evidence_rows) if evidence_rows else None,
            "invalid_citation_ids": sum(len(row.get("invented_evidence_ids", [])) for row in rows),
            "input_tokens_including_build": input_tokens, "output_tokens_including_build": output_tokens,
            "mean_total_tokens_including_build": (input_tokens + output_tokens) / len(rows),
            "live_calls": sum(row["calls"] for row in rows),
            "mean_latency_seconds_including_build": statistics.mean(row["elapsed_seconds"] for row in rows)}
    for memory_method in ("state_memory", "state_memory_archive"):
        if memory_method not in majority:
            continue
        for baseline in ("full_text", "tfidf_rag", "append_memory_archive"):
            if baseline not in majority:
                continue
            wins = sum(majority[memory_method][episode]["correct"] and not majority[baseline][episode]["correct"] for episode in episode_ids)
            losses = sum(not majority[memory_method][episode]["correct"] and majority[baseline][episode]["correct"] for episode in episode_ids)
            n = wins + losses
            p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(wins, losses) + 1)) / 2 ** n) if n else 1.0
            result["paired_majority"][f"{memory_method}_vs_{baseline}"] = {"wins": wins, "losses": losses,
                "ties": len(episode_ids) - n, "exact_mcnemar_p": p, "independent_units_assumed": len(episode_ids)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--provider", choices=["qwen", "deepseek"], default="qwen")
    parser.add_argument("--model", default="qwen-plus")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--methods", nargs="+", choices=["full_text", "tfidf_rag", "state_memory", "append_memory_archive", "state_memory_archive"],
                        default=["full_text", "tfidf_rag", "state_memory"])
    args = parser.parse_args()
    plan_path = args.out.with_suffix(".plan.json")
    progress_path = args.out.with_suffix(".progress.jsonl")
    if args.out.exists() or plan_path.exists() or progress_path.exists() or args.repeats < 1 or args.top_k < 1:
        parser.error("Use a fresh output name and positive repeats/top-k")
    if len(set(args.methods)) != len(args.methods) or len(args.methods) < 2 or "tfidf_rag" not in args.methods:
        parser.error("Select distinct methods including tfidf_rag and at least one comparator")
    episodes = derive_episodes(read_jsonl(args.corpus), read_jsonl(args.labels))
    plan = manifest([args.corpus, args.labels], task="repeated_rag_comparison", protocol=MEMORY_PROTOCOL,
        reference_derivation="positive-only=BULLISH; negative-only=BEARISH; both=NEUTRAL; no future returns",
        independent_episode_annotation=False, episode_count=len(episodes), repeats=args.repeats,
        provider=args.provider, model=args.model, temperature=0, top_k=args.top_k, methods=args.methods,
        retrieval="character_bigram_tfidf_cosine_not_neural_embedding", episodes=episodes)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    client = LiveClient(args.provider, args.model)
    records = []
    methods = args.methods
    for repeat in range(args.repeats):
        for episode in episodes:
            for method in methods[repeat % len(methods):] + methods[:repeat % len(methods)]:
                row = evaluate_episode(episode, method, client, args.top_k)
                row.update(repeat=repeat + 1, reference_direction=episode["gold"]["direction"])
                records.append(row)
                with progress_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                args.out.with_suffix(".calls.json").write_text(json.dumps(client.calls, ensure_ascii=False), encoding="utf-8")
                print(f"{len(records)}/{len(episodes) * len(methods) * args.repeats} repeat={repeat+1} {episode['id']} {method} status={row['status']} calls={row['calls']}", flush=True)
    summary = summarize(records)
    completed_manifest = {**plan, "calls": client.calls, "episodes": None,
        "provider_response_models": sorted({call.get("response_model") for call in client.calls if call.get("response_model")})}
    save_run(args.out, records, summary, completed_manifest)
    write_jsonl(args.out / "episodes.jsonl", episodes)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if any(row["status"] != "ok" for row in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
