"""Targeted live development regression; never a new held-out accuracy study."""
import argparse
import json
from pathlib import Path

from experiments.common import LiveClient, manifest, read_jsonl, save_run
from experiments.eval_memory import MEMORY_PROTOCOL, evaluate_episode
from experiments.reviewed_comparison import derive_episodes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new output directory")
    # Predeclared regressions cover mixed metrics and lost repurchase evidence.
    episodes = [episode for episode in derive_episodes(read_jsonl(args.corpus), read_jsonl(args.labels)) if episode["stock_code"] in {"002594", "300750"}]
    frozen_manifest = manifest([args.corpus, args.labels], task="targeted_repair_smoke",
        protocol=MEMORY_PROTOCOL, model="qwen-plus", provider="qwen", held_out=False)
    client = LiveClient("qwen", "qwen-plus")
    rows = []
    for episode in episodes:
        for method in ("tfidf_rag", "state_memory_archive"):
            row = evaluate_episode(episode, method, client)
            row.update(reference_direction=episode["gold"]["direction"], repeat=1)
            rows.append(row)
            print(f"{episode['id']} {method}: status={row['status']} correct={row['correct']} archive_sources={len(row.get('archive_document_ids', []))}", flush=True)
    summary = {"scope": "known_development_case_engineering_regression_not_new_benchmark",
        "episodes": len(episodes), "predictions": len(rows), "failures": sum(row["status"] != "ok" for row in rows),
        "calls": len(client.calls), "correct": sum(row["correct"] for row in rows),
        "input_tokens": sum(call["usage"].get("input_tokens", 0) for call in client.calls),
        "output_tokens": sum(call["usage"].get("output_tokens", 0) for call in client.calls),
        "memory_gain_claim": False}
    save_run(args.out, rows, summary, {**frozen_manifest, "calls": client.calls})
    print(json.dumps(summary, indent=2))
    return 2 if summary["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
