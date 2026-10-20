"""行情字段口径：历史流通市值只接受不复权价格和有可用日期的股本记录。"""
from __future__ import annotations

import pandas as pd
import math


def add_float_market_cap(bars: pd.DataFrame, share_history: pd.DataFrame,
                         as_of_date: str) -> pd.DataFrame:
    """返回元计价市值及逐行状态；绝不使用当前股本替代未知历史股本。

    bars: code/date/close/price_adjustment，price_adjustment 必须明确为 raw。
    share_history: code/effective_date/available_date/float_shares（股）。
    available_date 是该股本记录当时已公开的日期，不能用下载日期冒充。
    """
    cutoff = pd.Timestamp(as_of_date)
    result = bars.loc[pd.to_datetime(bars["date"]) <= cutoff].copy().reset_index(drop=True)
    result["float_market_cap"] = float("nan")
    result["float_market_cap_status"] = "missing_historical_share_history"
    if not share_history.empty:
        required = {"code", "effective_date", "available_date", "float_shares"}
        if not required <= set(share_history):
            raise ValueError(f"股本记录缺少字段：{sorted(required - set(share_history))}")
        shares = share_history.copy()
        for field in ("effective_date", "available_date"):
            shares[field] = pd.to_datetime(shares[field], errors="coerce")
        shares["float_shares"] = pd.to_numeric(shares["float_shares"], errors="coerce")
        if shares.groupby(["code", "effective_date", "available_date"])["float_shares"].nunique().gt(1).any():
            raise ValueError("同一代码、生效日期、可用日期有冲突的股本记录")
    else:
        shares = share_history
    for index, row in result.iterrows():
        if row.get("price_adjustment") != "raw":
            result.at[index, "float_market_cap_status"] = "unsupported_adjusted_price"
            continue
        price = pd.to_numeric(row["close"], errors="coerce")
        if pd.isna(price) or not math.isfinite(price) or price <= 0:
            result.at[index, "float_market_cap_status"] = "missing_raw_price"
            continue
        if shares.empty:
            continue
        day = pd.Timestamp(row["date"])
        known = shares.loc[(shares["code"] == row["code"]) &
                           (shares["effective_date"] <= day) &
                           (shares["available_date"] <= day)]
        if known.empty:
            continue
        latest = known.sort_values(["effective_date", "available_date"]).iloc[-1]
        if pd.notna(latest["float_shares"]) and math.isfinite(latest["float_shares"]) and latest["float_shares"] > 0:
            value = float(price * latest["float_shares"])
            if math.isfinite(value):
                result.at[index, "float_market_cap"] = value
                result.at[index, "float_market_cap_status"] = "dated_raw_price_and_shares"
    return result.reset_index(drop=True)
