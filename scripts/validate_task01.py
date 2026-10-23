"""Offline RealFin task_01 acceptance, with RSI14, same-day evidence and official grading."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import market_snapshot as ms
from scripts.realfin_contract import grade_task, load_task

AS_OF = "2026-03-31"
WINDOW_START = "2026-03-04"
LOOKBACK = 120
TASK_ID = "task_01_macd_rsi_filter"


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    dif = ema(close, 12) - ema(close, 26)
    return dif, ema(dif, 9)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder smoothing, seeded with the first period arithmetic gain/loss means."""
    if period < 1:
        raise ValueError("RSI period must be positive")
    values = close.astype(float).tolist()
    output = [float("nan")] * len(values)
    if len(values) <= period:
        return pd.Series(output, index=close.index)
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gain = sum(max(x, 0) for x in changes[:period]) / period
    loss = sum(max(-x, 0) for x in changes[:period]) / period
    for i in range(period, len(values)):
        if i > period:
            gain = (gain * (period - 1) + max(changes[i - 1], 0)) / period
            loss = (loss * (period - 1) + max(-changes[i - 1], 0)) / period
        output[i] = 50.0 if gain == loss == 0 else (100.0 if loss == 0 else 100 - 100 / (1 + gain / loss))
    return pd.Series(output, index=close.index)


def rebound_signals(values: pd.Series) -> pd.Series:
    """One first >50 crossing per oversold cycle; a new <30 observation resets it."""
    result = pd.Series(False, index=values.index)
    armed, previous = False, float("nan")
    for day, value in values.items():
        if pd.notna(value):
            if value < 30:
                armed = True
            elif armed and previous <= 50 < value:
                result.loc[day] = True
                armed = False
            previous = value
    return result


def evaluate_stock(frame: pd.DataFrame) -> dict:
    frame = frame.sort_values("date").set_index("date").tail(LOOKBACK)
    close, volume = frame["close"].astype(float), frame["volume"].astype(float)
    if len(frame) < 60:
        return {"eligible_history": False, "selected": False}
    dif, dea = macd(close)
    strength = rsi(close)
    ma5, ma8 = close.rolling(5).mean(), close.rolling(8).mean()
    average = volume.rolling(5).mean().shift(1)
    macd_cross = ((dif.shift(1) <= dea.shift(1)) & (dif > dea)).loc[WINDOW_START:AS_OF]
    ma_cross = ((ma5.shift(1) <= ma8.shift(1)) & (ma5 > ma8)).loc[WINDOW_START:AS_OF]
    rebound = rebound_signals(strength.loc[WINDOW_START:AS_OF])
    spike = ((volume > 2 * average) & (average > 0)).loc[WINDOW_START:AS_OF]
    joint = rebound & ma_cross & spike
    selected = bool(macd_cross.any() and spike.sum() >= 2 and joint.any())
    signal_dates = joint.index[joint].tolist()
    return {
        "eligible_history": True, "selected": selected, "history_rows": len(frame),
        "macd_cross_dates": macd_cross.index[macd_cross].tolist(),
        "rsi_rebound_dates": rebound.index[rebound].tolist(),
        "ma_cross_dates": ma_cross.index[ma_cross].tolist(),
        "volume_spike_days": int(spike.sum()), "joint_signal_dates": signal_dates,
        "signals": [
            {"date": day, "rsi14": float(strength.loc[day]), "volume": float(volume.loc[day]),
             "previous_5_volume_mean": float(average.loc[day]),
             "ma5": float(ma5.loc[day]), "ma8": float(ma8.loc[day])}
            for day in signal_dates
        ],
    }


def run(data_dir: Path | None = None) -> dict:
    data_dir = Path(data_dir or ms.DATA_DIR)
    universe = ms.load_universe(AS_OF, data_dir=data_dir)
    codes = universe.loc[universe["code"].str.startswith("300"), "code"].tolist()
    bars = ms.load_bars(AS_OF, codes=codes, data_dir=data_dir)
    if bars.empty:
        raise RuntimeError("No cached OHLCV at the task cutoff")
    missing_codes = sorted(set(codes) - set(bars["code"]))
    evidence, hits = [], []
    for code, frame in bars.groupby("code", sort=True):
        row = {"code": code, **evaluate_stock(frame)}
        evidence.append(row)
        if row["selected"]:
            hits.append(row)
    hits.sort(key=lambda item: (-item["volume_spike_days"], item["code"]))
    return {
        "as_of": AS_OF, "window": [WINDOW_START, AS_OF], "profile": "official_expected_plus_prompt",
        "rsi_period": 14, "lookback_per_stock": LOOKBACK, "universe_count": len(codes),
        "missing_codes": missing_codes, "coverage_complete": not missing_codes,
        "evaluated_count": len(evidence), "candidate_count": len(hits), "hits": hits,
        "evidence": evidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ms.DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=ms.DATA_DIR / "acceptance" / "task01")
    args = parser.parse_args()
    started = time.perf_counter()
    task = load_task(TASK_ID)
    result = run(args.data_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    codes = [row["code"] for row in result["hits"][:10]]
    (args.output_dir / "result.txt").write_text("\n".join(codes) + ("\n" if codes else ""), encoding="utf-8")
    result_written_seconds = time.perf_counter() - started
    transcript = [
        {"operation": "read_cached_ohlcv", "as_of": AS_OF, "universe_count": result["universe_count"],
         "evaluated_stocks": result["evaluated_count"], "network_requests": 0},
        {"operation": "calculate_indicators", "indicators": ["MACD(12,26,9)", "RSI14 Wilder", "MA5", "MA8"],
         "volume_rule": "volume > 2 * previous five observations mean, excluding today",
         "signal_rule": "same-day RSI first rebound >50, MA5/MA8 crossing, volume spike",
         "candidate_count": len(result["hits"]), "written_codes": codes},
    ]
    grading = grade_task(TASK_ID, transcript, args.output_dir)
    reference = task["reference_ans"].splitlines()
    summary = {
        **{k: v for k, v in result.items() if k not in {"hits", "evidence"}},
        "written_codes": codes, "reference_overlap": sorted(set(codes) & set(reference)),
        "result_written_seconds": round(result_written_seconds, 4),
        "timeout_seconds": task["timeout_seconds"], "network_requests": 0,
        "grading": grading,
        "limitations": [
            "Current surviving-stock universe; historical delisted securities are unavailable.",
            "Cached qfq prices are not a historical point-in-time adjustment-factor archive.",
            "Official prompt and expected_behavior differ; this profile applies both the window MACD/two-volume-day requirements and the same-day RSI14/MA/volume requirement.",
            "Zero qualifying stocks are a valid computed outcome, but the official valid_codes check scores an empty file as zero.",
        ],
    }
    for name, value in [("summary.json", summary), ("transcript.json", transcript),
                        ("evidence.json", result["evidence"])]:
        (args.output_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    elapsed = time.perf_counter() - started
    summary.update(elapsed_seconds=round(elapsed, 4), within_timeout=elapsed < task["timeout_seconds"])
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["within_timeout"] or not summary["coverage_complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
