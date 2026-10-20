"""申万 2021 细分行业快照；来源、缺失和可用时间显式保存。

默认使用申万官网批量历史归属和分类字典。历史文件可能追溯修订；默认拒绝将
今天取得的分类用于过去的分析；allow_current_snapshot=True 只适合已披露的比较。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "https://legulegu.com"
CATALOG_URL = BASE + "/stockdata/sw-industry-overview"
DATA_DIR = Path(__file__).resolve().parent / "data" / "market"
SHANGHAI = timezone(timedelta(hours=8))
SW_BASE = "https://www.swsresearch.com/swindex/pdf/SwClass2021/"


def _write_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def parse_catalog(html: str) -> list[dict]:
    """仅使用来源明确标注的层级和父级，不按公司名称推测行业。"""
    soup, rows = BeautifulSoup(html, "html.parser"), []
    for level in (1, 2, 3):
        section = soup.find(id=f"level{level}Items")
        if section is None:
            raise ValueError(f"行业目录缺少 level{level}Items")
        for item in section.select(".lg-industries-item"):
            name = item.select_one(".lg-industries-item-number")
            parent = item.select_one(".parent-industry-name")
            rows.append({
                "industry_code": item["id"], "level": level,
                "industry_name": name.get_text(strip=True).split("(")[0],
                "parent_name": parent.get_text(strip=True).strip("[]") if parent else None,
            })
    if not rows:
        raise ValueError("行业目录为空")
    return rows


def parse_members(html: str) -> tuple[list[dict], str | None]:
    """只解析股票代码、纳入时间，避免网页 JSON-LD 混入 HTML 表头。"""
    soup, rows = BeautifulSoup(html, "html.parser"), []
    for item in soup.select("tr.index-basic-composition-item"):
        code = str(item.get("data-stock-code", "")).split(".")[0]
        cells = item.find_all("td")
        if re.fullmatch(r"\d{6}", code) and len(cells) >= 4:
            rows.append({"code": code, "source_member_since": cells[3].get_text(strip=True)})
    if not rows:
        raise ValueError("成分页面未返回可识别记录")
    source_date = re.search(r'"description"\s*:\s*"(\d{4}-\d{2}-\d{2})', html)
    return rows, source_date.group(1) if source_date else None


def _download(url: str, timeout: float, direct: bool) -> str:
    # direct 仅关闭进程内 requests 的环境代理；始终保留 TLS 证书验证。
    with requests.Session() as session:
        session.trust_env = not direct
        response = session.get(url, timeout=(timeout, timeout),
                               headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return response.content.decode("utf-8")


def assemble_mapping(universe: pd.DataFrame, catalog: list[dict],
                     memberships: list[dict], level: int) -> tuple[pd.DataFrame, dict]:
    """覆盖全部股票池；重复归属不擅自择一，显式标记 conflict。"""
    lookup = {(row["level"], row["industry_name"]): row for row in catalog}
    frame = pd.DataFrame(memberships)
    groups = {code: group for code, group in frame.groupby("code")} if not frame.empty else {}
    rows, conflicts = [], {}
    for code in universe["code"].astype(str).str.zfill(6):
        row = {"code": code, "scheme": "SW2021", "level": level,
               "classification_method": "source_membership", "status": "missing"}
        members = groups.get(code)
        if members is not None:
            members = members.drop_duplicates("industry_code")
            if len(members) > 1:
                row["status"] = "conflict"
                conflicts[code] = members["industry_code"].tolist()
            else:
                row.update(members.iloc[0].to_dict())
                row["status"] = "mapped"
                item = lookup[(level, row["industry_name"])]
                for depth in range(level, 0, -1):
                    row[f"level{depth}_code"] = item["industry_code"]
                    row[f"level{depth}_name"] = item["industry_name"]
                    if depth > 1:
                        item = lookup[(depth - 1, item["parent_name"])]
        rows.append(row)
    result = pd.DataFrame(rows)
    mapped = int(result["status"].eq("mapped").sum())
    return result, {
        "universe_count": len(result), "mapped_count": mapped,
        "coverage_pct": round(100 * mapped / max(len(result), 1), 2),
        "missing_codes": result.loc[result["status"].eq("missing"), "code"].tolist(),
        "conflicts": conflicts, "source": "Legulegu / SW2021 current constituents",
        "point_in_time_history": False,
    }


def build_legulegu(data_dir: Path = DATA_DIR, level: int = 3, workers: int = 4,
                  timeout: float = 5, budget: float = 180, direct: bool = False,
                  refresh: bool = False) -> dict:
    """预先构建；局部失败记入报告，已有成功分片可断点续传。"""
    from market_snapshot import bounded_call, load_universe

    if level not in (2, 3) or workers < 1 or timeout <= 0 or budget <= 0:
        raise ValueError("level 必须为 2/3，workers、timeout、budget 必须为正")
    started = time.monotonic()
    directory = Path(data_dir) / "industries"
    directory.mkdir(parents=True, exist_ok=True)
    parts = directory / "parts"
    parts.mkdir(exist_ok=True)
    observed = datetime.now(SHANGHAI).isoformat(timespec="seconds")
    catalog_path = directory / "catalog.json"
    if catalog_path.exists() and not refresh:
        catalog_doc = json.loads(catalog_path.read_text(encoding="utf-8"))
    else:
        catalog_doc = {"observed_at": observed, "source_url": CATALOG_URL,
                       "rows": parse_catalog(bounded_call(_download, CATALOG_URL, timeout, direct, timeout=timeout))}
        _write_json(catalog_path, catalog_doc)
    catalog = catalog_doc["rows"]
    chosen = [row for row in catalog if row["level"] == level]
    failures, memberships = [], []
    limited = threading.Event()

    def fetch(item: dict) -> dict:
        target = parts / f"{item['industry_code']}.json"
        if target.exists() and not refresh:
            return json.loads(target.read_text(encoding="utf-8"))
        remaining = budget - (time.monotonic() - started)
        if remaining <= 0 or limited.is_set():
            raise TimeoutError("行业构建总预算已用完；可重跑续传")
        url = BASE + "/stockdata/index-composition?industryCode=" + item["industry_code"]
        try:
            html = bounded_call(_download, url, timeout, direct, timeout=min(timeout, remaining))
        except Exception as exc:
            if "429" in str(exc):
                limited.set()
            raise
        members, source_date = parse_members(html)
        acquired = datetime.now(SHANGHAI).isoformat(timespec="seconds")
        doc = {"industry_code": item["industry_code"], "industry_name": item["industry_name"],
               "source_url": url, "source_data_date": source_date, "observed_at": acquired,
               "rows": members}
        _write_json(target, doc)
        return doc

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(fetch, item): item for item in chosen}
        for future in as_completed(pending):
            item = pending[future]
            try:
                doc = future.result()
                provenance = {key: value for key, value in doc.items() if key != "rows"}
                for member in doc["rows"]:
                    memberships.append({**member, **provenance})
            except Exception as exc:
                failures.append({"industry_code": item["industry_code"], "error": str(exc)[:300]})
    universe = load_universe(data_dir=Path(data_dir))
    mapping, report = assemble_mapping(universe, catalog, memberships, level)
    # All classifications require both member and catalog observations.
    if "observed_at" in mapping:
        mapping["available_at"] = mapping["observed_at"].map(
            lambda value: max(value, catalog_doc["observed_at"]) if isinstance(value, str) else None)
    else:
        mapping["available_at"] = None
    report.update({"built_at": observed, "catalog_observed_at": catalog_doc["observed_at"],
                   "level": level, "requested_industries": len(chosen), "failures": failures,
                   "failed_industries": len(failures), "direct_connection": direct,
                   "elapsed_seconds": round(time.monotonic() - started, 3)})
    if report["mapped_count"] == 0:
        _write_json(directory / "last_failure.json", report)
        raise RuntimeError("未取得任何行业映射；保留已有快照，见 industries/last_failure.json")
    output = directory / f"mapping_level{level}.parquet"
    if output.exists():
        previous = pd.read_parquet(output)
        if report["mapped_count"] < int(previous["status"].eq("mapped").sum()):
            _write_json(directory / "last_failure.json", report)
            raise RuntimeError("部分行业源失败，已保留覆盖更完整的快照")
    temp = output.with_suffix(".parquet.tmp")
    mapping.to_parquet(temp, index=False)
    temp.replace(output)
    _write_json(directory / f"report_level{level}.json", report)
    return report


def _official_file(name: str, directory: Path, timeout: float, refresh: bool) -> Path:
    """使用受验证 HTTPS；Windows 原生 TLS 可补全该站缺失的中间证书。"""
    if name not in {"StockClassifyUse_stock.xls", "SwClass.rar"}:
        raise ValueError("unsupported official file")
    target = directory / name
    stamp = target.with_suffix(target.suffix + ".json")
    if target.exists() and stamp.exists() and not refresh:
        return target
    temporary = target.with_suffix(target.suffix + ".download")
    url = SW_BASE + name
    if os.name == "nt":
        # Constant URL and single-quoted escaped absolute path; never disable TLS validation.
        quoted = str(temporary.resolve()).replace("'", "''")
        command = (f"$ErrorActionPreference='Stop'; Invoke-WebRequest -UseBasicParsing "
                   f"-Uri '{url}' -OutFile '{quoted}' -TimeoutSec {max(1, int(timeout))}")
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                       check=True, capture_output=True, timeout=timeout)
    else:
        response = requests.get(url, timeout=(timeout, timeout))
        response.raise_for_status()
        temporary.write_bytes(response.content)
    temporary.replace(target)
    _write_json(stamp, {"url": url, "observed_at": datetime.now(SHANGHAI).isoformat(timespec="seconds")})
    return target


def official_mapping(universe: pd.DataFrame, history: pd.DataFrame,
                     dictionary: pd.DataFrame, observed_at: str, level: int = 3) -> tuple[pd.DataFrame, dict]:
    """官方六位行业代码独立于证券指数代码，不混用两种编码。"""
    hist = history.rename(columns={"股票代码": "code", "计入日期": "effective_date",
                                   "行业代码": "source_industry_code", "更新日期": "source_updated_at"}).copy()
    hist["code"] = hist["code"].astype(str).str.zfill(6)
    hist["source_industry_code"] = hist["source_industry_code"].astype(str).str.zfill(6)
    for field in ("effective_date", "source_updated_at"):
        hist[field] = pd.to_datetime(hist[field], errors="coerce")
    day = pd.Timestamp(observed_at).tz_localize(None)
    hist = hist[(hist["effective_date"] <= day) & (hist["source_updated_at"] <= day)]
    hist = hist.sort_values(["code", "effective_date", "source_updated_at"])
    latest = hist.groupby("code").tail(1).copy()
    candidates = hist.merge(latest[["code", "effective_date", "source_updated_at"]],
                            on=["code", "effective_date", "source_updated_at"])
    conflicts = {code: group["source_industry_code"].unique().tolist()
                 for code, group in candidates.groupby("code")
                 if group["source_industry_code"].nunique() > 1}
    dictionary = dictionary.rename(columns={
        "行业代码": "source_industry_code", "一级行业名称": "level1_name",
        "二级行业名称": "level2_name", "三级行业名称": "level3_name"})
    dictionary["source_industry_code"] = dictionary["source_industry_code"].astype(str).str.zfill(6)
    if dictionary["source_industry_code"].duplicated().any():
        raise ValueError("官方行业字典有重复代码，不能静默择一")
    latest = latest.merge(dictionary, on="source_industry_code", how="left", validate="many_to_one")
    latest["industry_code"] = latest["source_industry_code"].str[:2 * level].str.pad(6, side="right", fillchar="0")
    latest["industry_name"] = latest[f"level{level}_name"]
    for depth in (1, 2, 3):
        latest[f"level{depth}_code"] = latest["source_industry_code"].str[:2 * depth].str.pad(6, side="right", fillchar="0")
    result = universe[["code"]].merge(latest, on="code", how="left", validate="one_to_one")
    result["status"] = result["industry_name"].notna().map({True: "mapped", False: "missing"})
    result.loc[result["code"].isin(conflicts), "status"] = "conflict"
    ambiguous = result["status"].eq("conflict")
    result.loc[ambiguous, ["industry_code", "industry_name"] +
               [f"level{i}_{field}" for i in (1, 2, 3) for field in ("code", "name")]] = None
    result["scheme"], result["level"] = "SW2021", level
    result["classification_method"] = "official_history_latest_record"
    result["source_url"] = SW_BASE + "StockClassifyUse_stock.xls"
    result["dictionary_url"] = SW_BASE + "SwClass.rar"
    result["observed_at"] = result["available_at"] = observed_at
    mapped = int(result["status"].eq("mapped").sum())
    return result, {"source": "SWS Research official history + official SW2021 dictionary",
                    "universe_count": len(result), "mapped_count": mapped,
                    "coverage_pct": round(100 * mapped / max(len(result), 1), 2),
                    "missing_codes": result.loc[result["status"].eq("missing"), "code"].tolist(),
                    "conflicts": conflicts, "history_rows": len(hist), "point_in_time_history": False,
                    "notes": ["历史文件更新日期不是公告发布时间；不能仅凭计入日期声称当时可知。",
                              "行业代码为申万官方六位分类代码，与 85xxxx.SI 行业指数代码不同。"]}


def build_sectors(data_dir: Path = DATA_DIR, level: int = 3, workers: int = 4,
                  timeout: float = 5, budget: float = 180, direct: bool = False,
                  refresh: bool = False, source: str = "official") -> dict:
    if source == "legulegu":
        return build_legulegu(data_dir, level, workers, timeout, budget, direct, refresh)
    if level not in (2, 3) or timeout <= 0 or budget <= 0:
        raise ValueError("level must be 2/3 and timeout/budget positive")
    from market_snapshot import load_universe
    started = time.monotonic()
    directory = Path(data_dir) / "industries"
    directory.mkdir(parents=True, exist_ok=True)
    def remaining():
        value = min(timeout, budget - (time.monotonic() - started))
        if value <= 0:
            raise TimeoutError("官方行业构建预算已用完")
        return value
    history_file = _official_file("StockClassifyUse_stock.xls", directory, remaining(), refresh)
    archive = _official_file("SwClass.rar", directory, remaining(), refresh)
    # Extract exactly one known member to stdout: no archive-controlled filesystem paths.
    extracted = subprocess.run(["tar", "-xOf", str(archive), "SwClassCode_2021.xls"],
                               capture_output=True, check=True, timeout=remaining())
    import io
    dictionary = pd.read_excel(io.BytesIO(extracted.stdout), dtype=str)
    history = pd.read_excel(history_file, dtype=str)
    observed = max(json.loads(path.with_suffix(path.suffix + ".json").read_text(encoding="utf-8"))["observed_at"]
                   for path in (history_file, archive))
    mapping, report = official_mapping(load_universe(data_dir=Path(data_dir)), history, dictionary, observed, level)
    report.update({"built_at": observed, "level": level, "failed_industries": 0, "failures": [],
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "source_url": SW_BASE + "StockClassifyUse_stock.xls",
                   "dictionary_url": SW_BASE + "SwClass.rar"})
    output = directory / f"mapping_level{level}.parquet"
    if output.exists():
        previous = pd.read_parquet(output)
        if mapping["status"].eq("mapped").sum() < previous["status"].eq("mapped").sum():
            _write_json(directory / "last_failure.json", report)
            raise RuntimeError("行业覆盖下降，已保留上一份映射；见 last_failure.json")
    temp = output.with_suffix(".parquet.tmp")
    mapping.to_parquet(temp, index=False)
    temp.replace(output)
    history.to_parquet(directory / "official_history.parquet", index=False)
    _write_json(directory / f"report_level{level}.json", report)
    acceptance = Path(data_dir) / "acceptance"
    acceptance.mkdir(parents=True, exist_ok=True)
    _write_json(acceptance / "sectors.json", report)
    return report


def load_sectors(as_of_date: str, codes: list[str] | None = None, *,
                 data_dir: Path = DATA_DIR, level: int = 3,
                 allow_current_snapshot: bool = False) -> pd.DataFrame:
    """默认只返回截至基准日已观察到的分类；历史查询缺证据时明确失败。"""
    as_of = pd.Timestamp(as_of_date)
    frame = pd.read_parquet(Path(data_dir) / "industries" / f"mapping_level{level}.parquet")
    if codes is not None:
        frame = frame[frame["code"].isin(codes)]
    available = pd.to_datetime(frame["available_at"], errors="coerce", utc=True)
    cutoff = pd.Timestamp(datetime.combine(as_of.date(), datetime.min.time(), tzinfo=SHANGHAI)
                          + timedelta(days=1))
    future = available >= cutoff
    if (frame["status"].eq("mapped") & available.isna()).any():
        raise ValueError("已映射行业缺少观察时间，不能用于时间切片")
    if future.any() and not allow_current_snapshot:
        raise ValueError("行业仅有当前快照，不能证明历史归属；如作描述性比较须显式 allow_current_snapshot=True")
    result = frame.copy()
    result["historical_snapshot_override"] = future if allow_current_snapshot else False
    return result.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--level", type=int, choices=[2, 3], default=3)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--budget", type=float, default=180)
    parser.add_argument("--direct", action="store_true", help="只在本次请求中不使用环境代理")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--source", choices=["official", "legulegu"], default="official")
    report = build_sectors(**vars(parser.parse_args()))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
