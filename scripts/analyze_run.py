#!/usr/bin/env python3
"""Print a per-case and paired comparison report for one LIVE_LLM_BENCHMARK run.

Usage:
    .venv/bin/python scripts/analyze_run.py memory/L4_archive/runs/<run_id>

The script is read-only: it never calls the API and never modifies the run.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path

METHOD_SHORT = {
    "B0: 20-Day Price Momentum Baseline (±3% Threshold, 0-Token)": "B0",
    "B1: Long-History Context + LLM (Full-Text)": "B1",
    "B2: Lexical Top-K Retrieval + LLM (Char-Bigram Top-3)": "B2",
    "B2+Prior: Lexical Top-K + Supply-Chain Text Prior + LLM (Top-3)": "B2+Prior",
    "Ablation A: w/o Invalidation Only": "Abl-A",
    "Ablation B: w/o Priced-in Only": "Abl-B",
    "Ablation C1: w/o Supply-Chain Prior & KG Edges (Node-Only)": "Abl-C1",
    "Ablation C2: 1-Hop KG Only (cutoff=1)": "Abl-C2",
    "Ours: Fin-MemKG (Full: Revision + PricedIn + 2-Hop KG)": "Ours",
}
DIR_SHORT = {"BULLISH": "BULL", "BEARISH": "BEAR", "NEUTRAL": "NEUT"}


def short(method: str) -> str:
    return METHOD_SHORT.get(method, method.split(":")[0][:10])


def sign(x: float) -> int:
    return 1 if x > 0 else (-1 if x < 0 else 0)


def mcnemar_exact_p(wins: int, losses: int) -> float:
    """Two-sided exact binomial p-value for discordant pairs."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)


def bootstrap_mean_ci(values: list[float], n_boot: int = 1000, seed: int = 42) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        return (values[0], values[0])
    rng = random.Random(seed)
    means = []
    n = len(values)
    for _ in range(n_boot):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return (means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    run_dir: Path = args.run_dir
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    records = [json.loads(line) for line in (run_dir / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

    print(f"run_id={manifest.get('run_id')} mode={manifest.get('evaluation_mode')}")
    print(f"dataset={manifest.get('dataset')} N={manifest.get('sample_count')} scenarios={manifest.get('scenario_counts')}")
    print(f"model={manifest.get('model_name')} params={manifest.get('generation_params')}")

    print("\n== Summary ==")
    header = f"{'method':<12} {'valid/fail':>10} {'acc':>7} {'macroF1':>8} {'nodeF1':>7} {'LS_CAR':>8} {'tokens':>7} {'lat_ms':>8}"
    print(header)
    print("-" * len(header))
    for m, st in payload["summary"].items():
        print(
            f"{short(m):<12} {st.get('valid_cases',0):>5}/{st.get('failed_cases',0):<4} "
            f"{st.get('t5_acc_over_all_pct',0):>6.1f}% {st.get('macro_f1_pct',0):>7.1f}% "
            f"{st.get('f1_pct',0):>6.1f}% {st.get('long_short_car_pct') or 0:>+7.2f}% "
            f"{st.get('avg_total_tokens') or 0:>7.0f} {st.get('avg_latency_ms') or 0:>8.0f}"
        )

    print("\n== Per-case (pred_dir / invalidation hit) ==")
    methods = list(payload["summary"].keys())
    by_case: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in records:
        by_case[r["case_id"]][r["method"]] = r
    case_ids = sorted(by_case)
    short_methods = [short(m) for m in methods]
    print("case        gt        car      " + " ".join(f"{s:>10}" for s in short_methods))
    print("  (BULL/BEAR/NEUT + node-hit; '-' = wrong/missing invalidation id)")
    for cid in case_ids:
        first = next(iter(by_case[cid].values()))
        gt = first["ground_truth_t5_direction"]
        car = first.get("car_5d_pct")
        cells = []
        for m in methods:
            r = by_case[cid].get(m)
            if not r:
                cells.append("MISSING")
                continue
            pred = DIR_SHORT.get(r.get("pred_dir"), "FAIL")
            inv_hit = r.get("pred_inv_id") == r.get("ground_truth_invalidated_id") and r.get("pred_inv_id") is not None
            cells.append(f"{pred}{'+' if inv_hit else '-'}")
        print(f"{cid:<11} {gt:<9} {car if car is not None else 0:>+7.2f}  " + " ".join(f"{c:>10}" for c in cells))

    print("\n== Paired vs Ours (direction correctness; exact McNemar) ==")
    ours = "Ours: Fin-MemKG (Full: Revision + PricedIn + 2-Hop KG)"
    for other in methods:
        if other == ours:
            continue
        wins = losses = ties = 0
        delta_car: list[float] = []
        for cid in case_ids:
            a, b = by_case[cid].get(ours), by_case[cid].get(other)
            if not a or not b:
                continue
            a_ok = a.get("pred_dir") == a.get("ground_truth_t5_direction")
            b_ok = b.get("pred_dir") == b.get("ground_truth_t5_direction")
            if a_ok and not b_ok:
                wins += 1
            elif b_ok and not a_ok:
                losses += 1
            else:
                ties += 1
            av = a.get("strategy_car_pct")
            bv = b.get("strategy_car_pct")
            if av is not None and bv is not None:
                delta_car.append(float(av) - float(bv))
        p = mcnemar_exact_p(wins, losses)
        lo, hi = bootstrap_mean_ci(delta_car)
        print(f"vs {short(other):<10} wins={wins:>2} losses={losses:>2} ties={ties:>2} p={p:.3f}  dCAR={sum(delta_car)/len(delta_car):+.2f}% CI[{lo:+.2f},{hi:+.2f}]" if delta_car else f"vs {short(other):<10} wins={wins:>2} losses={losses:>2} ties={ties:>2} p={p:.3f}")

    print("\n== Scenario accuracy (from summary) ==")
    for m, sc in payload.get("by_scenario", {}).items():
        print(f"{short(m):<10} " + "  ".join(f"{k}={v}" for k, v in sc.items()))

    failed = [r for r in records if r.get("status") == "FAILED"]
    retries = [r for r in records if (r.get("retry_count") or 0) > 0]
    print(f"\nfailed_records={len(failed)} retry_records={len(retries)}")
    if failed:
        for r in failed[:10]:
            print(f"  FAILED {r.get('case_id')} {short(r.get('method',''))}: {r.get('error_type')} {r.get('error')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
