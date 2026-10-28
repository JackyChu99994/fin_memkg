# -*- coding: utf-8 -*-
"""修复版 update_logic.py —— 演示“新信息推翻旧逻辑”，保持文件名不变。

FIX #4  原代码在 except 里引用 `response`，请求异常时 response 未定义 → NameError 掩盖真实错误。
        现在异常只记日志并回退规则引擎，绝不引用可能未绑定的变量。
FIX #6  原 Cypher 写死 `MATCH (a:公司)-[r:利好事件]->(b:公司)`，
        旧逻辑是“利空”、或标签不是“公司”时会静默失败。现在按“主体+对象+相反方向”匹配，
        并同时处理显式 invalidates。
FIX #1  archive_ref 精确到单条新闻，旧逻辑被证伪时也能指回“是谁推翻的”。

用法：
    python update_logic.py                       # 使用内置示例新闻（真实日期）
    python update_logic.py --text "……" --date 2026-10-22
    python update_logic.py --no-llm              # 0 Token 规则引擎
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE if (HERE / "config.py").exists() else HERE.parent
sys.path.insert(0, str(ROOT))

import l4_archive as l4  # noqa: E402
from pipeline import run_news  # noqa: E402
from store import get_store  # noqa: E402

DEFAULT_NEWS = ("突发：由于监管审查未通过，宁德时代宣布暂停对上海时代宸远创业投资合伙企业"
                "的4亿元投资计划。")


def main() -> None:
    ap = argparse.ArgumentParser(description="演示：新信息推翻旧逻辑")
    ap.add_argument("--text", default=DEFAULT_NEWS)
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--code", default="300750")
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()

    store = get_store()
    before = {e["id"]: e for e in store.edges()}

    print(f"① 输入新闻（{args.date}）：{args.text[:50]}…")
    res = run_news(args.text, store, use_llm=not args.no_llm,
                   date=args.date, stock_code=args.code)

    print(f"② 抽取模式：{res.mode}（heuristic = 规则引擎，未调用大模型）")
    print(f"③ 本轮新增 {len(res.added)} 条边，证伪 {len(res.invalidated)} 条旧逻辑\n")

    for a in res.added:
        print(f"  ＋ {a['source']} -[{a['relation']}]-> {a['target']}")
        print(f"     理由：{a['reason']}")
        print(f"     证据：{a['archive_ref']}")

    if res.invalidated:
        print("\n  被推翻的旧逻辑：")
        for inv in res.invalidated:
            old = before.get(inv["event_id"], {})
            print(f"  － {old.get('source_name', inv['source'])} -[{old.get('type', '?')}]-> "
                  f"{old.get('target_name', inv['target'])}")
            print(f"     状态：发酵中 → 已被证伪，by {inv['by']}")
    else:
        print("\n  （没有旧逻辑被推翻：可能主体/对象不匹配，或旧边已经失效）")

    p = res.prediction or {}
    print(f"\n④ 当前结论：{p.get('direction')}（score={p.get('score')}，"
          f"证伪 {p.get('n_invalidated', 0)} 条）")
    for r in (p.get("reasons") or [])[:3]:
        print(f"   · {r['edge']} {r['source']}→{r['target']}：{r['text']}")
    print("\n提示：打开 app.py，中间图谱中被证伪的边会显示为灰色虚线。")


if __name__ == "__main__":
    main()
