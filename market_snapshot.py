"""本地行情快照层：一次性并发下载、落盘复用，按 as_of_date 严格切片。

RealFin 任务需要在创业板 1400+ 只股票上算指标，现场抓取远超任务超时，
因此先构建本地快照，上层只读快照、不直接联网。

数据源（2026-10-18 实测）：东方财富在本机被代理/网络拦截，不可用；
创业板清单走深交所官方接口，日线与指数走新浪，腾讯作为备用。

已知偏差（必须在报告里写明）：
- 股票池是当前清单，不含已退市股票（幸存者偏差）。
- 股本、行业为当前快照；历史市值/换手率用当前股本近似。
"""
from __future__ import annotations

import argparse
import json
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "market"
BARS_PATH = DATA_DIR / "bars.parquet"
UNIVERSE_PATH = DATA_DIR / "universe.parquet"
INDEX_PATH = DATA_DIR / "index.parquet"
META_PATH = DATA_DIR / "meta.json"

BOARD_PREFIX = {"创业板": "30", "科创板": "68", "主板": ("00", "60")}


def _sina_symbol(code: str) -> str:
    return ("sh" if code.startswith(("6", "9")) else "bj" if code.startswith(("4", "8")) else "sz") + code


def _to_int(value) -> int | None:
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def fetch_universe(board: str = "创业板") -> pd.DataFrame:
    """深交所官方 A 股清单：代码、简称、上市日期、总股本、流通股本、所属行业。"""
    import akshare as ak

    raw = ak.stock_info_sz_name_code(symbol="A股列表")
    df = pd.DataFrame(
        {
            "code": raw["A股代码"].astype(str).str.zfill(6),
            "name": raw["A股简称"].astype(str),
            "board": raw["板块"].astype(str),
            "list_date": raw["A股上市日期"].astype(str),
            "total_shares": raw["A股总股本"].map(_to_int),
            "float_shares": raw["A股流通股本"].map(_to_int),
            "industry": raw["所属行业"].astype(str),
        }
    )
    if board:
        df = df[df["board"] == board].copy()
    return df.reset_index(drop=True)


def _fetch_one(code: str, start: str, end: str, retries: int = 3) -> pd.DataFrame:
    import akshare as ak

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            df = ak.stock_zh_a_daily(
                symbol=_sina_symbol(code),
                start_date=start.replace("-", ""),
                end_date=end.replace("-", ""),
                adjust="qfq",
            )
            if df is None or df.empty:
                raise ValueError("empty response")
            out = df[["date", "open", "high", "low", "close", "volume", "amount"]].copy()
            out["date"] = out["date"].astype(str).str.slice(0, 10)
            if "turnover" in df.columns:
                out["turnover_pct"] = pd.to_numeric(df["turnover"], errors="coerce") * 100
            else:
                out["turnover_pct"] = pd.NA
            out["code"] = code
            return out
        except Exception as exc:  # noqa: BLE001 - 网络源异常类型不统一
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"{code}: {last_error!r}")


def fetch_index(start: str = "2024-01-01", end: str | None = None, symbol: str = "sz399006") -> pd.DataFrame:
    """新浪指数日线（创业板指默认 399006），不支持区间参数，取得后本地切片。"""
    import akshare as ak

    end = end or date.today().isoformat()
    df = ak.stock_zh_index_daily(symbol=symbol)
    df = df.copy()
    df["date"] = df["date"].astype(str).str.slice(0, 10)
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    df["symbol"] = symbol
    return df.reset_index(drop=True)


def build_snapshot(
    start: str = "2024-01-01",
    end: str | None = None,
    workers: int = 6,
    board: str = "创业板",
    limit: int | None = None,
    out_dir: Path = DATA_DIR,
    per_symbol_timeout: float = 15.0,
    resume: bool = True,
) -> dict:
    """构建本地快照。

    akshare 的新浪接口内部 requests 没有 timeout，长时间批量抓取会永久挂住；
    这里用 socket 默认超时兜底，并把每只股票单独落盘，支持断点续传。
    """
    end = end or date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    parts_dir = out_dir / "parts"
    parts_dir.mkdir(exist_ok=True)
    started = time.perf_counter()
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(per_symbol_timeout)

    universe = fetch_universe(board=board)
    codes = universe["code"].tolist()
    if limit:
        codes = codes[:limit]

    pending: list[str] = []
    for code in codes:
        part = parts_dir / f"{code}.parquet"
        if resume and part.exists():
            try:
                if not pd.read_parquet(part).empty:
                    continue
            except Exception:  # noqa: BLE001 - 损坏的分片重下
                pass
        pending.append(code)

    failures: list[dict] = []
    done = 0
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_fetch_one, code, start, end): code for code in pending}
            for future in as_completed(futures):
                code = futures[future]
                done += 1
                try:
                    frame = future.result()
                    frame.to_parquet(parts_dir / f"{code}.parquet", index=False)
                except Exception as exc:  # noqa: BLE001
                    failures.append({"code": code, "error": str(exc)[:200]})
                if done % 100 == 0 or done == len(pending):
                    print(f"  {done}/{len(pending)} downloaded, failures={len(failures)}", flush=True)
    finally:
        socket.setdefaulttimeout(old_timeout)

    parts = sorted(parts_dir.glob("*.parquet"))
    frames = []
    for part in parts:
        try:
            frame = pd.read_parquet(part)
            if not frame.empty:
                frames.append(frame)
        except Exception as exc:  # noqa: BLE001
            failures.append({"code": part.stem, "error": f"read part: {exc}"[:200]})

    if not frames:
        raise RuntimeError(f"no bars downloaded; first failures: {failures[:3]}")

    downloaded = {frame["code"].iloc[0] for frame in frames}
    universe = universe[universe["code"].isin(downloaded)].reset_index(drop=True)

    bars = pd.concat(frames, ignore_index=True)
    bars = bars.sort_values(["code", "date"]).reset_index(drop=True)

    index_df = fetch_index(start=start, end=end)
    bars.to_parquet(out_dir / "bars.parquet", index=False)
    universe.to_parquet(out_dir / "universe.parquet", index=False)
    index_df.to_parquet(out_dir / "index.parquet", index=False)

    meta = {
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "board": board,
        "start": start,
        "end": end,
        "requested_codes": len(codes),
        "resumed_codes": len(codes) - len(pending),
        "pending_this_run": len(pending),
        "downloaded_codes": len(frames),
        "failed_codes": len(failures),
        "per_symbol_timeout": per_symbol_timeout,
        "parts_dir": str(parts_dir),
        "failures_sample": failures[:10],
        "bar_rows": len(bars),
        "date_min": str(bars["date"].min()),
        "date_max": str(bars["date"].max()),
        "sources": {"universe": "SZSE stock_info_sz_name_code", "bars": "Sina stock_zh_a_daily (qfq)", "index": "Sina stock_zh_index_daily"},
        "known_biases": [
            "股票池为当前清单，不含已退市股票（幸存者偏差）",
            "股本与行业为当前快照，历史市值/换手率用当前股本近似",
        ],
        "elapsed_seconds": round(time.perf_counter() - started, 1),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def fetch_sina_sectors(workers: int = 4) -> pd.DataFrame:
    """新浪行业板块 → 个股映射。49 个板块，每板块一次请求。"""
    import akshare as ak

    boards = ak.stock_sector_spot(indicator="新浪行业")[["label", "板块"]].drop_duplicates()
    rows: list[dict] = []

    def _one(label: str, name: str) -> list[dict]:
        try:
            members = ak.stock_sector_detail(sector=label)
        except Exception:  # noqa: BLE001
            return []
        return [
            {"code": str(r["code"]).zfill(6), "sina_sector": name}
            for _, r in members.iterrows()
            if str(r.get("code", "")).strip()
        ]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, r["label"], r["板块"]) for _, r in boards.iterrows()]
        for future in as_completed(futures):
            rows.extend(future.result())
    return pd.DataFrame(rows).drop_duplicates(subset="code") if rows else pd.DataFrame(columns=["code", "sina_sector"])


def enrich_universe_with_sectors(out_dir: Path = DATA_DIR) -> dict:
    """给已建股票池补新浪行业字段，不触碰行情数据。"""
    universe_path = _require(out_dir / "universe.parquet")
    universe = pd.read_parquet(universe_path)
    sectors = fetch_sina_sectors()
    merged = universe.drop(columns=["sina_sector"], errors="ignore").merge(sectors, on="code", how="left")
    merged.to_parquet(universe_path, index=False)
    return {
        "universe_rows": len(merged),
        "industry_coverage_pct": round(merged["sina_sector"].notna().mean() * 100, 2),
        "sectors": int(merged["sina_sector"].nunique()),
    }


def _require(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"快照不存在：{path}；先运行 python market_snapshot.py build")
    return path


def load_bars(as_of_date: str, codes: list[str] | None = None) -> pd.DataFrame:
    """读取 date <= as_of_date 的日线，严格禁止未来数据。"""
    bars = pd.read_parquet(_require(BARS_PATH))
    bars = bars[bars["date"] <= as_of_date]
    if codes:
        bars = bars[bars["code"].isin(codes)]
    return bars.reset_index(drop=True)


def load_panel(as_of_date: str, lookback: int = 60, field: str = "close", codes: list[str] | None = None) -> pd.DataFrame:
    """返回宽表：index=交易日，columns=股票代码，仅含 as_of 前 lookback 个交易日。"""
    bars = load_bars(as_of_date, codes)
    if bars.empty:
        return pd.DataFrame()
    dates = sorted(bars["date"].unique())[-lookback:]
    bars = bars[bars["date"].isin(dates)]
    return bars.pivot(index="date", columns="code", values=field).sort_index()


def load_universe(as_of_date: str | None = None, codes: list[str] | None = None) -> pd.DataFrame:
    """股票池与静态字段。注意：清单是当前快照，存在幸存者偏差。"""
    universe = pd.read_parquet(_require(UNIVERSE_PATH))
    if codes:
        universe = universe[universe["code"].isin(codes)]
    return universe.reset_index(drop=True)


def load_index(as_of_date: str, lookback: int | None = None) -> pd.DataFrame:
    index_df = pd.read_parquet(_require(INDEX_PATH))
    index_df = index_df[index_df["date"] <= as_of_date].sort_values("date")
    if lookback:
        index_df = index_df.tail(lookback)
    return index_df.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="构建本地行情快照")
    sub = parser.add_subparsers(dest="cmd", required=True)
    build = sub.add_parser("build", help="下载并落盘")
    build.add_argument("--start", default="2024-01-01")
    build.add_argument("--end", default=None)
    build.add_argument("--workers", type=int, default=6)
    build.add_argument("--timeout", type=float, default=15.0, help="单只股票 socket 超时（秒）")
    build.add_argument("--no-resume", action="store_true", help="忽略已有分片，全部重下")
    build.add_argument("--board", default="创业板")
    build.add_argument("--limit", type=int, default=None)
    sub.add_parser("sectors", help="给股票池补充新浪行业字段")
    args = parser.parse_args()

    if args.cmd == "build":
        meta = build_snapshot(
            start=args.start,
            end=args.end,
            workers=args.workers,
            board=args.board,
            limit=args.limit,
            per_symbol_timeout=args.timeout,
            resume=not args.no_resume,
        )
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    elif args.cmd == "sectors":
        print(json.dumps(enrich_universe_with_sectors(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
