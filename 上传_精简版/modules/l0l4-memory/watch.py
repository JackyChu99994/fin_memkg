# -*- coding: utf-8 -*-
"""近实时监听（near-real-time watcher）：轮询新闻 → 只处理新增 → 自动写 L2/L4。

它和你按按钮的区别只有一个：**触发者从"人"变成"定时器"**。

    python watch.py --codes 300750 --interval 60          # 每 60 秒看一次
    python watch.py --watchlist --interval 120 --llm
    python watch.py --codes 300750 --once                 # 只跑一轮，用来验证

三个关键机制（缺一个就会重复入图或漏新闻）：
    1. 水位线 watermark：每只票记录"最后处理到的发布时间"，只处理更新的；
    2. 幂等 idempotency：L4 内容哈希兜底，重复抓到同一条不会重复写；
    3. 增量：单条新闻走 run_news，处理完立刻落盘，进程挂了也不丢。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import l4_archive as l4
from config import ROOT, has_llm
from fetch_real import fetch_news, norm_codes, watchlist_codes
from pipeline import run_news
from store import get_store

STATE_FILE = ROOT / "data" / "watch_state.json"
STATUS_FILE = ROOT / "data" / "watch_status.json"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def one_cycle(codes: list[str], store, state: dict, *, use_llm: bool, limit: int,
              pause: float = 0.8) -> dict:
    stat = {"at": datetime.now().isoformat(timespec="seconds"),
            "new": 0, "added": 0, "reinforced": 0, "invalidated": 0, "errors": 0, "detail": []}

    for code in codes:
        try:
            items = fetch_news(code, limit=limit)
        except Exception as exc:
            stat["errors"] += 1
            stat["detail"].append(f"{code} 抓取失败：{exc}")
            print(f"  ! {code} 抓取失败：{exc}")
            continue

        last_seen = state.get(code, "")
        fresh = [it for it in items if it["time"] > last_seen]
        if fresh:
            print(f"  {code}: 新增 {len(fresh)} 条（水位线 {last_seen or '无'}）")

        for it in sorted(fresh, key=lambda x: x["time"]):
            # 幂等：即便水位线丢了，内容哈希也能挡住重复
            if l4.get_event(l4.make_event_id(it["text"], it["date"])):
                continue
            try:
                res = run_news(it["text"], store, use_llm=use_llm,
                               date=it["date"], stock_code=code)
            except Exception as exc:
                stat["errors"] += 1
                print(f"  ! 处理失败：{exc}")
                continue

            stat["new"] += 1
            stat["added"] += len(res.added)
            stat["reinforced"] += len(res.reinforced)
            stat["invalidated"] += len(res.invalidated)
            flag = "＋" if res.added else ("＝" if res.reinforced else "×")
            title = it["title"][:32]
            print(f"    {flag} {title}  (新增{len(res.added)} 强化{len(res.reinforced)} "
                  f"证伪{len(res.invalidated)})")
            stat["detail"].append({"code": code, "title": title, "decision": flag,
                                   "added": len(res.added), "invalidated": len(res.invalidated)})
            time.sleep(pause)

        if items:
            state[code] = max(it["time"] for it in items)
            save_json(STATE_FILE, state)   # 每条处理完立刻落盘
    return stat


def main() -> None:
    ap = argparse.ArgumentParser(description="近实时新闻监听")
    ap.add_argument("--codes", default="300750")
    ap.add_argument("--watchlist", action="store_true")
    ap.add_argument("--interval", type=int, default=60, help="轮询间隔秒数（>=30）")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--once", action="store_true", help="只跑一轮")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()

    codes = norm_codes(args.codes) or (watchlist_codes() if args.watchlist else [])
    if not codes:
        ap.error("请用 --codes 或 --watchlist 指定标的")

    interval = max(30, args.interval)
    use_llm = (args.llm or has_llm()) and not args.no_llm
    store = get_store()
    state = load_json(STATE_FILE, {})

    print("=" * 62)
    print(f"Fin-MemKG watcher  标的 {len(codes)} 只  间隔 {interval}s  "
          f"抽取 {'LLM' if use_llm else '规则引擎'}")
    print(f"存储 {store.mode} · L4 {l4.NEWS_JSONL.name} · Ctrl+C 退出")
    print("=" * 62)

    try:
        while True:
            t0 = time.time()
            stat = one_cycle(codes, store, state, use_llm=use_llm, limit=args.limit)
            save_json(STATUS_FILE, stat)
            cost = time.time() - t0
            print(f"[{datetime.now():%H:%M:%S}] 本轮 新增{stat['new']} 边+{stat['added']} "
                  f"强化{stat['reinforced']} 证伪{stat['invalidated']} "
                  f"错误{stat['errors']} 耗时{cost:.1f}s")
            if args.once:
                break
            time.sleep(max(1, interval - cost))
    except KeyboardInterrupt:
        print("\n已停止。水位线已保存，下次从断点继续。")
        sys.exit(0)


if __name__ == "__main__":
    main()
