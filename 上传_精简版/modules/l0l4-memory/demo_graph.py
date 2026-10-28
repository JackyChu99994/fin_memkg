# -*- coding: utf-8 -*-
"""修复版 demo_graph.py —— 保持文件名不变，接力队友的调用方式不用改。

相对你原来那份，改动对应我列过的 7 个问题：

  FIX #1  archive_path 指向“整个批次 JSON” → 现在每条边带 archive_ref（精确到一条新闻）
  FIX #2  MERGE (a)-[r:利好事件]->(b) 无 event_id，第二条利好会覆盖第一条 → 边以 event_id 唯一
  FIX #3  兜底用 prompt.replace(...) 重渲染，字符串替换易错位 → 结构化 build_prompt
  FIX #5  os.makedirs("archive/news") 依赖 cwd → 所有路径基于 __file__
  FIX #6  Cypher 写死 (a:公司)-[r:利好事件]->(b:公司) → 标签/关系来自白名单校验
  FIX #7  密钥硬编码 → 读 .env（config.py）

FIX #4 在 update_logic.py 里（except 分支引用未定义的 response）。

用法：
    python demo_graph.py --code 300750 --limit 5 --llm
    python demo_graph.py --code 300750 --limit 5          # 不调模型，规则引擎
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE if (HERE / "config.py").exists() else HERE.parent
sys.path.insert(0, str(ROOT))

import l4_archive as l4  # noqa: E402
from config import NEWS_JSONL, has_llm  # noqa: E402
from fetch_real import fetch_kline, fetch_news, ingest_items  # noqa: E402
from store import get_store  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="抓取真实新闻 → L4 归档 → L2 抽取 → Neo4j")
    ap.add_argument("--code", default="300750")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--llm", action="store_true", help="调用 DeepSeek（默认规则引擎）")
    ap.add_argument("--no-kline", action="store_true")
    args = ap.parse_args()

    print(f"① 抓取 {args.code} 的最新新闻（最多 {args.limit} 条）…")
    items = fetch_news(args.code, limit=args.limit)
    if not items:
        print("⚠️ 没抓到新闻，检查代码或网络。")
        return
    for it in items:
        print(f"   - [{it['date']}] {it['title'][:40]}")

    if not args.no_kline:
        try:
            n = fetch_kline(args.code)
            print(f"② 行情已缓存 {n} 行 → data/prices/{args.code}.csv（L3 用）")
        except Exception as exc:
            print(f"② 行情抓取失败（不影响入库）：{exc}")

    store = get_store()
    print(f"③ 写入 L2（{store.mode}）+ L4（{NEWS_JSONL.name}）…")
    stat = ingest_items(args.code, items, store, use_llm=args.llm or has_llm(), sleep=0.6)

    print("\n===== 结果 =====")
    print(f"抓取 {stat['fetched']} · 已归档跳过 {stat['skipped']} · L0 过滤 {stat['filtered']} · "
          f"新增边 {stat['added']} · 强化 {stat['reinforced']} · 证伪旧逻辑 {stat['invalidated']}")
    for e in stat["events"]:
        print(f"  + ({e['source']})-[{e['relation']}]->({e['target']})  证据：{e['archive_ref']}")
    for e in stat["invalidated_events"]:
        print(f"  ✗ 旧逻辑被推翻：{e['source']} → {e['target']}（by {e['by']}）")

    print(f"\nL4 归档：{NEWS_JSONL}")
    print("下一步：streamlit run app.py 看图谱，或 python update_logic.py 演示反转。")


if __name__ == "__main__":
    main()
