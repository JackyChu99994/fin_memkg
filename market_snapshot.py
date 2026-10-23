"""本地行情快照层：一次性并发下载、落盘复用，按 as_of_date 严格切片。

RealFin 任务需要在创业板 1400+ 只股票上算指标，现场抓取远超任务超时，
因此先构建本地快照，上层只读快照、不直接联网。

股票清单走深交所官方接口，日线与指数走新浪；分钟线与细分行业
由各自模块提供。本模块不把未实现的备用源算作可用能力。

已知偏差（必须在报告里写明）：
- 股票池是当前清单，不含已退市股票（幸存者偏差）。
- 股本、行业为采集时快照，不能直接用于准确的历史市值。
- 换手率来自新浪逐日 turnover 序列并转换为百分比，不以当前股本重算。
- 前复权价格采用采集时复权基准，并非逐时点可见的复权数据库。
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import re
import time
import uuid
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


def _day(value: str) -> str:
    value = str(value)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(value).isoformat()


def _code(value) -> str:
    code = str(value).strip().lower()
    code = re.sub(r"^(sh|sz|bj)", "", code)
    code = re.sub(r"\.(sh|sz|bj)$", "", code)
    if not code.isdigit() or len(code) > 6:
        raise ValueError(f"invalid stock code: {value!r}")
    return code.zfill(6)


def _process_call(conn, function, args, kwargs):
    try:
        conn.send((True, function(*args, **kwargs)))
    except Exception as exc:  # third-party network exceptions vary
        conn.send((False, f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


def bounded_call(function, *args, timeout: float = 5.0, **kwargs):
    """Run a network operation in a killable subprocess; includes import/startup time."""
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_process_call, args=(child, function, args, kwargs))
    process.start()
    child.close()
    try:
        if not parent.poll(timeout):
            raise TimeoutError(f"{function.__name__} exceeded {timeout:g}s")
        ok, result = parent.recv()
        if not ok:
            raise RuntimeError(result)
        return result
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join(timeout=1)
        parent.close()


def _json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, value: dict):
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def snapshot_paths(data_dir: Path = DATA_DIR) -> dict[str, Path]:
    """Resolve one immutable generation, or the pre-generation legacy snapshot."""
    data_dir = Path(data_dir)
    manifest = _json(data_dir / "CURRENT.json")
    root = data_dir / manifest["generation"] if manifest else data_dir
    if not root.resolve().is_relative_to(data_dir.resolve()):
        raise ValueError("snapshot generation must remain inside data_dir")
    return {key: root / name for key, name in {
        "bars": "bars.parquet", "universe": "universe.parquet",
        "index": "index.parquet", "meta": "meta.json"}.items()}


def publish_snapshot(bars: pd.DataFrame, universe: pd.DataFrame, index: pd.DataFrame,
                     meta: dict, data_dir: Path = DATA_DIR) -> dict[str, Path]:
    """Publish all four files with a single atomic pointer; retain last good files."""
    data_dir = Path(data_dir)
    generation = Path("snapshots") / uuid.uuid4().hex
    root = data_dir / generation
    root.mkdir(parents=True)
    for name, frame in (("bars", bars), ("universe", universe), ("index", index)):
        frame.to_parquet(root / f"{name}.parquet", index=False)
    _atomic_json(root / "meta.json", meta)
    _atomic_json(data_dir / "CURRENT.json", {"generation": generation.as_posix()})
    return snapshot_paths(data_dir)


def _covers(meta: dict, start: str, end: str) -> bool:
    return bool(meta.get("start") and meta.get("end")
                and meta["start"] <= start and meta["end"] >= end)


def _clean_bars(frame: pd.DataFrame, code: str | None = None) -> pd.DataFrame:
    frame = frame.copy()
    required = {"code", "date", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame):
        raise ValueError(f"missing columns: {sorted(required - set(frame))}")
    frame["code"] = frame["code"].map(_code)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.strftime("%Y-%m-%d")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if code and not frame["code"].eq(code).all():
        raise ValueError(f"part contains other codes than {code}")
    if frame.duplicated(["code", "date"]).any():
        raise ValueError("duplicate stock/date rows")
    if frame[list(required)].isna().any().any():
        raise ValueError("missing OHLCV/code/date values")
    return frame.sort_values(["code", "date"]).reset_index(drop=True)


def _sina_symbol(code: str) -> str:
    return ("sh" if code.startswith(("6", "9")) else "bj" if code.startswith(("4", "8")) else "sz") + code


def _to_int(value) -> int | None:
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def fetch_universe(board: str = "创业板") -> pd.DataFrame:
    """深交所官方 A 股清单：代码、简称、上市日期、总股本、流通股本、所属行业。"""
    if board not in ("创业板", "深圳主板"):
        raise ValueError("SZSE source supports 创业板 or 深圳主板 only; 沪市/科创板 require another source")
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
    df = df[df["board"] == ("主板" if board == "深圳主板" else board)].copy()
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
    """Range-aware resume; refresh an entire symbol history when its qfq range changes.

    Network work is explicitly offline preparation. Failed runs keep their successful
    parts for resume, write last_attempt.json, and never replace the active snapshot.
    Coverage means the interval queried successfully, not a guarantee of daily trading.
    """
    start, end = _day(start), _day(end or date.today().isoformat())
    if start > end or end > date.today().isoformat():
        raise ValueError("require start <= end <= collection date")
    if board not in ("创业板", "深圳主板"):
        raise ValueError("use 创业板 or 深圳主板; this source does not cover Shanghai")
    if workers < 1 or (limit is not None and limit < 1) or per_symbol_timeout <= 0:
        raise ValueError("workers, limit and timeout must be positive")
    out_dir = Path(out_dir)
    parts_dir = out_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    paths = snapshot_paths(out_dir)
    old_meta = _json(paths["meta"])
    failures = []
    pending, frames, coverage = [], {}, {}
    universe = pd.DataFrame()
    meta = {"board": board, "start": start, "end": end, "published": False,
            "sources": {"universe": "SZSE stock_info_sz_name_code",
                        "bars": "Sina stock_zh_a_daily (qfq)",
                        "index": "Sina stock_zh_index_daily"}}
    try:
        # Reuse a cached listing for same-board historical/repeated runs. Extending
        # forward refreshes the listing so new listings are not silently missed.
        if (resume and paths["universe"].exists() and old_meta.get("board") == board
                and old_meta.get("end", "") >= end
                and old_meta.get("universe_complete", old_meta.get("requested_codes") == old_meta.get("downloaded_codes"))):
            universe = pd.read_parquet(paths["universe"])
        else:
            universe = bounded_call(fetch_universe, board=board, timeout=per_symbol_timeout)
        universe["code"] = universe["code"].map(_code)
        universe["list_date"] = pd.to_datetime(universe["list_date"], errors="raise").dt.strftime("%Y-%m-%d")
        universe = universe.drop_duplicates("code").sort_values("code")
        universe = universe[universe["list_date"].le(end)].reset_index(drop=True)
        full_count = len(universe)
        if limit is not None:
            universe = universe.head(limit).copy()
        codes = universe["code"].tolist()
        if not codes:
            raise ValueError("requested stock universe is empty")
        for code in codes:
            part = parts_dir / f"{code}.parquet"
            cached, info = pd.DataFrame(), {}
            if part.exists():
                try:
                    cached = _clean_bars(pd.read_parquet(part), code)
                    info = _json(part.with_suffix(".json"))
                    if not info and old_meta.get("board") == board and old_meta.get("failed_codes") == 0:
                        # Adopt only legacy parts that were part of the previous
                        # complete published build. Preserve their queried range.
                        if (not cached.empty and old_meta.get("start", "") <= cached["date"].min()
                                and cached["date"].max() <= old_meta.get("end", "")):
                            info = {"start": old_meta["start"], "end": old_meta["end"],
                                    "legacy_adopted": True, "adjust": "qfq"}
                            _atomic_json(part.with_suffix(".json"), info)
                except Exception:
                    cached = pd.DataFrame()
            if resume and not cached.empty and _covers(info, start, end):
                frames[code], coverage[code] = cached, info
            else:
                # Never append to old qfq rows: later corporate actions can change
                # their adjustment basis. Download one consistent union interval.
                fetch_start = min(start, str(cached["date"].min())) if not cached.empty else start
                fetch_end = max(end, str(cached["date"].max())) if not cached.empty else end
                fetch_start, fetch_end = min(fetch_start, info.get("start", fetch_start)), max(fetch_end, info.get("end", fetch_end))
                pending.append((code, fetch_start, fetch_end))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(bounded_call, _fetch_one, code, lo, hi,
                                   retries=1, timeout=per_symbol_timeout): (code, lo, hi)
                       for code, lo, hi in pending}
            for done, future in enumerate(as_completed(futures), 1):
                code, lo, hi = futures[future]
                try:
                    frame = _clean_bars(future.result(), code)
                    frame = frame[frame["date"].between(lo, hi)].reset_index(drop=True)
                    if frame.empty:
                        raise ValueError("empty bars for requested range")
                    part = parts_dir / f"{code}.parquet"
                    temp = part.with_suffix(".tmp.parquet")
                    frame.to_parquet(temp, index=False)
                    # Invalidate coverage first. An interruption cannot leave a new
                    # data file falsely paired with previous coverage metadata.
                    _atomic_json(part.with_suffix(".json"), {"refresh_incomplete": True})
                    temp.replace(part)
                    info = {"start": lo, "end": hi, "adjust": "qfq",
                            "date_min": frame["date"].min(), "date_max": frame["date"].max(),
                            "rows": len(frame), "fetched_at": datetime.now().isoformat(timespec="seconds")}
                    _atomic_json(part.with_suffix(".json"), info)
                    frames[code], coverage[code] = frame, info
                except Exception as exc:
                    failures.append({"code": code, "error": str(exc)[:500]})
                if done % 100 == 0 or done == len(pending):
                    print(f"  {done}/{len(pending)} downloaded, failures={len(failures)}", flush=True)
        meta.update(requested_codes=len(codes), resumed_codes=len(codes)-len(pending),
                    pending_this_run=len(pending), downloaded_codes=len(frames),
                    universe_complete=limit is None or limit >= full_count,
                    per_symbol_timeout=per_symbol_timeout, parts_dir=str(parts_dir))
        if failures:
            raise RuntimeError("some symbols failed; previous active snapshot retained")
        bars = pd.concat([frames[code] for code in codes], ignore_index=True)
        bars = bars[bars["date"].between(start, end)].sort_values(["code", "date"]).reset_index(drop=True)
        if bars.empty:
            raise ValueError("no bars in selected range")
        index_coverage = old_meta.get("index_coverage", old_meta)
        if resume and paths["index"].exists() and _covers(index_coverage, start, end):
            index_df = pd.read_parquet(paths["index"])
        else:
            index_df = bounded_call(fetch_index, start=start, end=end, timeout=per_symbol_timeout)
        index_df = index_df.copy()
        index_df["date"] = pd.to_datetime(index_df["date"], errors="raise").dt.strftime("%Y-%m-%d")
        index_df = index_df[index_df["date"].between(start, end)].sort_values("date").reset_index(drop=True)
        if index_df.empty or index_df.duplicated(["date", "symbol"]).any():
            raise ValueError("index data is empty or duplicated")
        meta.update(built_at=datetime.now().isoformat(timespec="seconds"), published=True,
                    bar_rows=len(bars), date_min=str(bars["date"].min()), date_max=str(bars["date"].max()),
                    index_coverage={"start": start, "end": end, "date_min": index_df["date"].min(),
                                    "date_max": index_df["date"].max(), "rows": len(index_df)},
                    coverage=[{"code": code, "date_min": frame["date"].min(),
                               "date_max": frame["date"].max(), "rows": len(frame)}
                              for code, frame in bars.groupby("code", sort=True)],
                    known_biases=["当前股票清单按上市日过滤，不含已退市股票（幸存者偏差）",
                                  "行业、股本为采集时快照，不能当作历史时点数据",
                                  "前复权基准为采集时基准；历史回测不是逐时点复权数据库",
                                  "区间已查询不等于每个交易日都有数据；停牌、源缺口需按实际覆盖审计"])
    except Exception as exc:
        failures.append({"stage": "build", "error": str(exc)[:500]})
        meta["published"] = False
    meta.update(failed_codes=len({item["code"] for item in failures if "code" in item}),
                failures=failures, failures_sample=failures[:10],
                elapsed_seconds=round(time.perf_counter()-started, 2))
    if meta["published"]:
        try:
            publish_snapshot(bars, universe, index_df, meta, out_dir)
        except Exception as exc:
            meta["published"] = False
            failures.append({"stage": "publish", "error": str(exc)[:500]})
    _atomic_json(out_dir / "last_attempt.json", meta)
    if not meta["published"]:
        raise RuntimeError(f"snapshot not published; inspect {out_dir / 'last_attempt.json'}: {failures[:3]}")
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
    paths = snapshot_paths(out_dir)
    universe_path = _require(paths["universe"])
    universe = pd.read_parquet(universe_path)
    sectors = fetch_sina_sectors()
    merged = universe.drop(columns=["sina_sector"], errors="ignore").merge(sectors, on="code", how="left")
    publish_snapshot(pd.read_parquet(paths["bars"]), merged,
                     pd.read_parquet(paths["index"]), _json(paths["meta"]), out_dir)
    return {
        "universe_rows": len(merged),
        "industry_coverage_pct": round(merged["sina_sector"].notna().mean() * 100, 2),
        "sectors": int(merged["sina_sector"].nunique()),
    }


def _require(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"快照不存在：{path}；先运行 python market_snapshot.py build")
    return path


def load_bars(as_of_date: str, codes: list[str] | None = None,
              data_dir: Path = DATA_DIR, start_date: str | None = None) -> pd.DataFrame:
    """Offline daily bars through as_of_date; optional inclusive start_date.

    Dates must be ISO dates. [] means no stocks, None means the dated universe.
    Listing dates are filtered; historical delisted constituents are unavailable.
    """
    as_of_date = _day(as_of_date)
    if start_date is not None:
        start_date = _day(start_date)
        if start_date > as_of_date:
            raise ValueError("start_date must not exceed as_of_date")
    paths = snapshot_paths(data_dir)
    bars = pd.read_parquet(_require(paths["bars"]))
    bars["date"] = pd.to_datetime(bars["date"], errors="raise").dt.strftime("%Y-%m-%d")
    bars["code"] = bars["code"].map(_code)
    bars = bars[bars["date"] <= as_of_date]
    if start_date:
        bars = bars[bars["date"] >= start_date]
    universe = _read_universe(paths["universe"], as_of_date, codes)
    bars = bars.merge(universe[["code", "list_date"]], on="code", how="inner", validate="many_to_one")
    bars = bars[bars["date"] >= bars["list_date"]].drop(columns="list_date")
    return bars.sort_values(["code", "date"]).reset_index(drop=True)


def load_panel(as_of_date: str, lookback: int = 60, field: str = "close",
               codes: list[str] | None = None, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Offline panel over the last N distinct market dates (not per-stock N bars)."""
    if lookback < 1:
        raise ValueError("lookback must be positive")
    bars = load_bars(as_of_date, codes, data_dir=data_dir)
    if bars.empty:
        return pd.DataFrame()
    dates = sorted(bars["date"].unique())[-lookback:]
    bars = bars[bars["date"].isin(dates)]
    return bars.pivot(index="date", columns="code", values=field).sort_index()


def _read_universe(path: Path, as_of_date: str | None, codes: list[str] | None) -> pd.DataFrame:
    universe = pd.read_parquet(_require(path)).copy()
    universe["code"] = universe["code"].map(_code)
    if universe["code"].duplicated().any():
        raise ValueError("duplicate universe codes")
    universe["list_date"] = pd.to_datetime(universe["list_date"], errors="raise").dt.strftime("%Y-%m-%d")
    if as_of_date is not None:
        universe = universe[universe["list_date"].le(_day(as_of_date))]
    if codes is not None:
        universe = universe[universe["code"].isin([_code(code) for code in codes])]
    return universe.reset_index(drop=True)


def load_universe(as_of_date: str | None = None, codes: list[str] | None = None,
                  data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """股票池与静态字段。注意：清单是当前快照，存在幸存者偏差。"""
    return _read_universe(snapshot_paths(data_dir)["universe"], as_of_date, codes)


def load_index(as_of_date: str, lookback: int | None = None,
               data_dir: Path = DATA_DIR) -> pd.DataFrame:
    as_of_date = _day(as_of_date)
    if lookback is not None and lookback < 1:
        raise ValueError("lookback must be positive")
    index_df = pd.read_parquet(_require(snapshot_paths(data_dir)["index"]))
    index_df["date"] = pd.to_datetime(index_df["date"], errors="raise").dt.strftime("%Y-%m-%d")
    index_df = index_df[index_df["date"] <= as_of_date].sort_values("date")
    if lookback:
        index_df = index_df.tail(lookback)
    return index_df.reset_index(drop=True)


def get_bars(codes: list[str], as_of_date: str, start_date: str,
             data_dir: Path = DATA_DIR, allow_fetch: bool = False,
             timeout: float = 5.0, max_fetch_codes: int = 5) -> pd.DataFrame:
    """Cache-first interval query with optional bounded small-batch network fallback.

    DataFrame.attrs['coverage'] describes unavailable/partial symbols explicitly.
    The universe must already exist. This never builds a full market during a task.
    Per-code fallback replaces the whole requested qfq interval; it does not append.
    """
    start_date, as_of_date = _day(start_date), _day(as_of_date)
    if start_date > as_of_date or timeout <= 0 or max_fetch_codes < 0:
        raise ValueError("invalid range, timeout, or max_fetch_codes")
    codes = list(dict.fromkeys(_code(code) for code in codes))
    paths = snapshot_paths(data_dir)
    universe = _read_universe(paths["universe"], as_of_date, codes)
    eligible = set(universe["code"])
    invalid = sorted(set(codes) - eligible)
    if invalid:
        raise ValueError(f"unknown or not-yet-listed stocks at {as_of_date}: {invalid}")
    try:
        bars = load_bars(as_of_date, codes, data_dir, start_date)
    except FileNotFoundError:
        bars = pd.DataFrame(columns=["code", "date", "open", "high", "low", "close", "volume"])
    meta = _json(paths["meta"])
    query_dir = Path(data_dir) / "query_cache"
    report, frames = [], []
    deadline, fetch_count = time.monotonic() + timeout, 0
    for code in codes:
        selected = bars[bars["code"].eq(code)].copy()
        status = {"code": code, "complete": _covers(meta, start_date, as_of_date) and not selected.empty,
                  "source": "snapshot"}
        part = query_dir / f"{code}.parquet"
        info = _json(part.with_suffix(".json"))
        if not status["complete"] and part.exists() and _covers(info, start_date, as_of_date):
            try:
                cached = _clean_bars(pd.read_parquet(part), code)
                selected = cached[cached["date"].between(start_date, as_of_date)].copy()
                status.update(complete=not selected.empty, source="query_cache")
            except Exception as exc:
                status["error"] = str(exc)[:200]
        remaining = deadline-time.monotonic()
        if not status["complete"] and allow_fetch and fetch_count < max_fetch_codes and remaining > 0:
            fetch_count += 1
            try:
                fresh = bounded_call(_fetch_one, code, start_date, as_of_date, retries=1, timeout=remaining)
                fresh = _clean_bars(fresh, code)
                fresh = fresh[fresh["date"].between(start_date, as_of_date)].copy()
                if fresh.empty:
                    raise ValueError("empty source response")
                query_dir.mkdir(parents=True, exist_ok=True)
                temp = part.with_suffix(".tmp.parquet")
                fresh.to_parquet(temp, index=False)
                _atomic_json(part.with_suffix(".json"), {"refresh_incomplete": True})
                temp.replace(part)
                _atomic_json(part.with_suffix(".json"), {"start": start_date, "end": as_of_date})
                selected = fresh
                status.update(complete=True, source="network")
            except Exception as exc:
                status["error"] = str(exc)[:200]
        list_date = universe.loc[universe["code"].eq(code), "list_date"].iloc[0]
        selected = selected[selected["date"].ge(list_date)]
        status.update(rows=len(selected),
                      date_min=None if selected.empty else selected["date"].min(),
                      date_max=None if selected.empty else selected["date"].max())
        if not status["complete"]:
            status.setdefault("error", "cache range missing; network disabled, budget exhausted, or fetch limit reached")
        report.append(status)
        frames.append(selected)
    result = pd.concat(frames, ignore_index=True) if frames else bars.iloc[:0].copy()
    result.attrs["coverage"] = report
    result.attrs["coverage_note"] = "complete means successfully queried interval; source gaps/suspensions may remain"
    return result.sort_values(["code", "date"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="构建本地行情快照")
    sub = parser.add_subparsers(dest="cmd", required=True)
    build = sub.add_parser("build", help="下载并落盘")
    build.add_argument("--start", default="2024-01-01")
    build.add_argument("--end", default=None)
    build.add_argument("--workers", type=int, default=6)
    build.add_argument("--timeout", type=float, default=15.0, help="每次下载的子进程时间上限，含启动（秒）")
    build.add_argument("--no-resume", action="store_true", help="忽略已有分片，全部重下")
    build.add_argument("--board", default="创业板")
    build.add_argument("--limit", type=int, default=None)
    build.add_argument("--out-dir", type=Path, default=DATA_DIR)
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
            out_dir=args.out_dir,
        )
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    elif args.cmd == "sectors":
        print(json.dumps(enrich_universe_with_sectors(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
