# -*- coding: utf-8 -*-
"""真实数据接入：AkShare → L1 路由 → L2 抽取/写回 → L4 归档（+ 行情缓存）。

用法：
    python fetch_real.py --codes 300750,002466 --limit 8 --llm
    python fetch_real.py --watchlist --limit 5 --no-llm
    python fetch_real.py --codes 300750 --dry-run          # 只看会抓到什么，不写库

设计要点：
  * 事件日期一律取新闻的【发布时间】，不是抓取时间（L0-1 时间隔离，避免前视偏差）；
  * L4 用内容哈希去重，同一条新闻被多个股票代码抓到也只归档一次；
  * 行情同时落一份 CSV 到 data/prices/，L3 事件研究优先读它，断网也能算 CAR。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import l4_archive as l4
from config import PRICE_CACHE, ROOT, has_llm
from l1_router import load_index, route
from pipeline import run_news

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
STATE_FILE = ROOT / "data" / "fetch_state.json"

log = logging.getLogger("fetch_real")


def setup_logging(tag: str = "fetch") -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / f"{tag}_{datetime.now():%Y%m%d}.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )


# --------------------------------------------------------------------------- #
# 抓取
# --------------------------------------------------------------------------- #
def watchlist_codes() -> list[str]:
    idx = load_index()
    return [s["code"] for c in idx["clusters"] for s in c["stocks"]]


def norm_codes(raw: str) -> list[str]:
    """把 300750,2466 这种输入统一成 6 位代码（PowerShell 会把 002466 当数字截成 2466）。"""
    return [c.strip().zfill(6) for c in (raw or "").split(",") if c.strip()]


def fetch_news(code: str, limit: int = 10, as_of: str | None = None) -> list[dict]:
    """抓个股新闻。返回 [{code,text,title,date,time,source,url}]，已按时间倒序过滤。"""
    import akshare as ak

    df = ak.stock_news_em(symbol=code)
    items: list[dict] = []
    for _, row in df.iterrows():
        text = str(row.get("新闻内容") or "").strip()
        title = str(row.get("新闻标题") or "").strip()
        pub = str(row.get("发布时间") or "").strip()
        if len(text) < 15:
            continue
        date = pub[:10]
        if as_of and date > as_of:
            continue
        items.append({
            "code": code, "text": text, "title": title, "date": date, "time": pub,
            "source": str(row.get("文章来源") or ""), "url": str(row.get("新闻链接") or ""),
        })
        if len(items) >= limit:
            break
    return items


def fetch_kline(code: str, days: int = 400) -> int:
    """拉日线并落 CSV（date,close），供 L3 事件研究离线使用。返回写入行数。"""
    import akshare as ak

    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
    df = df.rename(columns={"日期": "date", "收盘": "close"})[["date", "close"]]
    df["date"] = df["date"].astype(str)
    df["close"] = df["close"].astype(float)
    df = df.sort_values("date")
    path = PRICE_CACHE / f"{code}.csv"
    df.to_csv(path, index=False, encoding="utf-8")
    return len(df)


# --------------------------------------------------------------------------- #
# 入库
# --------------------------------------------------------------------------- #
def ingest_items(code: str, items: list[dict], store, *, use_llm: bool, sleep: float = 0.8) -> dict:
    """逐条走完整的 L1→L0→L2→L4 链路。返回统计。"""
    stat = {"code": code, "fetched": len(items), "skipped": 0, "filtered": 0,
            "added": 0, "invalidated": 0, "reinforced": 0, "rejected": 0,
            "events": [], "invalidated_events": []}
    for it in items:
        # 已归档过的直接跳过（内容寻址）
        if l4.get_event(l4.make_event_id(it["text"], it["date"])):
            stat["skipped"] += 1
            continue
        try:
            res = run_news(it["text"], store, use_llm=use_llm, date=it["date"], stock_code=code)
        except Exception as exc:
            log.warning("[%s] 处理失败：%s | %s", code, exc, it["title"][:40])
            continue

        if not res.added and not res.reinforced:
            stat["filtered"] += 1
            log.info("[%s] L0 过滤：%s", code, it["title"][:40])
        else:
            stat["added"] += len(res.added)
            stat["invalidated"] += len(res.invalidated)
            stat["reinforced"] += len(res.reinforced)
            stat["rejected"] += len(res.rejected)
            for a in res.added:
                stat["events"].append({"code": code, "date": it["date"], "source": a["source"],
                                       "relation": a["relation"], "target": a["target"],
                                       "reason": a["reason"], "event_id": a["event_id"],
                                       "archive_ref": a["archive_ref"]})
            for inv in res.invalidated:
                stat["invalidated_events"].append({"code": code, "date": it["date"],
                                                   "source": inv["source"], "target": inv["target"],
                                                   "by": inv["by"]})
            log.info("[%s] +%d 边 / %d 强化 / -%d 旧逻辑 | %s", code, len(res.added),
                     len(res.reinforced), len(res.invalidated), it["title"][:40])
        if sleep:
            time.sleep(sleep)
    return stat


def run_codes(codes: list[str], store, *, limit: int = 8, use_llm: bool = False,
              sleep: float = 0.8, with_kline: bool = True, as_of: str | None = None) -> list[dict]:
    stats = []
    for code in codes:
        try:
            items = fetch_news(code, limit=limit, as_of=as_of)
        except Exception as exc:
            log.error("[%s] 新闻抓取失败：%s", code, exc)
            continue
        if with_kline:
            try:
                n = fetch_kline(code)
                log.info("[%s] 行情缓存 %d 行", code, n)
            except Exception as exc:
                log.warning("[%s] 行情抓取失败（L3 会退回缓存/模拟）：%s", code, exc)
        stats.append(ingest_items(code, items, store, use_llm=use_llm, sleep=sleep))
    return stats


# --------------------------------------------------------------------------- #
# 状态 & CLI
# --------------------------------------------------------------------------- #
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="AkShare 真实数据接入")
    ap.add_argument("--codes", default="", help="逗号分隔的股票代码，如 300750,002466")
    ap.add_argument("--watchlist", action="store_true", help="抓取 L1 词典里的全部标的")
    ap.add_argument("--limit", type=int, default=8, help="每只股票最多处理多少条新闻")
    ap.add_argument("--llm", action="store_true", help="调用 DeepSeek 抽取（默认规则引擎）")
    ap.add_argument("--no-llm", action="store_true", help="强制用规则引擎")
    ap.add_argument("--sleep", type=float, default=0.8, help="每条新闻之间的间隔秒数")
    ap.add_argument("--no-kline", action="store_true", help="不抓行情")
    ap.add_argument("--as-of", default="", help="只用该日期之前的新闻（YYYY-MM-DD）")
    ap.add_argument("--dry-run", action="store_true", help="只抓取和路由，不写库")
    args = ap.parse_args()

    setup_logging("fetch" if not args.dry_run else "dryrun")
    codes = norm_codes(args.codes) or (watchlist_codes() if args.watchlist else [])

    if not codes:
        ap.error("请用 --codes 或 --watchlist 指定标的")

    if args.dry_run:
        for code in codes:
            items = fetch_news(code, limit=args.limit, as_of=args.as_of or None)
            print(f"\n=== {code} · {len(items)} 条 ===")
            for it in items:
                d = route(it["text"])
                hit = "、".join(s.name for s in d.stocks) or "未命中"
                print(f"[{it['date']}] {it['title'][:36]:<36} → L1: {hit}")
        return

    from store import get_store

    store = get_store()
    use_llm = (args.llm or has_llm()) and not args.no_llm
    stats = run_codes(codes, store, limit=args.limit, use_llm=use_llm,
                      sleep=args.sleep, with_kline=not args.no_kline,
                      as_of=args.as_of or None)

    total = {k: sum(s[k] for s in stats)
             for k in ("fetched", "skipped", "filtered", "added", "invalidated", "reinforced")}
    print("\n===== 汇总 =====")
    for s in stats:
        print(f"{s['code']}: 抓取{s['fetched']} 跳过{s['skipped']} 过滤{s['filtered']} "
              f"+{s['added']}边 强化{s['reinforced']} -{s['invalidated']}旧逻辑")
    print(f"合计：+{total['added']} 条边，强化 {total['reinforced']} 条，"
          f"{total['invalidated']} 条逻辑被证伪，{total['filtered']} 条被 L0 过滤")

    state = load_state()
    for s in stats:
        if s["fetched"]:
            state[s["code"]] = {"last_run": datetime.now().isoformat(timespec="seconds"),
                                "added": total["added"]}
    save_state(state)


if __name__ == "__main__":
    main()
