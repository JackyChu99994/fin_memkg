# -*- coding: utf-8 -*-
"""数据层融合：读队友 stage3 的本地行情快照，替代在线 AkShare。

这是两条技术线唯一的"硬接口"。契约来自 fin_memkg 的 `market_snapshot.py`：

    data/market/bars.parquet      个股日线（code / date / close，可能还带 open/high/low/volume/amount/turnover）
    data/market/index.parquet     指数日线（同结构）
    data/market/universe.parquet  股票池（含申万三级行业）
    data/market/meta.json         版本、区间、覆盖统计

我们只依赖 (date, close) 两列，其它列忽略——这样对方换字段名也不会把我们的
L3 事件研究打挂。顺序：本地快照 → AkShare → 模拟（三级回退，前两级在 L3 里）。

为什么要这个文件：
  * 快照是"某天固化下来的版本"，天然满足 PIT（point-in-time）约束；
  * 921k 行日线在本地，CAR 不再依赖当天网络；
  * 对方的覆盖检查（1411 只 / 区间）可以原样展示到我们的大屏上。
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

from config import ROOT

DATA_DIR = Path(os.environ.get("MEMKG_MARKET_DIR", str(ROOT / "data" / "market")))

CODE_KEYS = ("code", "股票代码", "证券代码", "symbol", "ts_code")
DATE_KEYS = ("date", "日期", "trade_date", "时间")
CLOSE_KEYS = ("close", "收盘", "收盘价", "adj_close")
INDUSTRY_KEYS = ("industry_l3", "sw_l3", "三级行业", "industry", "行业")


def _paths(data_dir: Optional[Path] = None) -> dict:
    d = Path(data_dir) if data_dir else DATA_DIR
    return {
        "dir": d,
        "bars": d / "bars.parquet",
        "index": d / "index.parquet",
        "universe": d / "universe.parquet",
        "meta": d / "meta.json",
    }


@lru_cache(maxsize=8)
def _read_parquet(path: str, mtime: float) -> Optional[pd.DataFrame]:
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _table(kind: str, data_dir: Optional[Path] = None) -> Optional[pd.DataFrame]:
    p = _paths(data_dir)[kind]
    if not p.exists():
        return None
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    return _read_parquet(str(p), mtime)


def _pick(df: pd.DataFrame, keys: tuple) -> Optional[str]:
    lower = {str(c).lower(): c for c in df.columns}
    for k in keys:
        if k in df.columns:
            return k
        if k.lower() in lower:
            return lower[k.lower()]
    return None


def _code_mask(series: pd.Series, code: str) -> pd.Series:
    """兼容 '300750' / 'sz399006' / '399006.SZ' 三种写法。"""
    s = series.astype(str)
    digits = s.str.replace(r"\D", "", regex=True).str.zfill(6)
    return (s.str.zfill(6) == code) | (digits == code)


def load_series(code: str, start: Optional[str] = None, end: Optional[str] = None,
                data_dir: Optional[Path] = None) -> Optional[pd.DataFrame]:
    """返回 DataFrame(date, close)，按日期升序；没有快照或没有该标的时返回 None。"""
    code = str(code).zfill(6)
    for kind in ("bars", "index"):
        df = _table(kind, data_dir)
        if df is None or df.empty:
            continue
        c_col, d_col, v_col = _pick(df, CODE_KEYS), _pick(df, DATE_KEYS), _pick(df, CLOSE_KEYS)
        if not (c_col and d_col and v_col):
            continue
        sub = df[_code_mask(df[c_col], code)]
        if sub.empty:
            continue
        out = pd.DataFrame({
            "date": pd.to_datetime(sub[d_col], errors="coerce"),
            "close": pd.to_numeric(sub[v_col], errors="coerce"),
        }).dropna().sort_values("date").reset_index(drop=True)
        if start:
            out = out[out["date"] >= pd.Timestamp(start)]
        if end:
            out = out[out["date"] <= pd.Timestamp(end)]
        if len(out):
            return out.reset_index(drop=True)
    return None


def available_index() -> Optional[str]:
    """快照里实际有哪些指数（队友这份只有创业板指 sz399006）。"""
    df = _table("index")
    if df is None or df.empty:
        return None
    c_col = _pick(df, CODE_KEYS)
    if not c_col:
        return None
    raw = str(df[c_col].iloc[0])
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits.zfill(6) if digits else raw


def industry_of(code: str, data_dir: Optional[Path] = None) -> Optional[str]:
    df = _table("universe", data_dir)
    if df is None or df.empty:
        return None
    c_col = _pick(df, CODE_KEYS)
    i_col = _pick(df, INDUSTRY_KEYS)
    if not (c_col and i_col):
        return None
    hit = df[df[c_col].astype(str).str.zfill(6) == str(code).zfill(6)]
    return None if hit.empty else str(hit.iloc[0][i_col])


def status(data_dir: Optional[Path] = None) -> dict:
    """给 UI 用的一句话状态：有没有快照、覆盖多少、区间多长。"""
    p = _paths(data_dir)
    info = {"available": False, "dir": str(p["dir"]), "reason": ""}
    if not p["bars"].exists():
        info["reason"] = "未找到 data/market/bars.parquet（队友的行情快照还没同步过来）"
        return info

    meta = {}
    if p["meta"].exists():
        try:
            meta = json.loads(p["meta"].read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}

    df = _table("bars", data_dir)
    if df is None:
        info["reason"] = "bars.parquet 读取失败（缺 pyarrow 或文件损坏）"
        return info

    d_col = _pick(df, DATE_KEYS)
    c_col = _pick(df, CODE_KEYS)
    dates = pd.to_datetime(df[d_col], errors="coerce") if d_col else None
    info.update({
        "available": True,
        "rows": int(len(df)),
        "codes": int(df[c_col].nunique()) if c_col else None,
        "start": dates.min().strftime("%Y-%m-%d") if dates is not None and len(dates.dropna()) else None,
        "end": dates.max().strftime("%Y-%m-%d") if dates is not None and len(dates.dropna()) else None,
        "meta": meta,
    })
    return info


def describe(data_dir: Optional[Path] = None) -> str:
    s = status(data_dir)
    if not s["available"]:
        return "行情底座：AkShare 在线（无本地快照）"
    return (f"行情底座：本地快照 {s['codes']} 只 / {s['rows']:,} 行 "
            f"（{s['start']} ~ {s['end']}）")


if __name__ == "__main__":
    print(describe())
