"""Prepare a small real-price candidate cache without synthetic fallback.

This is not a historical news benchmark. The inherited twelve event labels and
publication times remain unverified until primary sources are checked.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from experiments.common import REPO, manifest, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codes", nargs="+", default=["300308", "300502", "600519", "002594"])
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2025-03-31")
    parser.add_argument("--benchmark", default="sh000300")
    parser.add_argument("--timeout", type=float, default=25)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists() or args.start > args.end or args.timeout <= 0:
        parser.error("Use a new output directory and valid interval/time budget")
    sys.path.append(str(REPO))
    import market_snapshot as market
    args.out.mkdir(parents=True)
    results = []
    for code in args.codes:
        row = {"code": code, "kind": "stock", "status": "failed", "source": "Sina via existing AkShare adapter",
               "adjustment": "qfq_at_collection_time_not_historical_point_in_time"}
        try:
            if len(code) != 6 or not code.isdigit():
                raise ValueError("Codes must contain six digits")
            frame = market.bounded_call(market._fetch_one, code, args.start, args.end, retries=1, timeout=args.timeout)
            if frame.empty:
                raise ValueError("No price rows returned")
            path = args.out / f"{code}.parquet"
            frame.to_parquet(path, index=False)
            row.update(status="ok", rows=len(frame), first_date=str(frame["date"].min()), last_date=str(frame["date"].max()), file=path.name, sha256=sha256(path))
        except Exception as exc:
            row["error_type"] = type(exc).__name__
        results.append(row)
        print(json.dumps(row), flush=True)
    index = {"code": args.benchmark, "kind": "index", "status": "failed", "source": "Sina via existing AkShare adapter"}
    try:
        frame = market.bounded_call(market.fetch_index, args.start, args.end, args.benchmark, timeout=args.timeout)
        if frame.empty:
            raise ValueError("No index rows returned")
        path = args.out / f"{args.benchmark}.parquet"
        frame.to_parquet(path, index=False)
        index.update(status="ok", rows=len(frame), first_date=str(frame["date"].min()), last_date=str(frame["date"].max()), file=path.name, sha256=sha256(path))
    except Exception as exc:
        index["error_type"] = type(exc).__name__
    results.append(index)
    print(json.dumps(index), flush=True)
    original = REPO / "memory" / "L4_archive" / "real_fin_events_12.json"
    legacy = json.loads(original.read_text(encoding="utf-8"))
    audit = [{"id": row["case_id"], "stock_code": row["stock_code"], "claimed_as_of": row["as_of_date"],
              "claimed_publication_time": row["latest_event"].get("published_at"),
              "claimed_source": row["latest_event"].get("source"),
              "primary_source_url": row["latest_event"].get("url") or row["latest_event"].get("source_url"),
              "status": "NOT_ELIGIBLE_UNVERIFIED_NEWS_PROVENANCE_AND_TIME",
              "legacy_return_labels_accepted": False} for row in legacy]
    report = manifest([original], task="real_price_candidate_cache", start=args.start, end=args.end,
        created_at_utc=datetime.now(timezone.utc).isoformat(), results=results,
        full_market_snapshot=False, synthetic_fallback=False, legacy_news_audit=audit,
        price_source_caveats=["Vendor historical data can be revised", "Collected qfq is not archived point-in-time adjustment factors",
                              "Prices alone do not validate news publication times or inherited return labels"])
    (args.out / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(row["status"] == "ok" for row in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
