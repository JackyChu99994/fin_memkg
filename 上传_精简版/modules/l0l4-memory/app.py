# -*- coding: utf-8 -*-
"""期末 Demo 大屏：左输入 / 中间图谱 / 右结论。

启动：  streamlit run app.py
"""
from __future__ import annotations

import json
from datetime import date as _date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import demo_data
import l4_archive as l4
import market_bridge
import viz
from agent import MemoryAgent
from config import (APP_TITLE, DEEPSEEK_MODEL, STATUS_ACTIVE, has_llm)
from store import get_store

st.set_page_config(page_title="Fin-MemKG", page_icon="🧠", layout="wide")

CSS = """
<style>
  .block-container {padding-top: 1.4rem; padding-bottom: 1rem;}
  .card {border:1px solid #2a2f3a; border-radius:12px; padding:14px 16px; background:#11161f;}
  .tag {display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; margin-right:6px;}
  .bull {background:#3a1518; color:#ff7b72;}
  .bear {background:#12291d; color:#3fb950;}
  .muted {color:#8b949e; font-size:12px;}
  .big {font-size:30px; font-weight:700;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def _store():
    return get_store()


store = _store()
demo_data.ensure_seeded(store)

if "news" not in st.session_state:
    st.session_state.news = demo_data.SCENARIOS["A"]["text"]
if "news_date" not in st.session_state:
    st.session_state.news_date = _date(2026, 10, 22)
if "last" not in st.session_state:
    st.session_state.last = None
if "prev_sg" not in st.session_state:
    st.session_state.prev_sg = None
if "center" not in st.session_state:
    st.session_state.center = "300750"


def _label(mode: str) -> str:
    return {"neo4j": "Neo4j AuraDB", "local": "本地 JSON（离线兜底）"}.get(mode, mode)


# --------------------------------------------------------------------------- #
# 侧边栏
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.title("🧠 Fin-MemKG")
    st.caption("L0–L4 分层记忆 · 股票量化情报")
    try:
        s = store.stats()
        st.success(f"存储：{_label(s.get('mode',''))}\n\n节点 {s.get('nodes',0)} · 边 {s.get('edges',0)}")
    except Exception as exc:
        st.error(f"存储连接失败：{exc}")

    _ms = market_bridge.status()
    if _ms.get("available"):
        st.caption(f"📈 行情底座：本地快照 {_ms.get('codes')} 只 / {_ms.get('rows', 0):,} 行"
                   f"（{_ms.get('start')} ~ {_ms.get('end')}）")
    else:
        st.caption("📈 行情底座：AkShare 在线（未发现本地快照）")

    st.divider()
    st.subheader("演示场景")
    for key, sc in demo_data.SCENARIOS.items():
        if st.button(sc["name"], use_container_width=True, key=f"sc_{key}"):
            st.session_state.news = sc["text"]
            st.session_state.news_date = _date.fromisoformat(sc["date"])
            st.rerun()

    st.divider()
    use_llm = st.toggle("调用 DeepSeek 抽取", value=has_llm(),
                        help="关闭后使用 0-Token 规则引擎，答辩断网也能演示")
    if not has_llm() and use_llm:
        st.warning("未检测到 DEEPSEEK_API_KEY，将自动回退到规则引擎。")

    if st.button("♻️ 重建演示图谱", use_container_width=True):
        demo_data.seed(store, reset=True)
        st.session_state.last = None
        st.session_state.prev_sg = None
        st.rerun()

    st.divider()
    with st.expander("L0 元规则（写进 Prompt，也写进代码）"):
        from l0_rules import META_RULES

        for r in META_RULES:
            st.markdown(f"**{r['id']} {r['name']}**  \n{r['text']}")
    with st.expander("工具清单（运动器官）"):
        st.dataframe(pd.DataFrame(MemoryAgent.tool_specs()), hide_index=True,
                     use_container_width=True)

# --------------------------------------------------------------------------- #
# 主体三栏
# --------------------------------------------------------------------------- #
left, mid, right = st.columns([1.05, 1.6, 1.25], gap="medium")

with left:
    st.subheader("① 情报输入")
    news = st.text_area("新闻原文", key="news", height=150,
                        placeholder="粘贴一条新闻，例如：碳酸锂期货涨停，锂矿供给收紧…")
    d = st.date_input("事件日期", key="news_date", format="YYYY-MM-DD")
    code = st.text_input("主标的代码", value=st.session_state.center, max_chars=6,
                         help="留空则使用 L1 路由命中的第一只标的")

    run_llm = st.button("🚀 运行 Agent（大模型）", type="primary", use_container_width=True, disabled=not news.strip())
    run_rule = st.button("🧪 只跑规则引擎（0 Token）", use_container_width=True, disabled=not news.strip())

    if run_llm or run_rule:
        agent = MemoryAgent(store, use_llm=run_llm and use_llm)
        with st.spinner("感知 → 路由 → 抽取 → 写回 → 复盘 …"):
            try:
                st.session_state.prev_sg = store.subgraph(code=code or None, hops=1)
                res = agent.run(news, date=d.strftime("%Y-%m-%d"), stock_code=code)
                st.session_state.last = res
                st.session_state.center = code or st.session_state.center
            except Exception as exc:
                st.session_state.last = None
                st.error(f"运行失败：{exc}")

    last = st.session_state.last
    if last:
        st.divider()
        st.markdown("**L1 路由结果**")
        st.info(last.run.routing.explain())
        stt = last.run.routing.stats or {}
        m1, m2, m3 = st.columns(3)
        m1.metric("候选/全市场", f"{stt.get('kept',0)}/{stt.get('universe',0)}")
        m2.metric("Prompt token", f"≈{stt.get('routed_tokens_est',0)}")
        m3.metric("节省", f"{int(stt.get('saved_pct',0)*100)}%")
        if last.run.mode == "heuristic":
            st.warning("本次由规则引擎产出（未调用大模型），用于演示流程；结论不代表模型能力。")

        if last.run.rejected:
            with st.expander(f"⛔ L0 校验拦截 {len(last.run.rejected)} 条"):
                st.json(last.run.rejected)
    else:
        st.caption("提示：先点左侧场景按钮，再点“运行 Agent”。")

with mid:
    st.subheader("② L2 逻辑图谱")
    stats = store.stats()
    m = st.columns(4)
    m[0].metric("活跃利好", stats.get("active_bull", 0))
    m[1].metric("活跃利空", stats.get("active_bear", 0))
    m[2].metric("已被证伪", stats.get("invalidated", 0))
    m[3].metric("节点", stats.get("nodes", 0))

    highlight = set()
    if last:
        highlight = {a["event_id"] for a in last.run.added}
    try:
        sg = store.subgraph(code=st.session_state.center or None, hops=1)
        if sg.get("error"):
            st.warning(f"Neo4j 查询异常，已展示空图：{sg['error']}")
        html = viz.build_network_html(sg, height=520, highlight_ids=highlight,
                                      title=f"以 {st.session_state.center} 为中心的一跳子图")
        components.html(html, height=580, scrolling=True)
    except Exception as exc:
        st.error(f"图谱渲染失败：{exc}")
        sg = {"nodes": [], "edges": []}

    with st.expander("Mermaid 源码（可直接贴进报告/PPT）"):
        st.code(viz.mermaid_source(sg), language="mermaid")

with right:
    st.subheader("③ 结论与检验")
    if not last:
        st.info("运行一次后，这里会出现：方向判断 / 证据链 / 事件研究 CAR。")
    else:
        dec = last.decision
        color = {"偏多": "#ff7b72", "偏空": "#3fb950"}.get(dec.get("direction", ""), "#d29922")
        st.markdown(
            f"<div class='card'><span class='big' style='color:{color}'>{dec.get('direction','-')}</span>"
            f"<span class='muted'>　置信度 {dec.get('confidence','-')} · 打分 {dec.get('score','-')}</span>"
            f"<div style='margin-top:8px;font-size:16px'>动作建议：<b>{dec.get('action','-')}</b></div>"
            f"<div class='muted'>{dec.get('why','')}</div></div>",
            unsafe_allow_html=True,
        )
        st.markdown("")
        if last.study:
            s1, s2, s3 = st.columns(3)
            s1.metric("CAR", f"{last.study['car_pct']:+.1f}%")
            s2.metric("Beta", f"{last.study['beta']:.2f}")
            s3.metric("交易日", f"{last.study['n_days']}")
            st.caption(f"数据源：{last.study['source']} · 基准 {last.study['benchmark']} · "
                       f"{'窗口完整' if last.study.get('complete') else '窗口尚未走完，仅作参考'}")
            st.markdown(f"<div class='muted'>{dec.get('car_verdict','')}</div>", unsafe_allow_html=True)
            with st.expander("逐日超额收益"):
                st.dataframe(pd.DataFrame(last.study["table"]), hide_index=True, use_container_width=True)
        elif last.study_error:
            st.warning(f"L3 事件研究失败：{last.study_error}")

        st.markdown("**证据链（点开即见 L4 原文）**")
        for r in dec.get("reasons", []):
            tag = "bull" if r["edge"] == "利好事件" else "bear"
            st.markdown(
                f"<div class='card' style='padding:10px 12px;margin-bottom:8px'>"
                f"<span class='tag {tag}'>{r['edge']}</span>"
                f"<b>{r['source']} → {r['target']}</b>"
                f"<div class='muted'>{r['text']}（{r['date']}）</div></div>",
                unsafe_allow_html=True)
            rec = l4.resolve(r.get("archive_ref", ""))
            if rec:
                with st.expander("查看原文证据"):
                    st.caption(f"{rec['publish_date']} · {rec['source']} · {rec['ref']}")
                    st.write(rec["text"])

    if last and (last.run.added or last.run.invalidated or last.run.reinforced):
        st.divider()
        st.markdown("**本次变更**")
        if last.run.invalidated:
            st.error(f"证伪 {len(last.run.invalidated)} 条：逻辑反转")
        if last.run.reinforced:
            st.info(f"强化 {len(last.run.reinforced)} 条已有逻辑（同向证据合并，图不重复建边）")
        for a in last.run.added:
            st.success(f"新增 {a['relation']}：{a['source']} → {a['target']}（{a['reason']}）")

# --------------------------------------------------------------------------- #
# 底部：运行轨迹 / Prompt 对比
# --------------------------------------------------------------------------- #
st.divider()
t1, t2 = st.columns([1.4, 1])
with t1:
    with st.expander("🕵️ Agent 运行轨迹（可解释性）", expanded=bool(st.session_state.last)):
        if st.session_state.last:
            st.dataframe(pd.DataFrame([{"步骤": s.name, "工具": s.tool, "结果": s.detail,
                                        "耗时(ms)": s.ms, "状态": "✅" if s.ok else "❌"}
                                       for s in st.session_state.last.steps]),
                         hide_index=True, use_container_width=True)
            st.caption(f"总耗时 {st.session_state.last.elapsed_ms} ms · 模型 {DEEPSEEK_MODEL}")
        else:
            st.write("尚未运行。")
with t2:
    with st.expander("📉 L1 降噪：全量 vs 路由"):
        from l1_router import route, universe_block

        sample = st.session_state.get("news", "")
        dec = route(sample)
        st.code(f"全量标的 Prompt：{dec.stats.get('full_tokens_est', 0)} token\n"
                f"L1 路由后：      {dec.stats.get('routed_tokens_est', 0)} token\n"
                f"节省：          {dec.stats.get('saved_pct', 0)*100:.0f}%", language="text")
        with st.expander("看看全量 Prompt 长什么样"):
            st.text(universe_block())

st.caption("Fin-MemKG · 课程项目 Demo · 数据来源 AkShare / 新闻原文归档于 memory/L4_archive/news.jsonl")
