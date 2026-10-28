# -*- coding: utf-8 -*-
"""运动器官：GenericAgent 风格的最小行动闭环。

    感知(perceive) → 路由(route) → 回忆(recall) → 推演(reason)
      → 行动(act: 写回 L2/L4) → 复盘(reflect: L3 事件研究) → 决策卡(decide)

和“只会抽三元组的 demo_graph.py”的区别就在最后两步：
系统不只记录世界，还会给出一个可被市场检验的动作，并留下证据链。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime

import l3_event_study as l3
from pipeline import RunResult, predict, run_news


@dataclass
class Step:
    name: str
    tool: str
    detail: str
    ms: int = 0
    ok: bool = True


@dataclass
class AgentResult:
    run: RunResult
    study: dict = field(default_factory=dict)
    study_error: str = ""
    decision: dict = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    elapsed_ms: int = 0


DECISION_TABLE = {
    ("偏多", True): ("增持 / 维持", "L2 逻辑偏多，且事件窗口超额收益为正，市场与逻辑同向。"),
    ("偏多", False): ("观察", "L2 逻辑偏多，但超额收益为负：可能利好出尽或市场不认可，先不动。"),
    ("偏空", False): ("减持 / 规避", "L2 逻辑偏空，且超额收益为负，风险正在被定价。"),
    ("偏空", True): ("观察", "L2 逻辑偏空，但超额收益仍为正：利空可能尚未反映，警惕补跌。"),
    ("中性", True): ("观察", "多空逻辑相互抵消，等待新的方向性证据。"),
    ("中性", False): ("观察", "多空逻辑相互抵消，等待新的方向性证据。"),
}


class MemoryAgent:
    """把 pipeline / L3 / 存储层串成一个可解释的 action loop。"""

    def __init__(self, store, *, use_llm: bool = True):
        self.store = store
        self.use_llm = use_llm

    # ---- 工具清单（GenericAgent 的“可调用能力”，UI 里直接展示） ----
    @staticmethod
    def tool_specs() -> list[dict]:
        return [
            {"name": "l1.route", "kind": "感知", "desc": "新闻 → 概念簇 → 候选标的（0 Token）"},
            {"name": "l2.recall", "kind": "记忆", "desc": "按标的召回活跃投资逻辑与证据指针"},
            {"name": "l2.extract", "kind": "推演", "desc": "L0 约束下抽取事件三元组（LLM）"},
            {"name": "l0.validate", "kind": "校验", "desc": "本体白名单校验，拦截越界三元组"},
            {"name": "l2.commit", "kind": "行动", "desc": "写 L2 图谱 + L4 归档，旧逻辑置为已证伪"},
            {"name": "l3.event_study", "kind": "计算", "desc": "市场模型 CAR，检验结论是否被市场认可"},
            {"name": "l2.predict", "kind": "决策", "desc": "多空打分 + 证据链 → 方向与置信度"},
        ]

    def run(self, news: str, *, date: str | None = None, stock_code: str = "",
            hops: int = 1, with_study: bool = True) -> AgentResult:
        t_start = time.perf_counter()
        date = (date or datetime.now().strftime("%Y-%m-%d"))[:10]
        steps: list[Step] = []

        t = time.perf_counter()
        run = run_news(news, self.store, use_llm=self.use_llm, date=date,
                       stock_code=stock_code, hops=hops)
        steps.append(Step("感知 → 路由 → 抽取 → 写回", "pipeline.run_news",
                          f"{len(run.added)} 条新边 / {len(run.invalidated)} 条证伪",
                          int((time.perf_counter() - t) * 1000)))

        center = stock_code or (run.routing.stocks[0].code if run.routing.stocks else "")
        study, err = {}, ""
        if with_study and center:
            t = time.perf_counter()
            try:
                study = l3.event_study(center, date)
                steps.append(Step("复盘 / L3 事件研究", "l3.event_study",
                                  f"CAR {study['car_pct']:+.2f}%（{study['source']}，{study['n_days']} 天）",
                                  int((time.perf_counter() - t) * 1000)))
            except Exception as exc:
                err = str(exc)
                steps.append(Step("复盘 / L3 事件研究", "l3.event_study", f"失败：{exc}", 0, ok=False))

        pred = run.prediction or predict(self.store, code=center)
        key = (pred.get("direction", "中性"), (study.get("car_pct", 0) or 0) > 0)
        action, why = DECISION_TABLE.get(key, ("观察", "证据不足，继续跟踪。"))

        decision = {
            "action": action,
            "why": why,
            "direction": pred.get("direction"),
            "confidence": pred.get("confidence"),
            "score": pred.get("score"),
            "car_pct": study.get("car_pct"),
            "car_verdict": l3.verdict(study, pred.get("direction", "中性")) if study else "",
            "reasons": pred.get("reasons", []),
            "counts": {k: pred.get(k) for k in ("n_active_bull", "n_active_bear", "n_invalidated")},
        }
        return AgentResult(run=run, study=study, study_error=err, decision=decision,
                           steps=steps, elapsed_ms=int((time.perf_counter() - t_start) * 1000))


if __name__ == "__main__":
    import json

    from demo_data import seed
    from store import LocalStore

    st = LocalStore()
    seed(st)
    agent = MemoryAgent(st, use_llm=False)
    res = agent.run("突发：由于监管审查未通过，宁德时代宣布暂停对上海时代宸远创业投资合伙企业的4亿元投资计划。",
                    date="2026-10-22", stock_code="300750")
    print(json.dumps(res.decision, ensure_ascii=False, indent=2))
    for s in res.steps:
        print(f"[{s.ok}] {s.tool} · {s.detail} ({s.ms} ms)")
