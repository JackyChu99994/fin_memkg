"""小样本在线探测；保存原始响应、覆盖范围、异常；不扫描全市场。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from market_intraday import DATA_DIR, fetch_recent, save_cache
from market_snapshot import bounded_call


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", default="300750,300059")
    parser.add_argument("--target-start", default="2024-08-16")
    parser.add_argument("--target-end", default="2024-08-22")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    codes = args.codes.split(",")
    if len(codes) > 5:
        parser.error("probe at most five stocks")
    report = {"target": [args.target_start, args.target_end], "attempts": [],
              "limitations": "Sampled stocks only; endpoint range overlap is not full-market or complete-day coverage."}
    started = time.perf_counter()
    for code in codes:
        for source, requested_end in (("sina", None), ("tencent", None), ("tencent", args.target_end.replace("-", ""))):
            label = f"{source}_{code}" + ("_dated" if requested_end else "")
            raw_path = args.data_dir / "probes" / f"{label}.txt"
            attempt = {"code": code, "source": source, "requested_end": requested_end}
            try:
                frame, meta = bounded_call(fetch_recent, code, source, timeout=5.0,
                                          raw_path=raw_path, requested_end=requested_end)
                covered = meta["first"][:10] <= args.target_start and meta["last"][:10] >= args.target_end
                attempt.update(meta)
                attempt["target_range_spanned"] = covered
                attempt["status"] = "RANGE_SPANNED_CHECK_INTERVALS" if covered else "HISTORICAL_RANGE_UNAVAILABLE"
                if requested_end is None:
                    save_cache(frame, meta, args.data_dir)
            except Exception as exc:
                attempt.update(status="SOURCE_ERROR", error=f"{type(exc).__name__}: {exc}"[:500])
            report["attempts"].append(attempt)
            print(json.dumps(attempt, ensure_ascii=False), flush=True)
    report["elapsed_seconds"] = round(time.perf_counter() - started, 4)
    target = args.data_dir / "probe_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
