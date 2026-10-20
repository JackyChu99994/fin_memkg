"""30 分钟原始 K 线缓存与 task_36 信号；日线近似始终单独标记。

新浪接口及字段见 AKShare stock_zh_a_minute 实现；腾讯公开图表接口为
实验性适配器。接口仅保证实际返回的区间，不承诺任意历史可下载。
时间戳统一为 Asia/Shanghai 的 K 线结束时间；价格不复权、成交量为股。
"""
from __future__ import annotations

import argparse
import json
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent / "data" / "market" / "intraday"
SINA_URL = "https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData"
TENCENT_URL = "https://ifzq.gtimg.cn/appstock/app/kline/mkline"
BAR_ENDS = ("10:00", "10:30", "11:00", "11:30", "13:30", "14:00", "14:30", "15:00")
COLUMNS = ["code", "timestamp", "open", "high", "low", "close", "volume"]


class IntradayCoverageError(ValueError):
    """缓存不能完整回答请求；调用方可明确选择日线近似。"""


def symbol(code: str) -> str:
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("code must be six digits")
    return ("sh" if code.startswith(("6", "9")) else "bj" if code.startswith(("4", "8")) else "sz") + code


def cutoff(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value + " 23:59:59.999999" if len(value) == 10 else value)
    return ts.tz_localize("Asia/Shanghai") if ts.tzinfo is None else ts.tz_convert("Asia/Shanghai")


def completed_daily_date(value: str) -> str:
    end = cutoff(value)
    day = end.date()
    if end.hour < 15:
        day -= timedelta(days=1)
    return day.isoformat()


def normalize(frame: pd.DataFrame, *, code: str | None = None, volume_unit: str = "shares") -> pd.DataFrame:
    """严格规范数据；一致重复可去重，冲突重复拒绝，避免静默覆盖历史。"""
    df = frame.rename(columns={"day": "timestamp", "time": "timestamp"}).copy()
    if code is not None:
        symbol(code)
        df["code"] = code
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    df = df[COLUMNS].copy()
    df["code"] = df["code"].astype(str).str.zfill(6)
    for value in df["code"].unique():
        symbol(value)
    dates = pd.to_datetime(df["timestamp"], errors="raise")
    df["timestamp"] = dates.dt.tz_localize("Asia/Shanghai") if dates.dt.tz is None else dates.dt.tz_convert("Asia/Shanghai")
    for field in ["open", "high", "low", "close", "volume"]:
        df[field] = pd.to_numeric(df[field], errors="raise")
    if volume_unit not in {"shares", "lots"}:
        raise ValueError("volume_unit must be shares or lots (100 shares)")
    if volume_unit == "lots":
        df["volume"] *= 100
    if df.isna().any().any() or df.isin([float("inf"), float("-inf")]).any().any():
        raise ValueError("missing or nonfinite value")
    if (not df["timestamp"].dt.strftime("%H:%M").isin(BAR_ENDS).all()
            or not df["timestamp"].dt.second.eq(0).all()
            or not df["timestamp"].dt.microsecond.eq(0).all()
            or not df["timestamp"].dt.nanosecond.eq(0).all()):
        raise ValueError("missing value or invalid 30-minute bar end")
    if (df["volume"] < 0).any() or (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("nonpositive price or negative volume")
    if ((df["high"] < df[["open", "close", "low"]].max(axis=1)) |
            (df["low"] > df[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("invalid OHLC bounds")
    df = df.drop_duplicates()
    if df.duplicated(["code", "timestamp"]).any():
        raise ValueError("conflicting duplicate code/timestamp")
    return df.sort_values(["code", "timestamp"]).reset_index(drop=True)


def fetch_recent(code: str, source: str, *, timeout: float = 5.0, raw_path: Path | None = None,
                 requested_end: str | None = None) -> tuple[pd.DataFrame, dict]:
    """一次有超时的 GET，无隐式重试、无全量下载、无日线复权调用。"""
    sym = symbol(code)
    if source == "sina":
        url, params = SINA_URL, {"symbol": sym, "scale": "30", "ma": "no", "datalen": "1970"}
    elif source == "tencent":
        url, params = TENCENT_URL, {"param": f"{sym},m30,{requested_end or ''},320"}
    else:
        raise ValueError("source must be sina or tencent")
    started = time.perf_counter()
    response = requests.get(url, params=params, timeout=min(timeout, 5.0),
                            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"})
    response.raise_for_status()
    if raw_path is not None:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(response.text, encoding="utf-8")
    if source == "sina":
        match = re.search(r"=\((.*)\);?", response.text, re.S)
        payload = json.loads(match.group(1) if match else response.text)
        raw = pd.DataFrame(payload)
        unit = "shares"
    else:
        payload = response.json()
        records = payload.get("data", {}).get(sym, {}).get("m30", [])
        raw = pd.DataFrame([row[:6] for row in records],
                           columns=["timestamp", "open", "close", "high", "low", "volume"])
        if not raw.empty:
            raw["timestamp"] = pd.to_datetime(raw["timestamp"], format="%Y%m%d%H%M")
        unit = "lots"
    if raw.empty:
        raise IntradayCoverageError(f"{source}: empty response")
    df = normalize(raw, code=code, volume_unit=unit)
    meta = {"code": code, "source": source, "endpoint": url, "params": params, "rows": len(df),
            "first": df["timestamp"].min().isoformat(), "last": df["timestamp"].max().isoformat(),
            "volume_source_unit": unit, "volume_stored_unit": "shares", "adjust": "none",
            "unit_basis": "Tencent lots convention; sample cross-source scale checked" if source == "tencent" else "Sina raw share units",
            "timezone": "Asia/Shanghai", "timestamp_semantics": "bar_end",
            "fetched_at": datetime.now().astimezone().isoformat(),
            "elapsed_seconds": round(time.perf_counter() - started, 4)}
    return df, meta


def save_cache(frame: pd.DataFrame, metadata: dict, data_dir: Path = DATA_DIR) -> None:
    df = normalize(frame)
    codes = df["code"].unique()
    if len(codes) != 1:
        raise ValueError("save one stock per cache")
    code = codes[0]
    source = metadata.get("source")
    if source not in {"sina", "tencent", "imported"} or metadata.get("adjust") != "none":
        raise ValueError("source and adjust=none required; never cache synthetic adjusted minute data")
    out = Path(data_dir) / source
    out.mkdir(parents=True, exist_ok=True)
    version = uuid.uuid4().hex
    temp = out / f"{code}.{version}.tmp.parquet"
    meta_temp = out / f"{code}.{version}.tmp.json"
    metadata = {**metadata, "code": code, "rows": len(df),
                "first": df["timestamp"].min().isoformat(), "last": df["timestamp"].max().isoformat()}
    meta_temp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    df.to_parquet(temp, index=False)
    temp.replace(out / f"{code}.parquet")
    meta_temp.replace(out / f"{code}.json")


def load_intraday(codes: list[str], as_of_date: str, trading_dates: list[str], *,
                  data_dir: Path = DATA_DIR, allow_network: bool = False,
                  max_wait_seconds: float = 5.0) -> tuple[pd.DataFrame, dict]:
    """仅完整覆盖每个已闭合时段才返回成功；默认离线，网络共用总预算。

    trading_dates 必须来自交易日历或指数；缺失时段不能默认为停牌。
    """
    end = cutoff(as_of_date)
    expected = [pd.Timestamp(f"{day} {bar}", tz="Asia/Shanghai") for day in trading_dates
                for bar in BAR_ENDS if pd.Timestamp(f"{day} {bar}", tz="Asia/Shanghai") <= end]
    if not expected:
        raise ValueError("no completed intervals requested")
    deadline = time.perf_counter() + max(0.0, max_wait_seconds)
    frames, missing, sources, cache_errors = [], {}, {}, []
    for code in codes:
        symbol(code)
        chosen = None
        for source in ("imported", "sina", "tencent"):
            path = Path(data_dir) / source / f"{code}.parquet"
            if path.exists():
                try:
                    candidate = normalize(pd.read_parquet(path))
                    meta_path = path.with_suffix(".json")
                    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
                    if (not isinstance(meta, dict) or meta.get("adjust") != "none"
                            or meta.get("source") != source or not candidate["code"].eq(code).all()):
                        raise ValueError(f"invalid cache provenance: {path}")
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    cache_errors.append({"code": code, "source": source,
                                         "error": f"{type(exc).__name__}: {exc}"[:300]})
                    continue
                if set(expected).issubset(set(candidate["timestamp"])):
                    chosen = candidate
                    sources[code] = source
                    break
        if chosen is None and allow_network:
            for source in ("sina", "tencent"):
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    break
                try:
                    from market_snapshot import bounded_call
                    candidate, meta = bounded_call(fetch_recent, code, source, timeout=min(remaining, 5.0))
                    save_cache(candidate, meta, data_dir)
                    if set(expected).issubset(set(candidate["timestamp"])):
                        chosen = candidate
                        sources[code] = source
                        break
                except (requests.RequestException, ValueError, KeyError, RuntimeError, OSError, TimeoutError):
                    continue
        if chosen is None:
            missing[code] = "missing requested closed intervals; recent endpoint is not historical coverage"
        else:
            frames.append(chosen[chosen["timestamp"].isin(expected)])
    report = {"mode": "MINUTE_30", "requested_codes": len(codes), "covered_codes": len(frames),
              "missing": missing, "sources": sources, "volume_unit": "shares", "adjust": "none",
              "dates": trading_dates, "as_of": as_of_date, "cache_errors": cache_errors}
    if missing:
        raise IntradayCoverageError(json.dumps(report, ensure_ascii=False))
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)), report


def detect_minute_signals(frame: pd.DataFrame, as_of_date: str) -> list[dict]:
    """前几个时段均量仅使用同日已发生时段，V 型后两棒连续上涨并收复跌前价格。"""
    data = normalize(frame)
    data = data[data["timestamp"] <= cutoff(as_of_date)].copy()
    data["date"] = data["timestamp"].dt.strftime("%Y-%m-%d")
    result = []
    for (code, day), bars in data.groupby(["code", "date"], sort=True):
        bars = bars.sort_values("timestamp").reset_index(drop=True)
        if set(bars["timestamp"].dt.strftime("%H:%M")) != set(BAR_ENDS):
            continue  # 未完成整天时不能判断当日收盘位置
        low, high = float(bars["low"].min()), float(bars["high"].max())
        position = (float(bars["close"].iloc[-1]) - low) / (high - low) if high > low else 0.0
        if position <= 0.6:
            continue
        for i in range(1, len(bars)):
            previous, current = float(bars.loc[i - 1, "close"]), float(bars.loc[i, "close"])
            change = current / previous - 1
            baseline = float(bars.loc[:i - 1, "volume"].mean())
            if baseline <= 0 or float(bars.loc[i, "volume"]) <= 5 * baseline:
                continue
            kind = None
            if change > 0.05:
                kind = "急拉"
            elif change < -0.03 and i + 2 < len(bars):
                if current < float(bars.loc[i + 1, "close"]) < float(bars.loc[i + 2, "close"]) and float(bars.loc[i + 2, "close"]) >= previous:
                    kind = "V型反转"
            if kind:
                result.append({"code": code, "date": day, "type": kind, "change_pct": change * 100,
                               "closing_position_pct": position * 100, "day_low": low,
                               "timestamp": bars.loc[i, "timestamp"].isoformat(),
                               "volume_ratio": float(bars.loc[i, "volume"]) / baseline,
                               "mode": "MINUTE_30"})
    return result


def daily_approximation(frame: pd.DataFrame, as_of_date: str, trading_dates: list[str]) -> list[dict]:
    """官方 reference_ans 的近似：日振幅>8%或下影线>50%，量>前5日均量3倍。

    不能验证 30 分钟路径、同日时段量比、两棒收复；只产生待核验候选。
    """
    data = frame.copy()
    data["date"] = data["date"].astype(str).str[:10]
    data = data[data["date"] <= completed_daily_date(as_of_date)].sort_values(["code", "date"])
    result = []
    for code, bars in data.groupby("code"):
        bars = bars.copy()
        bars["previous_close"] = bars["close"].shift()
        bars["previous_volume5"] = bars["volume"].shift().rolling(5).mean()
        for _, bar in bars[bars["date"].isin(trading_dates)].iterrows():
            span = float(bar["high"] - bar["low"])
            if span <= 0 or pd.isna(bar["previous_volume5"]) or bar["previous_volume5"] <= 0:
                continue
            position = float((bar["close"] - bar["low"]) / span)
            volume_ratio = float(bar["volume"] / bar["previous_volume5"])
            amplitude = float(span / bar["previous_close"] * 100)
            lower_wick = float((min(bar["open"], bar["close"]) - bar["low"]) / span)
            if position <= 0.6 or volume_ratio <= 3:
                continue
            for kind, match in (("急拉", amplitude > 8), ("V型反转", lower_wick > 0.5)):
                if match:
                    result.append({"code": str(code), "date": bar["date"], "type": kind,
                                   "change_pct": amplitude, "closing_position_pct": position * 100,
                                   "day_low": float(bar["low"]), "volume_ratio": volume_ratio,
                                   "mode": "DAILY_OHLC_APPROX", "amplitude_semantics": "daily high-low / previous close",
                                   "intraday_verified": False})
    return result


def attach_continuation(signals: list[dict], daily: pd.DataFrame, as_of_date: str,
                        trading_dates: list[str]) -> list[dict]:
    """后续标签独立计算；不读取截止日之后的数据，不用下一个有成交日冒充次日。"""
    closes = daily.copy()
    closes["date"] = closes["date"].astype(str).str[:10]
    closes = closes[closes["date"] <= completed_daily_date(as_of_date)]
    lookup = {(str(row.code), row.date): float(row.close) for row in closes.itertuples()}
    calendar = sorted(set(trading_dates))
    output = []
    for signal in signals:
        item = dict(signal)
        position = calendar.index(item["date"])
        next_day = calendar[position + 1] if position + 1 < len(calendar) else None
        next_close = lookup.get((item["code"], next_day))
        item["continuation"] = "待验证" if next_day is None or next_close is None else ("是" if next_close >= item["day_low"] else "否")
        item["confirmation_date"] = next_day
        output.append(item)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Import externally obtained genuine unadjusted 30-minute bars.")
    parser.add_argument("input", type=Path, help="CSV or parquet; code,timestamp,open,high,low,close,volume")
    parser.add_argument("--volume-unit", choices=["shares", "lots"], required=True)
    parser.add_argument("--source-name", required=True, help="actual vendor/file provenance, not an invented source")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    raw = pd.read_csv(args.input, dtype={"code": str}) if args.input.suffix.lower() == ".csv" else pd.read_parquet(args.input)
    frame = normalize(raw, volume_unit=args.volume_unit)
    for code, part in frame.groupby("code"):
        save_cache(part, {"source": "imported", "vendor": args.source_name, "input": str(args.input.resolve()),
                          "adjust": "none", "volume_source_unit": args.volume_unit,
                          "volume_stored_unit": "shares", "timezone": "Asia/Shanghai",
                          "timestamp_semantics": "bar_end", "rows": len(part),
                          "first": part["timestamp"].min().isoformat(), "last": part["timestamp"].max().isoformat()},
                   args.data_dir)
    print(json.dumps({"imported_codes": int(frame["code"].nunique()), "rows": len(frame)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
