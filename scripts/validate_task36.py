"""离线验收 task_36；真实历史分钟不足时按题目许可作日线近似，保留限制。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import market_snapshot as ms
from market_intraday import (
    IntradayCoverageError, attach_continuation, daily_approximation,
    detect_minute_signals, load_intraday,
)
from scripts.realfin_contract import grade_task, load_task

TASK_ID = "task_36_intraday_anomaly"
AS_OF = "2024-08-22"


def run(data_dir: Path, out_dir: Path, *, mode: str = "auto", codes: list[str] | None = None) -> dict:
    started = time.perf_counter()
    task = load_task(TASK_ID)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = ms.load_index(AS_OF, lookback=15, data_dir=data_dir)
    calendar = sorted(index["date"].astype(str).unique())
    if len(calendar) < 10 or calendar[-1] != AS_OF:
        raise ValueError("index calendar must cover at least ten trading dates through task as_of")
    dates = calendar[-5:]
    daily = ms.load_bars(AS_OF, codes=codes, data_dir=data_dir, start_date=calendar[0])
    universe = ms.load_universe(AS_OF, codes=codes, data_dir=data_dir)
    available_codes = universe["code"].tolist()
    if daily.empty:
        raise ValueError("daily snapshot is empty")
    probe_path = data_dir / "intraday" / "probe_report.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8")) if probe_path.exists() else None
    transcript = [{"role": "tool", "content": json.dumps({
        "operation": "load_cached_intraday_probe_evidence",
        "path": str(probe_path), "report": probe,
        "note": "Saved actual GET results; no network requests in this timed validation.",
    }, ensure_ascii=False)}]
    coverage, reason = {}, None
    if mode == "daily":
        actual_mode = "DAILY_OHLC_APPROX"
        reason = "explicit daily approximation requested"
    else:
        try:
            intraday, coverage = load_intraday(available_codes, AS_OF, dates, data_dir=data_dir / "intraday")
            actual_mode = "MINUTE_30"
        except IntradayCoverageError as exc:
            if mode == "minute":
                raise
            actual_mode = "DAILY_OHLC_APPROX"
            coverage = json.loads(str(exc))
            reason = "Historical 30-minute cache incomplete; task prompt explicitly permits daily OHLC approximation."
    if actual_mode == "MINUTE_30":
        candidates = detect_minute_signals(intraday, AS_OF)
        # Minute caches are unadjusted. Never compare these lows against daily qfq prices.
        confirmation_daily = intraday.assign(date=intraday["timestamp"].dt.strftime("%Y-%m-%d"))
        confirmation_daily = confirmation_daily.groupby(["code", "date"], as_index=False).agg(close=("close", "last"))
        method = "30-minute close/previous close; volume > 5x preceding SAME-DAY interval mean; two rising bars recover V-drop."
    else:
        candidates = daily_approximation(daily, AS_OF, dates)
        confirmation_daily = daily
        method = ("DAILY_OHLC_APPROX: (high-low)/previous_close > 8% OR lower wick/range > 50%; "
                  "closing position > 60%; volume > 3x prior 5-day mean. "
                  "Cannot establish 30-minute path, >5x same-day interval volume, or two-bar recovery.")
    evaluated = attach_continuation(candidates, confirmation_daily, AS_OF, calendar)
    confirmed = [row for row in evaluated if row["continuation"] == "是"]
    output = ["股票代码,异动日期,异动类型,异动幅度(%),当日收盘位置(%),次日是否持续",
              f"# mode={actual_mode}; as_of={AS_OF}; window={dates[0]}..{dates[-1]}",
              f"# {method}"]
    if actual_mode == "DAILY_OHLC_APPROX":
        output.append("# 仅日线近似候选；异动幅度列为日振幅，不是真实30分钟涨跌幅；不声称已验证分钟信号。")
    if not confirmed:
        output.append("# 无符合本模式筛选及截至基准日次日验证的候选；分钟数据不足时不能据此断言真实分钟信号不存在。")
    for row in confirmed:
        output.append(f"{row['code']},{row['date']},{row['type']},{row['change_pct']:.1f},"
                      f"{row['closing_position_pct']:.1f},{row['continuation']}")
    output_path = out_dir / "intraday_signal.txt"
    output_path.write_text("\n".join(output) + "\n", encoding="utf-8")
    transcript.append({"role": "tool", "content": json.dumps({
        "operation": "detect_anomaly_and_separate_next_day_labels", "mode": actual_mode,
        "method": method, "candidate_count": len(candidates), "confirmed_count": len(confirmed),
        "pending_count": sum(row["continuation"] == "待验证" for row in evaluated),
        "data_max_date": daily["date"].max(), "reason": reason,
    }, ensure_ascii=False)})
    (out_dir / "transcript.json").write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
    grade = grade_task(TASK_ID, transcript, out_dir)
    elapsed = time.perf_counter() - started
    result = {
        "task_id": TASK_ID, "as_of": AS_OF, "window": dates, "mode": actual_mode,
        "reason": reason, "method": method, "offline": True, "universe_rows": len(universe),
        "daily_codes": int(daily["code"].nunique()), "coverage": coverage,
        "source_probe_report": str(probe_path) if probe else None,
        "candidate_count": len(candidates), "confirmed_count": len(confirmed),
        "pending_count": sum(row["continuation"] == "待验证" for row in evaluated),
        "rejected_continuation_count": sum(row["continuation"] == "否" for row in evaluated),
        "candidates": evaluated, "output_file": str(output_path),
        "elapsed_seconds": round(elapsed, 4), "timeout_seconds": task["timeout_seconds"],
        "within_timeout": elapsed <= task["timeout_seconds"], "official_automated_grade": grade,
        "limitations": ["Current universe omits historical delisted stocks.",
                       "No data after as_of used; last-day continuation remains pending.",
                       "Daily fallback is permitted approximation, not true minute capability.",
                       "Automatic grade checks format/keywords, not arithmetic correctness.",
                       "Cached daily prices are current-vintage qfq, not a point-in-time vintage."],
    }
    (out_dir / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ms.DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=Path("data/market/acceptance/task36"))
    parser.add_argument("--mode", choices=["auto", "minute", "daily"], default="auto")
    parser.add_argument("--codes", help="optional comma-separated sample; omit for universe")
    args = parser.parse_args()
    result = run(args.data_dir, args.out_dir, mode=args.mode, codes=args.codes.split(",") if args.codes else None)
    print(json.dumps({key: value for key, value in result.items() if key not in {"candidates", "coverage"}},
                     ensure_ascii=False, indent=2))
    if not result["within_timeout"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
