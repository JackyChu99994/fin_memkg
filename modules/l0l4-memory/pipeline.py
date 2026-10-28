# -*- coding: utf-8 -*-
"""L2 流水线：路由 -> 抽取 -> 校验 -> 与旧逻辑对账 -> 写图 -> 给结论。

这是“记忆库”变成“会思考的记忆库”的地方：
新事件不是简单 append，而是先在已有 L2 图谱里找**相反方向的活跃逻辑**，
把它标成“已被证伪”，再挂上新边——这就是老师要的“动态知识更新”。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import l4_archive as l4
from config import (DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
                    ENTITY_TYPES, POLARITY, REL_TYPES, STATUS_ACTIVE,
                    STATUS_INVALID)
from l0_rules import EXTRACT_SYSTEM, OUTPUT_CONTRACT, render_l0_block
from l1_router import RoutingDecision, route


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #
@dataclass
class RunResult:
    news: str
    date: str
    mode: str                      # llm | heuristic
    routing: RoutingDecision
    events: list[dict] = field(default_factory=list)
    added: list[dict] = field(default_factory=list)
    invalidated: list[dict] = field(default_factory=list)
    reinforced: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    prediction: dict = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)
    llm_raw: str = ""
    prompt: str = ""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _trace(trace: list, step: str, detail: str, **extra) -> None:
    trace.append({"step": step, "detail": detail, "at": _now(), **extra})


# --------------------------------------------------------------------------- #
# 检索：把“与本次路由相关的已有逻辑”压缩成几行
# --------------------------------------------------------------------------- #
def theses_block(store, decision: RoutingDecision, limit: int = 14) -> str:
    if not decision.stocks:
        return ""
    names = {s.name for s in decision.stocks}
    rows = []
    for e in store.edges():
        if e["status"] != STATUS_ACTIVE:
            continue
        if e["source_name"] in names or e["target_name"] in names:
            rows.append(f"- {e['source_name']} -[{e['type']}]-> {e['target_name']}"
                        f"（{e['props'].get('date','')}，置信度 {e['props'].get('confidence','?')}，id={e['id']}）")
    rows = rows[:limit]
    if not rows:
        return "【已有逻辑】无（本次为首条事件）"
    return "【已有活跃逻辑（若被本条新闻推翻，请置为已被证伪）】\n" + "\n".join(rows)


def build_prompt(news: str, decision: RoutingDecision, theses: str, date: str) -> str:
    return f"""{render_l0_block()}

{decision.prompt_block}

{theses}

【新闻】
{news}

【事件日期】{date}
请抽取“会改变投资逻辑”的事件。若新闻与股价/产业链/财务/监管/供需无关，输出 {{"events": []}}。
同一主体对同一对象若方向相反，请把旧逻辑写进 invalidates。
{OUTPUT_CONTRACT}"""


# --------------------------------------------------------------------------- #
# LLM 调用与解析
# --------------------------------------------------------------------------- #
def _chat(client, model: str, prompt: str, *, thinking: bool | None = None,
          max_tokens: int = 1200) -> str:
    kwargs = {
        "model": model,
        "messages": [{"role": "system", "content": EXTRACT_SYSTEM},
                     {"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if thinking is False:
        # DeepSeek V4 起默认开启思考模式；结构化抽取不需要推理链，显式关掉更便宜也更快
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def call_llm(prompt: str, timeout: float = 60.0) -> str:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY（可在 .env 中设置）")
    from openai import OpenAI

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=timeout)
    try:
        return _chat(client, DEEPSEEK_MODEL, prompt)
    except Exception as exc:
        msg = str(exc).lower()
        # 配置的旧模型名被下线时（如 deepseek-chat 退役），退回 flash 的非思考模式
        if DEEPSEEK_MODEL == "deepseek-flash" or not any(
                k in msg for k in ("model", "not found", "400", "404", "invalid")):
            raise
        return _chat(client, "deepseek-flash", prompt, thinking=False)


def parse_events(raw: str) -> list[dict]:
    text = (raw or "").strip().replace("```json", "").replace("```", "").strip()
    if not text:
        return []
    m = re.search(r"\{.*\}|\[.*\]", text, re.S)
    if not m:
        raise ValueError("输出中找不到 JSON")
    data = json.loads(m.group(0))
    if isinstance(data, dict):
        data = data.get("events", [])
    return data if isinstance(data, list) else []


def validate_events(events: list[dict], date: str) -> tuple[list[dict], list[dict]]:
    ok, bad = [], []
    for ev in events:
        reason = ""
        if not ev.get("source") or not ev.get("target"):
            reason = "source/target 为空"
        elif ev.get("relation") not in REL_TYPES:
            reason = f"关系 {ev.get('relation')} 不在白名单"
        elif (ev.get("target_type") or "公司") not in ENTITY_TYPES:
            reason = f"实体类型 {ev.get('target_type')} 不在白名单"
        elif not ev.get("reason"):
            reason = "缺少 reason"
        if reason:
            bad.append({"event": ev, "reason": reason})
            continue
        ev = dict(ev)
        ev["source_type"] = ev.get("source_type") or "公司"
        ev["target_type"] = ev.get("target_type") or "公司"
        ev["status"] = ev.get("status") if ev.get("status") in (STATUS_ACTIVE, STATUS_INVALID, "已兑现") else STATUS_ACTIVE
        ev["date"] = (ev.get("date") or date)[:10]
        try:
            ev["confidence"] = max(0.0, min(1.0, float(ev.get("confidence", 0.7))))
        except (TypeError, ValueError):
            ev["confidence"] = 0.7
        ev["reason"] = str(ev["reason"])[:80]
        ok.append(ev)
    return ok, bad


# --------------------------------------------------------------------------- #
# 0-Token 规则引擎：答辩现场断网/没额度也能跑通
# --------------------------------------------------------------------------- #
BULL_KW = ("签约", "签订", "中标", "增长", "上涨", "涨停", "扩产", "合作", "突破",
           "超预期", "获批", "涨价", "提价", "放量", "回暖", "回购", "增持")
BEAR_KW = ("暂停", "终止", "未通过", "下滑", "下跌", "跌停", "减持", "亏损", "调查",
           "处罚", "转给", "下降", "承压", "收紧", "风险", "延期", "解约", "退单")
PRICE_UP = ("涨价", "上涨", "涨停", "收紧", "短缺", "反弹", "新高", "提价", "缺货")
UPSTREAM_WORDS = ("锂矿", "碳酸锂", "锂盐", "锂精矿", "盐湖提锂", "上游")


def heuristic_extract(text: str, decision: RoutingDecision, date: str) -> list[dict]:
    """不调用模型的可解释规则：关键词极性 + 产业链上下游传导。"""
    if not decision.stocks:
        return []
    bull = sum(text.count(k) for k in BULL_KW)
    bear = sum(text.count(k) for k in BEAR_KW)

    # 规则 1：上游资源涨价 -> 上游利好 / 下游成本承压（两跳传导）
    if any(k in text for k in PRICE_UP) and any(w in text for w in UPSTREAM_WORDS):
        up = [s for s in decision.stocks if "上游" in s.chain]
        down = [s for s in decision.stocks if ("电池" in s.chain or "材料" in s.chain)]
        out = []
        for s in up:
            out.append({"source": s.name, "source_code": s.code, "relation": "利好事件",
                        "target": "碳酸锂" if "碳酸锂" in text else "锂矿", "target_type": "产品",
                        "status": STATUS_ACTIVE, "confidence": 0.78, "date": date,
                        "reason": "上游资源涨价，量价弹性直接受益"})
        for s in down:
            out.append({"source": s.name, "source_code": s.code, "relation": "利空事件",
                        "target": "碳酸锂", "target_type": "产品",
                        "status": STATUS_ACTIVE, "confidence": 0.70, "date": date,
                        "reason": "原材料涨价压缩毛利率"})
        return out

    if bull == 0 and bear == 0:
        return []

    rel = "利空事件" if bear > bull else "利好事件"
    named = [s for s in decision.stocks if s.name in text]
    subject = named[0] if named else decision.stocks[0]

    # 目标优先级：文本中出现的其他标的 > 已有逻辑里的对手方 > 概念行业
    target, ttype, tcode = "", "行业", ""
    for s in decision.stocks:
        if s.code != subject.code and s.name in text:
            target, ttype, tcode = s.name, "公司", s.code
            break
    if not target:
        concept_name = decision.clusters[0]["name"] if decision.clusters else "相关行业"
        target, ttype = concept_name, "行业"

    return [{"source": subject.name, "source_code": subject.code, "relation": rel,
             "target": target, "target_type": ttype, "target_code": tcode,
             "status": STATUS_ACTIVE, "confidence": 0.55 if bear or bull else 0.4,
             "date": date, "reason": text.strip()[:60]}]


def heuristic_extract_with_theses(text, decision, date, store) -> list[dict]:
    """在规则引擎上补一步：如果新闻点名了某条已有逻辑的对手方，就指向它，便于演示“反转”。"""
    events = heuristic_extract(text, decision, date)
    if not events:
        return events
    names = {s.name for s in decision.stocks}
    for e in store.edges():
        if e["status"] != STATUS_ACTIVE:
            continue
        if e["source_name"] in names and e["target_name"] in text and e["target_name"] not in names:
            events[0]["target"] = e["target_name"]
            events[0]["target_type"] = e["target_type"] or "公司"
            events[0]["target_code"] = ""
            break
    return events


# --------------------------------------------------------------------------- #
# 对账 + 写库
# --------------------------------------------------------------------------- #
def commit(store, events: list[dict], *, date: str, stock_code: str,
           news: str) -> tuple[list[dict], list[dict], list[dict]]:
    """写库。返回 (新增边, 被证伪边, 被强化的已有边)。

    真实新闻里同一件事会被 4~5 家媒体重复报道，如果每条都建边，图会瞬间变成毛线团。
    所以同向证据合并到已有边上（evidence_refs 累加），只有方向相反才触发“证伪”。
    """
    added: list[dict] = []
    invalidated: list[dict] = []
    reinforced: list[dict] = []
    if not events:
        return added, invalidated, reinforced

    # 一条新闻只归档一次（L4），多条三元组共享同一个 archive_ref
    rec = l4.append_event(text=news, stock_code=stock_code, stock_name=events[0].get("source", ""),
                          publish_date=date, source="pipeline")
    for idx, ev in enumerate(events, start=1):
        ev["event_id"] = f"{rec['event_id']}-{idx:02d}"
        by = rec["event_id"]  # 推翻者指向 L4 新闻记录，永远可回溯

        # 反转：同主体+同对象，方向相反的旧逻辑 -> 已被证伪
        if ev["relation"] in POLARITY:
            opposite = "利空事件" if ev["relation"] == "利好事件" else "利好事件"
            hits = store.invalidate(source=ev["source"], target=ev["target"], rel_type=opposite,
                                    by_event=by, date=ev["date"],
                                    reason=f"被新事件推翻：{ev['reason'][:40]}")
            for h in hits:
                invalidated.append({"event_id": h, "by": by,
                                    "source": ev["source"], "target": ev["target"]})

        # 同向证据：合并到已有活跃边，而不是再画一条重复的边
        same = store.find_active(ev["source"], ev["target"], ev["relation"])
        if same:
            store.reinforce(same["id"], ev, rec["ref"])
            reinforced.append({"event_id": same["id"], "source": ev["source"],
                               "target": ev["target"], "relation": ev["relation"]})
            continue

        store.upsert_event(ev, rec["ref"])
        added.append({**ev, "archive_ref": rec["ref"]})

        for old_id in ev.get("invalidates", []) or []:
            hits = store.invalidate(event_id=old_id, by_event=by, date=ev["date"],
                                    reason=f"显式证伪：{ev['reason'][:40]}")
            for h in hits:
                invalidated.append({"event_id": h, "by": by,
                                    "source": ev["source"], "target": ev["target"]})
    return added, invalidated, reinforced


# --------------------------------------------------------------------------- #
# 结论
# --------------------------------------------------------------------------- #
def predict(store, *, code: str = "", name: str = "", hops: int = 1) -> dict:
    sg = store.subgraph(code=code or None, name=name or None, hops=hops)
    names = {n["name"] for n in sg["nodes"]}
    active = [e for e in sg["edges"] if e["status"] == STATUS_ACTIVE and e["type"] in POLARITY
              and (e["source_name"] in names and e["target_name"] in names)]
    invalid = [e for e in sg["edges"] if e["status"] == STATUS_INVALID and e["type"] in POLARITY]

    score = 0.0
    for e in active:
        score += POLARITY[e["type"]] * float(e["props"].get("confidence", 0.6))
    # 逻辑反转惩罚：被证伪的旧逻辑会削弱它原本支持的方向
    penalty = 0.5 * sum(POLARITY[e["type"]] * float(e["props"].get("confidence", 0.6)) for e in invalid)
    score -= penalty

    if score > 0.25:
        direction = "偏多"
    elif score < -0.25:
        direction = "偏空"
    else:
        direction = "中性"

    reasons = sorted(active, key=lambda e: -float(e["props"].get("confidence", 0)))[:4]
    return {
        "direction": direction,
        "score": round(score, 3),
        "active_score": round(score + penalty, 3),
        "reversal_penalty": round(penalty, 3),
        "confidence": round(min(0.95, max(0.35, 0.5 + abs(score) * 0.35)), 2),
        "n_active_bull": sum(1 for e in active if e["type"] == "利好事件"),
        "n_active_bear": sum(1 for e in active if e["type"] == "利空事件"),
        "n_invalidated": len(invalid),
        "invalidated": [{"source": e["source_name"], "target": e["target_name"], "edge": e["type"],
                         "reason": e["props"].get("reason") or e["props"].get("invalidated_reason", ""),
                         "by": e["props"].get("invalidated_by", ""),
                         "archive_ref": e["props"].get("archive_ref", "")} for e in invalid],
        "reasons": [{"text": e["props"].get("reason", ""), "edge": e["type"],
                     "source": e["source_name"], "target": e["target_name"],
                     "date": e["props"].get("date", ""), "event_id": e["id"],
                     "archive_ref": e["props"].get("archive_ref", "")} for e in reasons],
        "reversal": bool(invalid) and bool(active),
    }


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #
def run_news(news: str, store, *, use_llm: bool = True, date: Optional[str] = None,
             stock_code: str = "", hops: int = 1, trace: Optional[list] = None) -> RunResult:
    date = (date or datetime.now().strftime("%Y-%m-%d"))[:10]
    trace = trace if trace is not None else []

    decision = route(news)
    _trace(trace, "① 感知 / L1 路由", decision.explain(),
           hit=[s.name for s in decision.stocks], stats=decision.stats)

    theses = theses_block(store, decision)
    _trace(trace, "② 回忆 / L2 检索", f"召回活跃逻辑 {theses.count('- ')} 条")

    result = RunResult(news=news, date=date, mode="heuristic", routing=decision)
    result.trace = trace

    if use_llm:
        try:
            result.prompt = build_prompt(news, decision, theses, date)
            result.llm_raw = call_llm(result.prompt)
            events = parse_events(result.llm_raw)
            result.mode = "llm"
            _trace(trace, "③ 推演 / DeepSeek 抽取", f"模型返回 {len(events)} 条候选事件")
        except Exception as exc:
            _trace(trace, "③ 推演 / DeepSeek 抽取", f"调用失败：{exc}（回退到规则引擎，UI 会明确标注）")
            events = heuristic_extract_with_theses(news, decision, date, store)
            result.mode = "heuristic"
    else:
        events = heuristic_extract_with_theses(news, decision, date, store)
        _trace(trace, "③ 推演 / 规则引擎（0 Token）", f"生成 {len(events)} 条候选事件")

    valid, rejected = validate_events(events, date)
    result.events = valid
    result.rejected = rejected
    if rejected:
        _trace(trace, "④ 校验 / L0 白名单", f"拦截 {len(rejected)} 条越界三元组")

    for ev in valid:
        ev.pop("_news", None)

    added, invalidated, reinforced = commit(store, valid, date=date, news=news,
                                            stock_code=stock_code or
                                            (decision.stocks[0].code if decision.stocks else "000000"))
    result.added, result.invalidated, result.reinforced = added, invalidated, reinforced
    _trace(trace, "⑤ 行动 / 写 L2 + L4",
           f"新增 {len(added)} 条边，强化 {len(reinforced)} 条，证伪 {len(invalidated)} 条旧边")

    center = stock_code or (decision.stocks[0].code if decision.stocks else "")
    result.prediction = predict(store, code=center, hops=hops)
    _trace(trace, "⑥ 复盘 / 结论", f"{result.prediction['direction']}（score={result.prediction['score']}）")
    return result


if __name__ == "__main__":
    from store import LocalStore

    st = LocalStore()
    res = run_news("碳酸锂期货主力合约涨停，锂矿供给持续收紧，现货价格单月上涨30%。",
                   st, use_llm=False, date="2026-10-21")
    print(json.dumps({"mode": res.mode, "added": res.added, "invalidated": res.invalidated,
                      "prediction": res.prediction}, ensure_ascii=False, indent=2))
