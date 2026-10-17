"""Fin-MemKG · Qwen 动态金融知识图谱与投资论点记忆更新工作台。"""
from __future__ import annotations

import re
from typing import Any, Dict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from plotly.subplots import make_subplots
from pyvis.network import Network

from agent_loop import (
    QwenAPIError,
    analyze_demo_event,
    cold_start_stock,
    get_builtin_demo_result,
    load_qwen_config,
    run_agent_inference,
)
from tools import (
    L2_DIR,
    fetch_market_data,
    find_contagion_paths,
    load_l2_graph,
    query_l4_archive,
    read_l1_index,
    verify_priced_in,
)

st.set_page_config(
    page_title="Fin-MemKG · Qwen 动态金融知识图谱工作台",
    page_icon="🕸️",
    layout="wide",
)
st.markdown("<style>.block-container{padding-top:1.1rem;padding-bottom:1rem;}</style>", unsafe_allow_html=True)

PRESET_EVENTS = {
    "300308.SZ": [
        (
            "🔥 场景A：英伟达Blackwell推迟（逻辑反转 / INVALIDATE）",
            "海外供应链核心快讯",
            "英伟达Blackwell B200机柜因连接器与散热背板公差缺陷推迟大批量交付一个季度",
            "受机柜散热方案改版影响，北美云厂商配套1.6T光模块集中提货节点顺延至明年Q2。",
            "EMPIRICAL_NEWS_FILING",
        ),
        (
            "⚠️ 场景B：三季报预增165%但近20日已涨28%（利好出尽 / PRICED_IN）",
            "深交所业绩预告",
            "中际旭创披露前三季度净利预增165%，符合卖方一致预期上限",
            "公司800G出货保持高景气，但前期股价已连续大涨28%，处于60日96%极高分位，获利盘兑现压力显著。",
            "EMPIRICAL_NEWS_FILING",
        ),
        (
            "🔗 场景C：磷化铟晶圆停产->Lumentum EML紧缺（两跳三节点传导 / 2-Hop Contagion）",
            "海外光电产业链快讯",
            "上游磷化铟(InP)晶圆外延片大厂产线停产检修两周，Lumentum 200G EML光芯片现货跳涨15%",
            "磷化铟衬底短缺传导至中游EML光芯片制造商Lumentum，导致下游800G/1.6T光模块厂面临物料配额收紧。",
            "EMPIRICAL_NEWS_FILING",
        ),
    ],
    "default": [
        (
            "🔥 场景A：下游大客户突发砍单（逻辑反转）",
            "产业链调研快讯",
            "核心下游客户下调四季度排产指引25%，要求供应链降价10%",
            "受终端需求放缓及库存积压影响，核心客户突发削减四季度采购订单并要求重新议价。",
            "EMPIRICAL_NEWS_FILING",
        ),
        (
            "⚠️ 场景B：业绩大增但股价处于95%分位（利好出尽）",
            "公司定期报告公告",
            "三季报净利润同比增长140%，前期股价已连续上涨30%",
            "公告业绩靓丽，但二级市场近20日涨幅已超30%，买方预期高度饱和。",
            "EMPIRICAL_NEWS_FILING",
        ),
    ],
}


def _render_pyvis_html(graph_obj) -> str:
    net = Network(height="380px", width="100%", bgcolor="#0E1117", font_color="#F8FAFC", directed=True)
    net.barnes_hut(gravity=-2800, central_gravity=0.35, spring_length=125)
    c_id = graph_obj.stock_code
    net.add_node(
        c_id,
        label=f"{graph_obj.stock_name}\n({c_id})\n净势能:{graph_obj.market_regime.net_sentiment_score:+.2f}",
        color="#3B82F6",
        size=30,
        shape="diamond",
    )
    for n in graph_obj.thesis_nodes:
        if n.status == "INVALIDATED":
            color, border, label = "#64748B", "#475569", f"❌ [已证伪]\n{n.id}: {n.title[:11]}"
        elif n.status == "PRICED_IN":
            color, border, label = "#F59E0B", "#D97706", f"⚠️ [已钝化]\n{n.id}: {n.title[:11]}"
        elif n.type == "BULLISH_LOGIC":
            color, border, label = "#10B981", "#059669", f"📈 {n.id}: {n.title[:12]}\n(w={n.weight:.2f})"
        else:
            color, border, label = "#EF4444", "#DC2626", f"📉 {n.id}: {n.title[:12]}\n(w={n.weight:.2f})"
        tip = (
            f"[{n.id}] {n.title}\n"
            f"状态: {n.status} | 权重: {n.weight} | 置信度: {n.confidence}\n"
            f"兑现度: {n.priced_in_ratio:.2f}\n"
            f"证伪条件: {n.invalidation_condition}"
        )
        net.add_node(
            n.id,
            label=label,
            title=tip,
            color={"background": color, "border": border},
            size=16 + int(n.weight * 14),
        )
        net.add_edge(c_id, n.id, color="#334155", width=1.5)
    for e in graph_obj.edges:
        ec = "#A855F7" if e.relation == "COMPETES_WITH" else ("#EF4444" if e.relation == "INVALIDATES" else "#38BDF8")
        net.add_edge(
            e.source,
            e.target,
            label=f"{e.relation}(σ={e.transmission_sign})",
            color=ec,
            dashes=(e.relation == "COMPETES_WITH"),
            width=2,
        )
    return net.generate_html()


stocks: dict[str, str] = {p.stem: p.stem for p in L2_DIR.glob("*.json") if p.stem != "sector_chains"}
stock_names: dict[str, str] = {}
for m in re.finditer(r"`(\d{6}\.(?:SZ|SH))`\s+\*\*([^*]+)\*\*", read_l1_index()):
    code_i, name_i = m.group(1), m.group(2).strip()
    stocks[code_i] = f"{code_i} ({name_i})"
    stock_names[code_i] = name_i
for c_code, c_name in st.session_state.get("custom_stocks", {}).items():
    stocks[c_code] = f"{c_code} ({c_name})" if c_name and c_name != c_code else c_code
    stock_names[c_code] = c_name or c_code
stock_list = sorted(stocks.keys()) or ["300308.SZ"]
if "sel_stock" not in st.session_state or st.session_state["sel_stock"] not in stock_list:
    st.session_state["sel_stock"] = "300308.SZ" if "300308.SZ" in stock_list else stock_list[0]

cur_code = st.session_state["sel_stock"]
as_of_dt = st.session_state.get("as_of_dt", "2026-10-14")
res_state = st.session_state.get("last_res")
has_active_res = bool(res_state and res_state.get("stock") == cur_code and res_state.get("as_of_date") == as_of_dt)
cold_cache = st.session_state.get("cold_graphs", {})

if has_active_res:
    g_cur = res_state["res"]["graph_after"]
elif (cur_code, as_of_dt) in cold_cache:
    g_cur = cold_cache[(cur_code, as_of_dt)]
else:
    g_cur = load_l2_graph(cur_code, as_of_date=as_of_dt) or cold_start_stock(
        cur_code, stock_names.get(cur_code, cur_code), as_of_dt, persist=False, use_builtin_demo=True
    )

l3_info = verify_priced_in(cur_code, as_of_dt)
meta = res_state["res"].get("execution_meta", {}) if has_active_res else {}
qwen_cfg = load_qwen_config()

with st.sidebar:
    st.markdown("### 🔑 Qwen API 配置状态")
    st.markdown(f"- **QWEN_API_KEY**：`{'已设置' if qwen_cfg['has_api_key'] else '未设置'}`")
    st.markdown(f"- **QWEN_MODEL**：`{qwen_cfg['model'] or '未设置'}`")
    st.markdown(f"- **QWEN_BASE_URL**：  \n  `{qwen_cfg['base_url']}`")
    st.caption("固定使用阿里云 DashScope OpenAI 兼容 Chat Completions 接口（`max_retries=0`，不读取 OPENAI_* 等多套变量）。")

    st.markdown("### 🛡️ 运行时透明审计徽章")
    inf_mode = meta.get("inference_mode", "READY (待触发推演)")
    read_mode = meta.get("storage_read_mode", l3_info.get("storage_read_mode", "DISK_CACHE"))
    data_orig = meta.get("underlying_data_origin", l3_info.get("underlying_data_origin", "SYNTHETIC_SIMULATION"))
    tok_type = meta.get("token_count_type", "MISSING_OR_ESTIMATED")
    p_mod = meta.get("persistence_mode", "IN_MEMORY_PREVIEW (零写盘隔离)")

    st.info(f"**推理引擎 (`inference_mode`)**：\n`{inf_mode}`\nModel: `{meta.get('llm_model', qwen_cfg['model'])}`")
    st.success(f"**1. 读取介质 (`storage_read_mode`)**：\n`{read_mode}`")
    if data_orig == "REAL_MARKET_API":
        st.success(f"**2. 底层源产地 (`underlying_data_origin`)**：\n`{data_orig}`")
    else:
        st.warning(f"**2. 底层源产地 (`underlying_data_origin`)**：\n`{data_orig}`")
    st.info(f"**3. Token 计量 (`token_count_type`)**：\n`{tok_type}`")
    st.caption(f"持久化状态: `{p_mod}`")

st.markdown("### 🧠 Fin-MemKG：面向金融事件的投资论点记忆与更新工作台 (Qwen API 驱动)")
st.caption("支持 L4 证据追踪、L2 论点证伪 (INVALIDATE)、L3 价格反映度钝化 (PRICED_IN) 与两跳三节点产业链传导（固定连接阿里云 DashScope Qwen API）")

if not qwen_cfg["ready"]:
    missing_str = "、".join(qwen_cfg["missing_fields"])
    st.warning(
        f"⚠️ 当前缺少配置项：**{missing_str}**。未配置时点击“调用 Qwen API”不会发起网络请求；请在 `.env` 中设置，或点击 **“📋 使用演示结果”** 进行离线图谱演示。"
    )

m1, m2, m3, m4 = st.columns(4)
m1.metric("当前选中标的", f"{g_cur.stock_name} ({cur_code})", f"截至 {as_of_dt} (零写盘安全回放)")
delta_s = (
    f"{res_state['res']['score_after'] - res_state['res']['score_before']:+.2f} (推演Delta)"
    if has_active_res
    else "多空逻辑净势能指数 [-2,+2]"
)
m2.metric("L2 多空逻辑净势能指数", f"{g_cur.market_regime.net_sentiment_score:+.2f}", delta_s)
m3.metric(
    "L3 预期兑现度 & 经验分位",
    f"{l3_info['priced_in_ratio']*100:.0f}% (Rank:{l3_info['close_rank_pct_60d']*100:.0f}%)",
    f"区间位置:{l3_info['range_pos_60d']*100:.0f}% | 20日:{l3_info['return_20d_pct']:+.1f}%",
    delta_color="inverse" if l3_info["priced_in_ratio"] > 0.8 else "normal",
)
tok_val = meta.get("total_tokens", 1320)
m4.metric("单次推演上下文体积", f"{tok_val:,} Tokens", f"模型: {meta.get('llm_model', qwen_cfg['model'])}")

col_left, col_mid, col_right = st.columns([1.18, 1.82, 1.45])

with col_left:
    st.subheader("1️⃣ 路由、时间机器与事件注入")
    sel = st.selectbox(
        "选择已有图谱标的",
        options=stock_list,
        index=stock_list.index(cur_code),
        format_func=lambda x: stocks.get(x, x),
    )
    if sel != cur_code:
        st.session_state["sel_stock"] = sel
        st.session_state.pop("last_err", None)
        st.rerun()

    as_of_input = st.date_input("📅 历史时间切片 (as_of_date，完整回放快照)", value=pd.to_datetime(as_of_dt)).strftime("%Y-%m-%d")
    if as_of_input != as_of_dt:
        st.session_state["as_of_dt"] = as_of_input
        st.session_state.pop("last_err", None)
        st.rerun()

    presets = PRESET_EVENTS.get(cur_code, PRESET_EVENTS["default"])
    p_idx = st.selectbox("⚡ 预设催化事件模板", range(len(presets)), format_func=lambda i: presets[i][0])
    ev_src = st.text_input("事件来源", value=presets[p_idx][1])
    ev_title = st.text_input("突发事件标题", value=presets[p_idx][2])
    ev_body = st.text_area("事件正文摘要", value=presets[p_idx][3], height=80)

    use_cache_chk = st.checkbox("📦 优先使用本地缓存（相同事件与模型不重复发起请求）", value=True)
    persist_chk = st.checkbox("💾 将本次推演结果持久化写入正式记忆库 (默认关闭以保护基准)", value=False)

    btn_c1, btn_c2 = st.columns(2)
    with btn_c1:
        clicked_demo = st.button("📋 使用演示结果", use_container_width=True)
    with btn_c2:
        clicked_qwen_api = st.button("🚀 调用 Qwen API", type="primary", use_container_width=True)

    event_payload: Dict[str, Any] = {
        "published_at": f"{as_of_input} 09:30:00",
        "source": ev_src,
        "title": ev_title,
        "content": ev_body,
        "stock_code": cur_code,
        "stock_name": g_cur.stock_name,
        "evidence_type": presets[p_idx][4],
    }

    if clicked_demo:
        try:
            single_demo = get_builtin_demo_result(event_payload)
            out = run_agent_inference(
                cur_code,
                g_cur.stock_name,
                event_payload,
                as_of_date=as_of_input,
                persist=persist_chk,
                use_builtin_demo=True,
                use_cache=False,
            )
            st.session_state["last_res"] = {
                "stock": cur_code,
                "as_of_date": as_of_input,
                "res": out,
                "single": single_demo,
                "injected_event": {
                    "event_id": out["event_id"],
                    "published_at": f"{as_of_input} 09:30:00",
                    "source": ev_src,
                    "title": ev_title,
                    "evidence_type": out["evidence_type"],
                },
            }
            st.session_state.pop("last_err", None)
            st.rerun()
        except Exception as err:
            st.session_state["last_err"] = {
                "error_type": "演示执行异常",
                "message": str(err),
                "hint": "请检查输入日期与图谱状态约束。",
            }

    if clicked_qwen_api:
        with st.spinner("正在调用阿里云 DashScope Qwen API 执行单事件结构化抽取与 L2 图谱状态更新..."):
            try:
                single_live = analyze_demo_event(event_payload, use_cache=use_cache_chk)
                out = run_agent_inference(
                    cur_code,
                    g_cur.stock_name,
                    event_payload,
                    as_of_date=as_of_input,
                    persist=persist_chk,
                    use_builtin_demo=False,
                    use_cache=use_cache_chk,
                )
                st.session_state["last_res"] = {
                    "stock": cur_code,
                    "as_of_date": as_of_input,
                    "res": out,
                    "single": single_live,
                    "injected_event": {
                        "event_id": out["event_id"],
                        "published_at": f"{as_of_input} 09:30:00",
                        "source": ev_src,
                        "title": ev_title,
                        "evidence_type": out["evidence_type"],
                    },
                }
                st.session_state.pop("last_err", None)
                st.rerun()
            except QwenAPIError as err:
                st.session_state["last_err"] = err.to_dict()
            except Exception as err:
                st.session_state["last_err"] = {
                    "error_type": f"执行异常 ({type(err).__name__})",
                    "message": str(err),
                    "hint": "请检查输入参数或点击“使用演示结果”查看内置图谱演示。",
                }

    if st.session_state.get("last_err"):
        err_obj = st.session_state["last_err"]
        if isinstance(err_obj, dict):
            st.error(f"❌ **调用失败：{err_obj.get('error_type', '错误')}**")
            st.markdown(f"- **原因**：`{err_obj.get('message', '')}`")
            st.markdown(f"- **下一步提示**：{err_obj.get('hint', '')}")
            if err_obj.get("raw_output"):
                with st.expander("查看模型原始输出片段"):
                    st.code(err_obj["raw_output"], language="text")
        else:
            st.error(str(err_obj))

    with st.expander("❄️ 任意 A 股代码冷启动建图", expanded=False):
        cs_code = st.text_input("股票代码", value="688981.SH")
        cs_name = st.text_input("股票名称", value="中芯国际")
        if st.button("🚀 一键冷启动 (先验节点将标注 COLD_START_PRIOR)", use_container_width=True):
            c_code_clean = cs_code.strip().upper()
            c_name_clean = cs_name.strip() or c_code_clean
            cs_g = cold_start_stock(c_code_clean, c_name_clean, as_of_input, persist=persist_chk, use_builtin_demo=True)
            st.session_state.setdefault("custom_stocks", {})[c_code_clean] = c_name_clean
            st.session_state.setdefault("cold_graphs", {})[(c_code_clean, as_of_input)] = cs_g
            st.session_state["sel_stock"] = c_code_clean
            st.session_state.pop("last_err", None)
            st.rerun()

with col_mid:
    st.subheader("2️⃣ L2 多空逻辑图谱与两跳三节点传导链")

    if has_active_res:
        r = res_state["res"]
        if r.get("is_demo_fallback"):
            st.warning("⚠️ **当前为演示数据，未调用 Qwen API**（由“使用演示结果”按钮触发）")
        elif r.get("from_cache"):
            st.info(f"📦 **{r.get('status_label', '本地缓存命中')}**")
        else:
            st.success(f"✅ **{r.get('status_label', '真实 Qwen API 图谱推演成功')}**")

    components.html(_render_pyvis_html(g_cur), height=390, scrolling=False)

    live_paths = (
        res_state["res"].get("contagion_paths", []) if has_active_res else []
    ) or find_contagion_paths(f"{ev_title} {ev_body}", cur_code)
    if live_paths:
        tp = live_paths[0]
        st.info(
            f"🔗 **跨公司两跳三节点传导路径 (`actual_hops={tp['actual_hops']}`)**：`{tp['path']}`\n\n"
            f"- **公式折算**：$\\sigma={tp['transmission_sign']},\\ \\gamma_{{\\text{{total}}}}={tp['gamma_total']},\\ \\lambda={tp['lambda_decay']} \\Rightarrow \\text{{PathFactor}}={tp['path_factor']:+.4f}$\n"
            f"- **逐跳明细**：{tp['description']}"
        )

    if has_active_res:
        r = res_state["res"]
        st.markdown(f"**📋 状态机审计日志 (`score: {r['score_before']:+.2f} → {r['score_after']:+.2f}`)**")
        for op in r["inference"].patch_ops:
            badge = (
                "🔴 INVALIDATE"
                if op.op == "INVALIDATE"
                else ("🟡 PRICED_IN" if op.op == "PRICED_IN" else ("🟢 CONFIRM" if op.op == "CONFIRM" else "🔵 ADD_NODE"))
            )
            st.markdown(
                f"- **{badge}** `{op.target_node_id or (op.new_node.id if op.new_node else '')}` (证据 `{op.evidence_id}`)：{op.reason}"
            )
        fc = r["inference"]
        c1, c2, c3 = st.columns(3)
        c1.info(f"**T+1**: {fc.t1_forecast.direction} ({fc.t1_forecast.confidence:.0%})\n\n{fc.t1_forecast.reasoning}")
        c2.warning(f"**T+5**: {fc.t5_forecast.direction} ({fc.t5_forecast.confidence:.0%})\n\n{fc.t5_forecast.reasoning}")
        c3.success(f"**T+20**: {fc.t20_forecast.direction} ({fc.t20_forecast.confidence:.0%})\n\n{fc.t20_forecast.reasoning}")

with col_right:
    st.subheader("3️⃣ 单事件要素、L3 经验分位 & L4 证据溯源")

    if has_active_res and res_state.get("single"):
        s_res = res_state["single"]
        s_ana = s_res.get("analysis", {})
        with st.container(border=True):
            st.markdown("##### 🎯 单事件结构化分析结果 (`DemoEventAnalysis`)")
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("事件类型", s_ana.get("event_type", "-"))
            sc2.metric("影响方向 / 风险", f"{s_ana.get('impact_direction', '-')} / {s_ana.get('risk_level', '-')}")
            sc3.metric("置信度", f"{float(s_ana.get('confidence', 0.0)):.2f}")
            st.markdown(f"**事件摘要**：{s_ana.get('event_summary', '')}")
            ents = s_ana.get("entities", [])
            if ents:
                ent_tags = " ".join([f"`{e.get('name')}({e.get('type')})`" for e in ents])
                st.markdown(f"**识别实体**：{ent_tags}")
            st.caption(
                f"当前模型：`{s_res.get('model', '-')}` | 调用成功：`{'是' if s_res.get('call_success') else '否(演示数据)'}` | 来自缓存：`{'是' if s_res.get('from_cache') else '否'}`"
            )

    m_data = fetch_market_data(cur_code, as_of_dt)
    df_k = pd.DataFrame(m_data.get("klines_60d", []))
    if not df_k.empty:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.68, 0.32])
        fig.add_trace(
            go.Scatter(x=df_k["date"], y=df_k["close"], mode="lines", name="收盘价", line=dict(color="#38BDF8", width=2.2)),
            row=1,
            col=1,
        )
        if l3_info["priced_in_ratio"] > 0.8:
            fig.add_hrect(
                y0=df_k["close"].min() + 0.8 * (df_k["close"].max() - df_k["close"].min()),
                y1=df_k["close"].max() * 1.02,
                fillcolor="#EF4444",
                opacity=0.18,
                line_width=0,
                annotation_text="⚠️ 预期透支警戒区",
                row=1,
                col=1,
            )
        fig.add_trace(go.Bar(x=df_k["date"], y=df_k["turnover"], name="换手率%", marker_color="#F59E0B"), row=2, col=1)
        fig.update_layout(height=265, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**🔍 L4 证据库溯源（严格校验 `evidence_type` 与唯一 `event_id`）**")
    l4_map = {item["event_id"]: item for item in query_l4_archive(cur_code, as_of_date=as_of_dt)}
    if has_active_res and res_state.get("injected_event"):
        inj = res_state["injected_event"]
        l4_map.setdefault(inj["event_id"], inj)
    for n in g_cur.thesis_nodes:
        with st.expander(f"[{n.id}] {n.title[:18]} ({n.status})", expanded=(n.status != "ACTIVE")):
            st.caption(f"证伪条件: `{n.invalidation_condition}` | 更新于: `{n.updated_at}`")
            for ptr in n.evidence_pointers:
                clean_id = ptr.lstrip("#")
                if clean_id in l4_map:
                    ev_item = l4_map[clean_id]
                    st.markdown(
                        f"- **`{clean_id}`** [`{ev_item.get('evidence_type', 'EMPIRICAL_NEWS_FILING')}`] ({ev_item.get('published_at','')[:10]}): {ev_item.get('title','')}"
                    )
