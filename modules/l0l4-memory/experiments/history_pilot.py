"""Build a delayed-entry historical pilot; keep realized outcomes out of inputs.

These known development cases are not held out and have no state-change history.
Publication precision is a day, never an invented first-release timestamp.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from experiments.common import manifest, sha256, write_jsonl

SPECS = [
    {"id": "PILOT_300308_2024Q3", "stock_code": "300308", "disclosure_date": "2024-10-23",
     "report": "300308-2024q3.pdf", "notice": "300308-disclosure-notice.pdf",
     "report_url": "https://static.cninfo.com.cn/finalpage/2024-10-23/1221474464.PDF",
     "notice_url": "https://disc.static.szse.cn/disc/disk03/finalpage/2024-10-22/682835bd-540c-46ab-a71d-0dfedb49d255.PDF"},
    {"id": "PILOT_300502_2024Q3", "stock_code": "300502", "disclosure_date": "2024-10-25",
     "report": "300502-2024q3.pdf", "notice": "300502-disclosure-notice.pdf",
     "report_url": "https://static.cninfo.com.cn/finalpage/2024-10-25/1221504363.PDF",
     "notice_url": "https://static.cninfo.com.cn/finalpage/2024-10-25/1221504365.PDF"},
]


def outcome(stock, benchmark, disclosure_day, horizon=5):
    """Next-session close to five subsequent benchmark sessions' close.

    Exact calendar alignment is required; suspended/missing stock bars fail closed.
    This is a gross arithmetic excess return, not risk-adjusted CAR or a strategy.
    """
    import math
    if horizon < 1:
        raise ValueError("Horizon must be positive")
    for frame in (stock, benchmark):
        if frame["date"].duplicated().any():
            raise ValueError("Duplicate price dates")
    bench = benchmark.sort_values("date").set_index("date")
    shares = stock.sort_values("date").set_index("date")
    sessions = [day for day in bench.index if day > disclosure_day]
    if len(sessions) <= horizon:
        raise ValueError("Incomplete forward benchmark window")
    window = sessions[:horizon + 1]
    if any(day not in shares.index for day in window):
        raise ValueError("Missing stock session; do not shift the horizon")
    values = [float(frame.loc[day, "close"]) for frame in (shares, bench) for day in window]
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("Invalid close price")
    start, end = window[0], window[-1]
    stock_return = float(shares.loc[end, "close"] / shares.loc[start, "close"] - 1)
    benchmark_return = float(bench.loc[end, "close"] / bench.loc[start, "close"] - 1)
    return {"entry_date": start, "exit_date": end, "holding_intervals": horizon,
            "stock_return": stock_return, "benchmark_return": benchmark_return,
            "arithmetic_excess_return": stock_return - benchmark_return}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new output directory")
    import pandas as pd
    sources = args.cache / "primary_sources"
    required = [args.cache / f"{code}.parquet" for code in ("300308", "300502", "sh000300")]
    required += [sources / spec[key] for spec in SPECS for key in ("report", "notice")]
    required += [sources / (spec["report"] + ".full.txt") for spec in SPECS]
    if any(not path.is_file() or path.stat().st_size == 0 for path in required):
        raise ValueError("All source PDFs, extracted full text, and prices must exist")
    args.out.mkdir(parents=True)
    protocol = {"scope": "known_case_pipeline_pilot_not_heldout", "cases": SPECS,
        "publication_precision": "date_only_confirmed_by_official_notice",
        "availability_rule": "Conservatively defer use until next calendar day 00:00 Asia/Shanghai",
        "entry": "first benchmark session strictly after disclosure date, at close",
        "exit": "close five benchmark trading intervals after entry",
        "outcome": "stock simple return minus benchmark simple return",
        "thresholds": "No directional labels or thresholds selected in this pilot",
        "costs": "Gross descriptive outcomes; no execution, fees, or causal effect claim",
        "state_memory_evaluation_ready": False,
        "reason": "Each case contains one report only; verified earlier state and changes are still needed",
        "created_before_outcome_computation": datetime.now(timezone.utc).isoformat()}
    # Freeze source hashes and outcome definition before inspecting forward prices.
    (args.out / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    (args.out / "manifest.json").write_text(json.dumps(manifest(required, task="historical_delayed_entry_pilot"), indent=2), encoding="utf-8")
    inputs, targets = [], []
    benchmark = pd.read_parquet(args.cache / "sh000300.parquet")
    for spec in SPECS:
        text = (sources / (spec["report"] + ".full.txt")).read_text(encoding="utf-8")
        available = (date.fromisoformat(spec["disclosure_date"]) + timedelta(days=1)).isoformat() + "T00:00:00+08:00"
        inputs.append({"id": spec["id"], "stock_code": spec["stock_code"], "as_of": available,
            "documents": [{"id": spec["id"] + "_REPORT", "text": text,
                "source_url": spec["report_url"], "source_sha256": sha256(sources / spec["report"]),
                "disclosure_date": spec["disclosure_date"], "publication_precision": "date_only",
                "available_by_policy_at": available}],
            "scope": "historical_pipeline_pilot_not_a_memory_benchmark"})
        result = outcome(pd.read_parquet(args.cache / f"{spec['stock_code']}.parquet"), benchmark, spec["disclosure_date"])
        targets.append({"id": spec["id"], **result})
    write_jsonl(args.out / "inputs.jsonl", inputs)
    write_jsonl(args.out / "outcomes.DO_NOT_USE_AS_MODEL_INPUT.jsonl", targets)
    print(json.dumps({"cases": len(inputs), "out": str(args.out), "ready_for_memory_comparison": False}))


if __name__ == "__main__":
    main()
