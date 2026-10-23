"""离线检查字段 + 可选小样本新浪不复权数据核验；结果写入本地验收目录。"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import market_snapshot as ms


def fetch_raw(code: str, start: str, end: str, direct: bool) -> pd.DataFrame:
    """在 ms.bounded_call 的独立进程内运行，代理和超时设置不泄漏到主进程。"""
    import akshare as ak
    import requests
    original = requests.sessions.Session.request

    def request(session, *args, **kwargs):
        if direct:
            session.trust_env = False
        kwargs.setdefault("timeout", (5, 5))
        return original(session, *args, **kwargs)

    requests.sessions.Session.request = request
    return ak.stock_zh_a_daily(symbol=ms._sina_symbol(code),
                              start_date=start.replace("-", ""),
                              end_date=end.replace("-", ""), adjust="")


def audit(data_dir: Path, as_of_date: str, sample_codes: list[str],
          direct: bool = False, timeout: float = 20) -> dict:
    import akshare as ak
    bars = ms.load_bars(as_of_date, data_dir=data_dir)
    if bars.empty:
        raise ValueError("基准日前没有本地行情，不能完成字段验收")
    source = inspect.getsource(ak.stock_zh_a_daily)
    turnover = pd.to_numeric(bars["turnover_pct"], errors="coerce")
    if not turnover.notna().any():
        raise ValueError("换手率全部缺失，不能完成字段验收")
    report = {
        "as_of_date": as_of_date,
        "checked_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "rows": len(bars), "codes": int(bars["code"].nunique()),
        "units": {"price": "CNY per share, qfq in existing snapshot", "volume": "shares",
                  "amount": "CNY", "turnover_pct": "percentage points (1 means 1%)"},
        "turnover_missing": int(turnover.isna().sum()),
        "turnover_negative": int((turnover < 0).sum()),
        "turnover_over_100": int((turnover > 100).sum()),
        "turnover_min": float(turnover.min()), "turnover_max": float(turnover.max()),
        "source": {
            "akshare_version": ak.__version__,
            "function_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "historical_share_series": 'temp_df["outstanding_share"] * 10000' in source,
            "formula_volume_divided_by_shares": 'temp_df["volume"] / temp_df["outstanding_share"]' in source,
            "url": "https://github.com/akfamily/akshare/blob/main/akshare/stock/stock_zh_a_sina.py",
        },
        "notes": [
            "换手率来自新浪历史流通股本序列，AKShare 前向填充后 volume/outstanding_share×100；不是当前 SZSE 股本近似。",
            "数据源可能修订历史；下载时点不等于当时公告可用时点。",
            "已有前复权 close 不能与当前股本相乘来声称准确历史市值。",
            "可选样本仅核对来源与单位，不代表全部股票的逐行外部复核。",
        ],
        "samples": [],
    }
    sample_dir = data_dir / "field_audit"
    sample_dir.mkdir(parents=True, exist_ok=True)
    for code in sample_codes:
        local = bars.loc[bars["code"] == code].tail(20)
        if local.empty:
            report["samples"].append({"code": code, "status": "missing_local_bars"})
            continue
        try:
            raw = ms.bounded_call(fetch_raw, code, local["date"].min(), as_of_date,
                                  direct, timeout=timeout)
            raw["date"] = raw["date"].astype(str)
            joined = local.merge(raw, on="date", suffixes=("_cached", "_raw"))
            if joined.empty:
                raise ValueError("来源与本地行情日期无交集，不能核验")
            errors = (joined["turnover_pct"] - joined["turnover"] * 100).abs()
            volume_errors = (joined["volume_cached"] - joined["volume_raw"]).abs()
            passed = len(joined) == len(local) and errors.le(1e-9).all() and volume_errors.le(1e-6).all()
            raw["code"] = code
            raw["raw_float_market_cap_reconstructed"] = raw["close"] * raw["outstanding_share"]
            raw["point_in_time_available"] = False
            raw.to_parquet(sample_dir / f"{code}_raw.parquet", index=False)
            report["samples"].append({
                "code": code, "status": "checked" if passed else "mismatch_or_incomplete",
                "passed": bool(passed), "expected_rows": len(local), "joined_rows": len(joined),
                "missing_dates": sorted(set(local["date"]) - set(joined["date"])),
                "max_turnover_error_pct": float(errors.max()),
                "max_volume_error_shares": float(volume_errors.max()),
                "latest_raw_close": float(raw["close"].iloc[-1]),
                "latest_historical_float_shares": float(raw["outstanding_share"].iloc[-1]),
                "market_cap_scope": "reconstructed from source history; historical announcement availability unverified",
            })
        except Exception as exc:
            report["samples"].append({"code": code, "status": "source_failed", "error": str(exc)[:300]})
    output = sample_dir / "report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    acceptance = data_dir / "acceptance"
    acceptance.mkdir(parents=True, exist_ok=True)
    (acceptance / "fields.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ms.DATA_DIR)
    parser.add_argument("--as-of", dest="as_of_date", required=True)
    parser.add_argument("--sample-codes", nargs="*", default=[])
    parser.add_argument("--direct", action="store_true")
    parser.add_argument("--timeout", type=float, default=20)
    print(json.dumps(audit(**vars(parser.parse_args())), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
