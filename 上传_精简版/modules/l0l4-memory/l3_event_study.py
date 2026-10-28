# -*- coding: utf-8 -*-
"""L3：技能层——事件研究（Event Study），把“结论”变成可检验的数字。

做法是金融学里最标准的市场模型（Market Model）：
    估计窗口 [-140, -11]：  r_i = α + β·r_m + ε
    事件窗口 [-1, +5]：     AR_t = r_i,t - (α + β·r_m,t)
    CAR = Σ AR_t
CAR > 0 表示跑赢基准，CAR < 0 表示跑输。基准默认沪深 300。

三种数据来源，优先级从高到低：
    akshare 实时  ->  本地 CSV 缓存  ->  确定性模拟数据（断网兜底，UI 会标注）
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from config import BENCHMARK_INDEX, ESTIMATION_WINDOW, EVENT_WINDOW, PRICE_CACHE


def _cache_path(code: str):
    return PRICE_CACHE / f"{code}.csv"


def _read_cache(code: str) -> Optional[pd.DataFrame]:
    p = _cache_path(code)
    if not p.exists():
        return None
    df = pd.read_csv(p, parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True) if len(df) else None


def _write_cache(code: str, df: pd.DataFrame) -> None:
    df.to_csv(_cache_path(code), index=False)


INDEX_CODES = {"000001", "000300", "000905", "000016", "399001", "399006", "399905"}


def _is_index(code: str) -> bool:
    return code in INDEX_CODES


def _fetch_akshare(code: str, start: str, end: str) -> pd.DataFrame:
    import akshare as ak

    if _is_index(code):
        # 新浪源指数日线（东方财富 push2 接口在部分网络下会 SSL 失败）
        symbol = ("sz" if code.startswith("399") else "sh") + code
        raw = ak.stock_zh_index_daily(symbol=symbol)
        df = raw.rename(columns={"date": "date", "close": "close"})[["date", "close"]].copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))]
    else:
        # 先走新浪（近期东财 push2his 在部分网络下 SSL 失败），失败再回东财
        try:
            prefix = "sh" if code.startswith(("6", "9")) else ("bj" if code.startswith(("4", "8")) else "sz")
            raw = ak.stock_zh_a_daily(symbol=prefix + code, start_date=start, end_date=end, adjust="qfq")
            if "date" not in raw.columns:
                raw = raw.reset_index()
            df = raw[["date", "close"]].copy()
        except Exception:
            raw = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
            df = raw.rename(columns={"日期": "date", "收盘": "close"})[["date", "close"]]
        df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna().sort_values("date").reset_index(drop=True)


def _market_rets(event_date: str, days: int) -> np.ndarray:
    """所有模拟序列共用同一个“市场因子”，这样估出来的 β 才像样。"""
    seed = int(hashlib.sha1(f"MARKET|{event_date}".encode()).hexdigest()[:8], 16)
    return np.random.default_rng(seed).normal(0.0003, 0.010, days)


def _synthetic(code: str, event_date: str, days: int = 300) -> pd.DataFrame:
    mkt = _market_rets(event_date, days)
    if code in ("000300", "000001", "399001", "399006"):
        rets = mkt
    else:
        seed = int(hashlib.sha1(f"{code}|{event_date}".encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        beta = 0.9 + (seed % 60) / 100.0
        rets = beta * mkt + rng.normal(0.0002, 0.013, days)
    end = pd.Timestamp((datetime.strptime(event_date, "%Y-%m-%d") + timedelta(days=40)).date())
    dates = pd.bdate_range(end=end, periods=days)
    close = 100 * np.cumprod(1 + rets)
    return pd.DataFrame({"date": dates, "close": close})


def load_prices(code: str, event_date: str, lookback_days: int = 400) -> tuple[pd.DataFrame, str]:
    end = (datetime.strptime(event_date, "%Y-%m-%d") + timedelta(days=40)).strftime("%Y%m%d")
    start = (datetime.strptime(event_date, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime("%Y%m%d")
    try:
        df = _fetch_akshare(code, start, end)
        if len(df) > 60:
            _write_cache(code, df)
            return df, "akshare"
    except Exception:
        pass
    cached = _read_cache(code)
    if cached is not None and len(cached) > 60:
        return cached, "cache"
    return _synthetic(code, event_date), "synthetic"


def _window_dates(event_date: str, lookback_days: int = 400) -> tuple[str, str]:
    end = (datetime.strptime(event_date, "%Y-%m-%d") + timedelta(days=40)).strftime("%Y-%m-%d")
    start = (datetime.strptime(event_date, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    return start, end


def event_study(code: str, event_date: str, *, benchmark: str = BENCHMARK_INDEX,
                window: tuple[int, int] = EVENT_WINDOW,
                est_len: int = ESTIMATION_WINDOW,
                as_of: str | None = None) -> dict:
    """事件研究（市场模型 CAR）。

    as_of: 时点约束（PIT）。传入后只使用 <= as_of 的行情，
           杜绝"用明天的数据解释今天"。回测/答辩演示建议显式传 as_of。
    """
    import market_bridge  # 延迟导入，避免与 config 形成环

    start, end = _window_dates(event_date)

    # ① 优先用队友的本地快照（离线、可复现、带版本），个股与基准都齐了才用
    snap_s = market_bridge.load_series(code, start, end)
    snap_i = market_bridge.load_series(benchmark, start, end)
    if snap_i is None:
        # 快照里可能只有创业板指（sz399006），没有 000300：显式换基准并记录
        alt = market_bridge.available_index()
        if alt and alt != benchmark:
            snap_i = market_bridge.load_series(alt, start, end)
            if snap_i is not None:
                benchmark = alt
    if snap_s is not None and snap_i is not None and len(snap_s) > 60 and len(snap_i) > 60:
        stock, index = snap_s, snap_i
        src_s = src_i = "snapshot"
    else:
        # ② AkShare / 缓存 / 模拟
        stock, src_s = load_prices(code, event_date)
        index, src_i = load_prices(benchmark, event_date)

    # 个股真实、指数模拟（或反之）会让 α/β 完全失真：任一侧缺失就两边都用模拟序列
    if "synthetic" in (src_s, src_i):
        stock, index = _synthetic(code, event_date), _synthetic(benchmark, event_date)
        src_s = src_i = "synthetic"

    px = stock.merge(index, on="date", suffixes=("_s", "_m")).sort_values("date").reset_index(drop=True)
    px["r_s"] = px["close_s"].pct_change()
    px["r_m"] = px["close_m"].pct_change()
    px = px.dropna().reset_index(drop=True)

    # ---- PIT：只允许看到 as_of 及之前的数据 ----
    truncated = False
    if as_of:
        last = px["date"].max()
        px = px[px["date"] <= pd.Timestamp(as_of)].reset_index(drop=True)
        truncated = bool(len(px)) and pd.Timestamp(as_of) < last
        if len(px) < est_len + 10:
            raise ValueError(f"{code} 在 as_of={as_of} 之前的样本不足（{len(px)} 行）")

    if len(px) < est_len + 10:
        raise ValueError(f"{code} 行情样本不足（{len(px)} 行）")

    ts = pd.to_datetime(event_date)
    future = px.index[px["date"] >= ts]
    if len(future) == 0:
        raise ValueError(f"事件日 {event_date} 晚于 as_of={as_of}，无法计算（这正是不许穿越的保护）")
    t0 = int(future[0])

    lo = max(0, t0 + window[0])
    hi = min(len(px) - 1, t0 + window[1])
    est_lo = max(0, t0 - est_len - 10)
    est = px.iloc[est_lo:t0 - 1]

    beta, alpha = np.polyfit(est["r_m"], est["r_s"], 1)
    ev = px.iloc[lo:hi + 1].copy()
    ev["ar"] = ev["r_s"] - (alpha + beta * ev["r_m"])
    ev["car"] = ev["ar"].cumsum()

    car = float(ev["car"].iloc[-1])
    return {
        "code": code,
        "benchmark": benchmark,
        "event_date": event_date,
        "t0_date": px["date"].iloc[t0].strftime("%Y-%m-%d"),
        "window": window,
        "alpha": round(float(alpha), 6),
        "beta": round(float(beta), 4),
        "n_est": len(est),
        "car": round(car, 4),
        "car_pct": round(car * 100, 2),
        "ar_mean_pct": round(float(ev["ar"].mean()) * 100, 2),
        "n_days": int(len(ev)),
        "complete": bool(t0 + window[1] < len(px)),
        "as_of": as_of,
        "truncated": truncated,
        "source": (src_s if src_s == src_i
                   else ("cache" if "cache" in (src_s, src_i) else "mixed")),
        "table": [{
            "date": d.strftime("%Y-%m-%d"),
            "股票收益%": round(float(rs) * 100, 2),
            "基准收益%": round(float(rm) * 100, 2),
            "超额收益%": round(float(ar) * 100, 2),
            "累计超额%": round(float(c) * 100, 2),
        } for d, rs, rm, ar, c in zip(ev["date"], ev["r_s"], ev["r_m"], ev["ar"], ev["car"])],
    }


def verdict(study: dict, direction: str) -> str:
    """把 CAR 与 L2 结论对照，形成一句可写进报告的话。"""
    car = study["car_pct"]
    if direction == "偏多":
        return f"L2 偏多，事件窗口 CAR {car:+.2f}%，{'方向一致' if car > 0 else '方向不一致（逻辑可能已提前兑现）'}。"
    if direction == "偏空":
        return f"L2 偏空，事件窗口 CAR {car:+.2f}%，{'方向一致' if car < 0 else '方向不一致（利空可能已被消化）'}。"
    return f"L2 中性，事件窗口 CAR {car:+.2f}%，缺乏方向性证据。"


if __name__ == "__main__":
    r = event_study("300750", "2026-10-21")
    print({k: v for k, v in r.items() if k != "table"})
    for row in r["table"]:
        print(row)
