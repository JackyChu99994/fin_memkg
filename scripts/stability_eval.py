#!/usr/bin/env python3
"""Repeated-run stability check for selected RealFin-12 methods.

Usage:
    .venv/bin/python scripts/stability_eval.py --repeats 3

Runs the requested methods on every real12 case multiple times, then reports:
- per-repeat accuracy (mean / std)
- majority-vote accuracy per case
- paired Ours vs C1 majority comparison

This is deliberately separate from eval_benchmark.py: it does not overwrite the
main benchmark archive and it never falls back to heuristic rules.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from eval_benchmark import (
    _make_blind_input,
    _normalize_case,
    evaluate_single_case_method,
    load_real_fin_events_12,
)

RUNS_DIR = Path(__file__).resolve().parent.parent / "memory" / "L4_archive" / "runs"
OURS = "Ours: Fin-MemKG (Full: Revision + PricedIn + 2-Hop KG)"
C1 = "Ablation C1: w/o Supply-Chain Prior & KG Edges (Node-Only)"
DEFAULT_METHODS = [OURS, C1]


def majority(votes: list[str]) -> str:
    if not votes:
        return "FAILED"
    counts = Counter(votes)
    top = counts.most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        # tie: be conservative, do not pretend a directional edge
        return "NEUTRAL"
    return top[0][0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--methods", nargs="*", default=DEFAULT_METHODS)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    cases = load_real_fin_events_12()
    if args.limit > 0:
        cases = cases[: args.limit]
    run_id = f"stability_real12_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    records_path = run_dir / "records.jsonl"

    all_records: list[dict] = []
    with records_path.open("w", encoding="utf-8") as fh:
        for method in args.methods:
            for raw_case in cases:
                norm = _normalize_case(raw_case)
                blind = _make_blind_input(raw_case)
                for rep in range(args.repeats):
                    out = evaluate_single_case_method(method, blind, use_cache=False)
                    rec = {
                        "run_id": run_id,
                        "method": method,
                        "case_id": norm["case_id"],
                        "scenario": norm["scenario"],
                        "repeat": rep,
                        "status": out["status"],
                        "pred_dir": out["pred_dir"],
                        "pred_inv_id": out["inv_id"],
                        "ground_truth_t5_direction": norm["ground_truth_t5_direction"],
                        "ground_truth_invalidated_id": norm["ground_truth_invalidated_id"],
                        "car_5d_pct": norm.get("car_5d_pct"),
                        "strategy_car_pct": (
                            None
                            if out["pred_dir"] is None or norm.get("car_5d_pct") is None
                            else (
                                float(norm["car_5d_pct"])
                                if out["pred_dir"] == "BULLISH"
                                else (-float(norm["car_5d_pct"]) if out["pred_dir"] == "BEARISH" else 0.0)
                            )
                        ),
                        "latency_ms": out.get("latency_ms"),
                        "usage": {
                            "prompt_tokens": out.get("prompt_tokens"),
                            "completion_tokens": out.get("completion_tokens"),
                            "estimated_tokens": out.get("estimated_tokens"),
                        },
                        "retry_count": out.get("retry_count"),
                        "finish_reason": out.get("finish_reason"),
                        "error_type": out.get("error_type"),
                        "error": out.get("error"),
                    }
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fh.flush()
                    all_records.append(rec)
                    print(
                        f"[{method.split(':')[0]}] {norm['case_id']} rep={rep} "
                        f"pred={out['pred_dir']} gt={norm['ground_truth_t5_direction']} "
                        f"status={out['status']}",
                        flush=True,
                    )

    summary: dict[str, dict] = {}
    per_case: dict[str, dict] = defaultdict(dict)
    for method in args.methods:
        rows = [r for r in all_records if r["method"] == method]
        repeat_acc: list[float] = []
        for rep in range(args.repeats):
            vals = [r for r in rows if r["repeat"] == rep]
            ok = sum(1 for r in vals if r["pred_dir"] == r["ground_truth_t5_direction"])
            repeat_acc.append(round(ok / max(1, len(vals)) * 100, 1))
        for cid in sorted({r["case_id"] for r in rows}):
            vals = [r for r in rows if r["case_id"] == cid]
            votes = [str(r["pred_dir"] or "FAILED") for r in vals]
            gt = vals[0]["ground_truth_t5_direction"]
            maj = majority(votes)
            strategy = [
                float(r["strategy_car_pct"]) for r in vals if r["strategy_car_pct"] is not None
            ]
            per_case[cid][method] = {
                "votes": votes,
                "majority": maj,
                "gt": gt,
                "majority_correct": maj == gt,
                "mean_strategy_car_pct": round(sum(strategy) / len(strategy), 2) if strategy else None,
            }
        majority_correct = sum(1 for cid in per_case if per_case[cid][method]["majority_correct"])
        summary[method] = {
            "repeats": args.repeats,
            "valid_cases": len(per_case),
            "repeat_acc_pct": repeat_acc,
            "repeat_acc_mean_pct": round(statistics.mean(repeat_acc), 1),
            "repeat_acc_std_pct": round(statistics.pstdev(repeat_acc), 1) if len(repeat_acc) > 1 else 0.0,
            "majority_acc_pct": round(majority_correct / max(1, len(per_case)) * 100, 1),
            "failed_calls": sum(1 for r in rows if r["status"] == "FAILED"),
            "live_calls": sum(1 for r in rows if r["status"] == "SUCCESS"),
            "avg_tokens": round(
                statistics.mean(
                    [
                        (r["usage"]["prompt_tokens"] or 0) + (r["usage"]["completion_tokens"] or 0)
                        for r in rows
                        if r["status"] == "SUCCESS"
                    ]
                ),
                1,
            ) if any(r["status"] == "SUCCESS" for r in rows) else 0,
        }

    paired = {}
    if OURS in per_case[next(iter(per_case))] and C1 in per_case[next(iter(per_case))]:
        wins = losses = ties = 0
        for cid, m in per_case.items():
            a = m[OURS]["majority_correct"]
            b = m[C1]["majority_correct"]
            if a and not b:
                wins += 1
            elif b and not a:
                losses += 1
            else:
                ties += 1
        paired = {"ours_vs_c1_majority": {"wins": wins, "losses": losses, "ties": ties}}

    payload = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "evaluation_mode": "LIVE_LLM_STABILITY_CHECK",
        "methods": args.methods,
        "repeats": args.repeats,
        "summary": summary,
        "paired": paired,
        "per_case": per_case,
    }
    (run_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "summary": summary, "paired": paired}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
