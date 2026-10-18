"""task_01 验收脚本：创业板 MACD + RSI + 量能 + 均线共振筛选。

用途：验证本地行情快照层能否支撑 RealFin 任务，并对照官方参考答案。
注意：官方 automated_checks 只校验文件/代码格式/关键词，不校验选股正确性；
本脚本额外计算与 reference_ans 的重合度，作为真实性校验。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import market_snapshot as ms  # noqa: E402

AS_OF = "2026-03-31"
WINDOW_START = "2026-03-04"
LOOKBACK = 120


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    dif = ema(close, 12) - ema(close, 26)
    dea = ema(dif, 9)
    return dif, dea


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def crossed_above(fast: pd.Series, slow: pd.Series, start: str, end: str) -> bool:
    cross = (fast.shift(1) <= slow.shift(1)) & (fast > slow)
    return bool(cross.loc[start:end].any())


def run() -> dict:
    close_panel = ms.load_panel(AS_OF, lookback=LOOKBACK, field="close")
    volume_panel = ms.load_panel(AS_OF, lookback=LOOKBACK, field="volume")
    if close_panel.empty or volume_panel.empty:
        raise RuntimeError("行情快照为空，先运行 python market_snapshot.py build")

    hits: list[dict] = []
    for code in close_panel.columns:
        close = close_panel[code].dropna()
        volume = volume_panel.get(code, pd.Series(dtype=float)).dropna()
        if len(close) < 60 or len(volume) < 60:
            continue

        dif, dea = macd(close)
        rsi14 = rsi(close)
        ma5, ma8 = close.rolling(5).mean(), close.rolling(8).mean()

        if not crossed_above(dif, dea, WINDOW_START, AS_OF):
            continue
        if not crossed_above(ma5, ma8, WINDOW_START, AS_OF):
            continue

        window_rsi = rsi14.loc[WINDOW_START:AS_OF]
        if window_rsi.empty or window_rsi.min() >= 30 or window_rsi.max() <= 50:
            continue

        vol_avg5 = volume.rolling(5).mean()
        spike_days = ((volume > 2 * vol_avg5) & (volume.index >= WINDOW_START)).sum()
        if spike_days < 2:
            continue

        hits.append(
            {
                "code": code,
                "rsi_min": round(float(window_rsi.min()), 2),
                "rsi_max": round(float(window_rsi.max()), 2),
                "volume_spike_days": int(spike_days),
            }
        )

    hits.sort(key=lambda x: (-x["volume_spike_days"], x["code"]))
    return {"as_of": AS_OF, "window": [WINDOW_START, AS_OF], "hits": hits}


def main() -> None:
    result = run()
    codes = [h["code"] for h in result["hits"]][:10]
    out = Path("result.txt")
    out.write_text("\n".join(codes) + ("\n" if codes else ""), encoding="utf-8")

    reference = ["300131", "300246", "300531", "300733"]
    overlap = sorted(set(codes) & set(reference))
    summary = {
        **{k: v for k, v in result.items() if k != "hits"},
        "candidate_count": len(result["hits"]),
        "written": len(codes),
        "reference_count": len(reference),
        "overlap_with_reference": overlap,
        "overlap_pct": round(len(overlap) / len(reference) * 100, 1) if reference else None,
        "note": "官方 automated_checks 不校验选股正确性；重合度仅作参考，数据源与复权口径不同会造成差异。",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
