"""Read-only snapshot audit and independent scalar recomputation of every task_01 candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import market_snapshot as ms


def independently_select(frame: pd.DataFrame) -> tuple[bool, list[str]]:
    """Separate scalar arithmetic implementation; no validator indicator functions imported."""
    rows = frame.sort_values("date").tail(120).to_dict("records")
    if len(rows) < 60:
        return False, []
    prices = [float(row["close"]) for row in rows]
    volumes = [float(row["volume"]) for row in rows]
    fast = slow = prices[0]
    signal, prior_dif, prior_signal = 0.0, 0.0, 0.0
    gain = loss = None
    prior_rsi = None
    armed, crossed_macd, spike_count, joint = False, False, 0, []
    for i, row in enumerate(rows):
        price = prices[i]
        if i:
            fast = fast + 2 / 13 * (price - fast)
            slow = slow + 2 / 27 * (price - slow)
        dif = fast - slow
        signal = signal + 2 / 10 * (dif - signal)
        strength = None
        if i == 14:
            changes = [prices[j] - prices[j - 1] for j in range(1, 15)]
            gain = sum(max(x, 0) for x in changes) / 14
            loss = sum(max(-x, 0) for x in changes) / 14
        elif i > 14:
            change = price - prices[i - 1]
            gain = (gain * 13 + max(change, 0)) / 14
            loss = (loss * 13 + max(-change, 0)) / 14
        if gain is not None:
            strength = 50 if gain == loss == 0 else (100 if loss == 0 else 100 * gain / (gain + loss))
        if "2026-03-04" <= row["date"] <= "2026-03-31":
            crossed_macd |= prior_dif <= prior_signal and dif > signal
            previous_volume_mean = sum(volumes[i-5:i]) / 5 if i >= 5 else 0
            spike = previous_volume_mean > 0 and volumes[i] > 2 * previous_volume_mean
            spike_count += int(spike)
            recovered = False
            if strength is not None:
                if strength < 30:
                    armed = True
                elif armed and prior_rsi is not None and prior_rsi <= 50 < strength:
                    recovered, armed = True, False
                prior_rsi = strength
            ma_cross = (i >= 8
                        and sum(prices[i-5:i])/5 <= sum(prices[i-8:i])/8
                        and sum(prices[i-4:i+1])/5 > sum(prices[i-7:i+1])/8)
            if recovered and spike and ma_cross:
                joint.append(row["date"])
        prior_dif, prior_signal = dif, signal
    return bool(crossed_macd and spike_count >= 2 and joint), joint


def audit(data_dir: Path) -> dict:
    started = time.perf_counter()
    paths = ms.snapshot_paths(data_dir)
    bars = pd.read_parquet(paths["bars"])
    universe = pd.read_parquet(paths["universe"])
    index = pd.read_parquet(paths["index"])
    dated = ms.load_universe("2026-03-31", data_dir=data_dir)
    valid_codes = dated.loc[dated["code"].str.startswith("300"), "code"].tolist()
    task_bars = ms.load_bars("2026-03-31", codes=valid_codes, data_dir=data_dir)
    evidence_path = data_dir / "acceptance" / "task01" / "evidence.json"
    evidence = {row["code"]: row for row in json.loads(evidence_path.read_text(encoding="utf-8"))}
    mismatches, selected, recomputed = [], [], set()
    for code, frame in task_bars.groupby("code"):
        recomputed.add(code)
        hit, joint = independently_select(frame)
        if hit:
            selected.append(code)
        original = evidence.get(code)
        if original is None or hit != original["selected"] or (original.get("eligible_history") and joint != original["joint_signal_dates"]):
            mismatches.append(code)
    future_rows = int((task_bars["date"] > "2026-03-31").sum())
    report = {
        "snapshot": {"rows": len(bars), "stocks": int(bars["code"].nunique()),
                     "date_min": bars["date"].min(), "date_max": bars["date"].max(),
                     "duplicate_code_date": int(bars.duplicated(["code", "date"]).sum()),
                     "missing_ohlcv": {key: int(bars[key].isna().sum()) for key in ["open", "high", "low", "close", "volume"]},
                     "turnover_non_null_pct": round(float(bars["turnover_pct"].notna().mean() * 100), 2),
                     "turnover_negative_rows": int((bars["turnover_pct"] < 0).sum()),
                     "universe_count": len(universe), "index_rows": len(index)},
        "temporal": {"as_of": "2026-03-31", "universe_count": len(dated),
                     "excluded_post_cutoff_listings": len(universe) - len(dated),
                     "future_rows_returned": future_rows,
                     "historical_universe_complete": False},
        "independent_task01": {"stocks_recomputed": len(recomputed), "selected_codes": selected,
                               "missing_requested_codes": sorted(set(valid_codes) - recomputed),
                               "evidence_code_set_matches": set(evidence) == recomputed,
                               "mismatches": mismatches, "implementation": "separate scalar arithmetic, no shared indicator functions"},
        "network_requests": 0, "elapsed_seconds": round(time.perf_counter() - started, 4),
    }
    report["passed"] = (not mismatches and not future_rows and set(valid_codes) == recomputed == set(evidence)
                        and not report["snapshot"]["duplicate_code_date"]
                        and not any(report["snapshot"]["missing_ohlcv"].values()))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ms.DATA_DIR)
    parser.add_argument("--output", type=Path, default=ms.DATA_DIR / "acceptance" / "audit.json")
    args = parser.parse_args()
    result = audit(args.data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
