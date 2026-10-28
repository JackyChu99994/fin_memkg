# -*- coding: utf-8 -*-
"""每日增量任务：抓新闻 → 更新 L2 → 归档 L4 → 新事件算 CAR → 生成日报。

这就是“定时任务”真正要跑的那一个脚本；任务计划程序只需要调用它。

    python daily_job.py --watchlist --limit 6 --llm
    python daily_job.py --codes 300750 --no-kline --limit 3
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

import l3_event_study as l3
from config import has_llm
from fetch_real import (load_state, norm_codes, run_codes, save_state,
                        setup_logging, watchlist_codes)

REPORT_DIR = Path(__file__).resolve().parent / "reports"


def build_report(stats: list[dict], studies: list[dict], day: str) -> str:
    lines = [f"# 每日情报日报 · {day}", "",
             f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}", "",
             "## 一、抓取与入库概览", "",
             "| 代码 | 抓取 | 已归档跳过 | L0 过滤 | 新增边 | 强化 | 证伪旧逻辑 |",
             "|---|---|---|---|---|---|---|"]
    for s in stats:
        lines.append(f"| {s['code']} | {s['fetched']} | {s['skipped']} | {s['filtered']} | "
                     f"{s['added']} | {s.get('reinforced', 0)} | {s['invalidated']} |")

    events = [e for s in stats for e in s["events"]]
    lines += ["", "## 二、新增投资逻辑", ""]
    if events:
        lines += ["| 日期 | 主体 | 关系 | 对象 | 理由 | 证据 |", "|---|---|---|---|---|---|"]
        for e in events:
            lines.append(f"| {e['date']} | {e['source']} | {e['relation']} | {e['target']} | "
                         f"{e['reason'][:30]} | `{e['archive_ref'].split('#')[-1]}` |")
    else:
        lines.append("今日无新增逻辑（全部被 L0 过滤或已归档）。")

    inv = [e for s in stats for e in s["invalidated_events"]]
    lines += ["", "## 三、被推翻的旧逻辑", ""]
    if inv:
        lines += ["| 日期 | 逻辑 | 被谁推翻 |", "|---|---|---|"]
        for e in inv:
            lines.append(f"| {e['date']} | {e['source']} → {e['target']} | `{e['by']}` |")
    else:
        lines.append("今日无逻辑反转。")

    lines += ["", "## 四、事件窗口 CAR（T+5 未走完的标注为“进行中”）", ""]
    if studies:
        lines += ["| 代码 | 事件日 | CAR | Beta | 交易日 | 数据源 |", "|---|---|---|---|---|---|"]
        for st in studies:
            flag = "" if st.get("complete") else "（进行中）"
            lines.append(f"| {st['code']} | {st['event_date']} | {st['car_pct']:+.2f}% | "
                         f"{st['beta']:.2f} | {st['n_days']} | {st['source']}{flag} |")
    else:
        lines.append("今日无新事件需要复盘。")

    lines += ["", "> 本报告由 daily_job.py 自动生成，所有结论均可回溯到 memory/L4_archive/news.jsonl。"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fin-MemKG 每日增量任务")
    ap.add_argument("--codes", default="")
    ap.add_argument("--watchlist", action="store_true")
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--no-kline", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.8)
    args = ap.parse_args()

    setup_logging("daily")
    codes = norm_codes(args.codes) or (watchlist_codes() if args.watchlist else [])
    if not codes:
        ap.error("请用 --codes 或 --watchlist 指定标的")

    from store import get_store

    store = get_store()
    use_llm = (args.llm or has_llm()) and not args.no_llm

    stats = run_codes(codes, store, limit=args.limit, use_llm=use_llm,
                      sleep=args.sleep, with_kline=not args.no_kline)

    # 只对今天之前（含）的事件算 CAR，避免窗口未走完带来的误导
    studies = []
    today = date.today().isoformat()
    for s in stats:
        for e in s["events"][:5]:
            if e["relation"] not in ("利好事件", "利空事件") or e["date"] > today:
                continue
            try:
                studies.append(l3.event_study(e["code"], e["date"]))
            except Exception as exc:
                print(f"CAR 计算失败 {e['code']} {e['date']}: {exc}")

    REPORT_DIR.mkdir(exist_ok=True)
    day = date.today().isoformat()
    path = REPORT_DIR / f"daily_{day}.md"
    path.write_text(build_report(stats, studies, day), encoding="utf-8")

    state = load_state()
    for s in stats:
        state[s["code"]] = {"last_run": datetime.now().isoformat(timespec="seconds"),
                            "added": s["added"]}
    save_state(state)

    total = sum(s["added"] for s in stats)
    print(f"\n✅ 今日新增 {total} 条逻辑，日报已写入 {path}")


if __name__ == "__main__":
    main()
