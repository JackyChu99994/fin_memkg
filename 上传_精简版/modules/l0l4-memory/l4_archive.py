# -*- coding: utf-8 -*-
"""L4：原始新闻归档（append-only JSONL）+ 指针协议。

为什么要 JSONL 而不是“每条新闻一个 json 文件”：
  1. 追加写，永不改写历史，天然满足“审计/回溯”；
  2. 一行一条，`grep`、`pandas.read_json(lines=True)` 都能直接用；
  3. 文件小、答辩时可以直接打开给老师看。

指针格式：  memory/L4_archive/news.jsonl#EV-20261021-8f3ac1de
L2 的关系属性里只存这个字符串（archive_ref），点开即可还原原文。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from config import ARCHIVE_DIR, NEWS_JSONL, ROOT

NEWS_JSONL.parent.mkdir(parents=True, exist_ok=True)


def _sha8(text: str) -> str:
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:8]


def make_event_id(text: str, publish_date: str) -> str:
    """内容寻址：同一段新闻重复抓取不会产生两条记录。"""
    day = (publish_date or "")[:10].replace("-", "") or datetime.now().strftime("%Y%m%d")
    return f"EV-{day}-{_sha8(text)}"


def make_ref(event_id: str, path: Path = NEWS_JSONL) -> str:
    try:
        rel = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rel = path.as_posix()
    return f"{rel}#{event_id}"


def _iter_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # 坏行跳过，归档本身不能因为一行脏数据而不可用


def append_event(
    *,
    text: str,
    stock_code: str,
    stock_name: str,
    publish_date: str,
    source: str = "akshare",
    url: str = "",
    extra: Optional[dict] = None,
    path: Path = NEWS_JSONL,
) -> dict:
    """把一条原始新闻写进 L4，返回含 event_id / ref 的记录（幂等）。"""
    event_id = make_event_id(text, publish_date)
    for rec in _iter_jsonl(path):
        if rec.get("event_id") == event_id:
            rec.setdefault("ref", make_ref(event_id, path))
            return rec

    rec = {
        "event_id": event_id,
        "stock_code": stock_code,
        "stock_name": stock_name,
        "publish_date": publish_date,
        "source": source,
        "url": url,
        "text": text,
        "ingested_at": datetime.now().isoformat(timespec="seconds"),
        "extra": extra or {},
        "ref": make_ref(event_id, path),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def get_event(event_id: str, path: Path = NEWS_JSONL) -> Optional[dict]:
    for rec in _iter_jsonl(path):
        if rec.get("event_id") == event_id:
            return rec
    return None


def iter_events(stock_code: Optional[str] = None) -> list[dict]:
    recs = list(_iter_jsonl(NEWS_JSONL))
    if stock_code:
        recs = [r for r in recs if r.get("stock_code") == stock_code]
    return recs


def resolve(ref: str) -> Optional[dict]:
    """L2 关系 -> L4 原文。UI 里“点击证据”走的就是这个函数。"""
    if not ref or "#" not in ref:
        return None
    rel_path, event_id = ref.rsplit("#", 1)
    path = Path(rel_path)
    if not path.is_absolute():
        path = ROOT / rel_path
    return get_event(event_id, path)


def import_legacy_batch(path: str | Path) -> list[dict]:
    """吃下你现在 archive/news/*_batch.json 里的历史数据，不丢证据。"""
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for item in data.get("candidate_news", []):
        out.append(
            append_event(
                text=item.get("text", ""),
                stock_code=data.get("stock_code", ""),
                stock_name=data.get("stock_name", ""),
                publish_date=item.get("date", ""),
                source="akshare:legacy_batch",
                extra={"legacy_file": path.name, "crawl_time": data.get("crawl_time", "")},
            )
        )
    return out


def stats() -> dict:
    recs = iter_events()
    by_stock: dict[str, int] = {}
    for r in recs:
        by_stock[r.get("stock_name", "?")] = by_stock.get(r.get("stock_name", "?"), 0) + 1
    return {
        "total": len(recs),
        "bytes": NEWS_JSONL.stat().st_size if NEWS_JSONL.exists() else 0,
        "by_stock": by_stock,
        "file": str(NEWS_JSONL),
    }


if __name__ == "__main__":
    demo = append_event(
        text="宁德时代宣布暂停对上海时代宸远创业投资合伙企业的投资计划。",
        stock_code="300750",
        stock_name="宁德时代",
        publish_date="2026-10-21",
    )
    print(json.dumps(demo, ensure_ascii=False, indent=2))
    print("resolve ->", (resolve(demo["ref"]) or {}).get("text"))
    print("stats   ->", stats())
