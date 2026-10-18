from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Optional
from schema import L2Graph

BASE_DIR = Path(__file__).resolve().parent
L0_PATH = BASE_DIR / "memory/L0_meta_rules.md"
SOP_PATH = BASE_DIR / "memory/L3_skills/sop_cold_start.md"
INPUT_SCHEMA_VERSION = "v4_unified_single_and_graph"
DEMO_PROMPT_VERSION = "qwen_demo_prompt_v1"
DEMO_SCHEMA_VERSION = "qwen_demo_schema_v1"

SOP_COLD_START_MD = """# L3 Skill SOP: 陌生个股 10 秒冷启动建图 (Cold-Start Graph Initialization)
1. **触发条件**：当查询标的未命中 `memory/L2_graphs/{stock_code}.json` 时自动触发。
2. **输入隔离**：严格使用 `published_at <= as_of_date` 的近 15 条新闻与 60 日量价指标（`close_rank_pct_60d` 经验分位与 `range_pos_60d` 区间位置），严禁前视偏差。
3. **证据闭环**：提取 2~4 个多空 `ThesisNode`（每个 `ACTIVE` 节点必须绑定合法的 L4 `EV_YYYYMMDD_...` 证据指针与明确的 `invalidation_condition`）及传导边 `Edge`。
"""

UNIFIED_OUTPUT_SCHEMA_DOC = """请严格输出符合以下统一契约的紧凑纯 JSON 对象（InferenceResponse，同时包含单事件结构化分析与图谱状态修正；硬性输出预算：只输出紧凑 JSON；每条 reason/reasoning 不超过 80 个汉字；patch_ops 最多 3 条；watch_indicators 最多 3 条）：
{
  "event_summary": "一句话概括本次事件的核心事实与传导逻辑（不超过100字）",
  "entities": [
    {"name": "实体名称", "type": "公司/产品/客户/地区/政策"}
  ],
  "event_type": "供应链/技术/业绩/政策/需求",
  "impact_direction": "positive" | "negative" | "neutral",
  "risk_level": "low" | "medium" | "high",
  "event_confidence": 0.85,
  "patch_ops": [
    {
      "op": "CONFIRM" | "INVALIDATE" | "PRICED_IN" | "ADD_NODE",
      "target_node_id": "若操作针对已有候选论点则填写其ID（如 'TH_01'），若为 ADD_NODE 则为 null",
      "reason": "状态更新或新增节点的具体依据（不超过80个汉字）",
      "new_weight": 0.85,
      "evidence_id": "当前事件唯一证据ID",
      "published_at": "当前事件发布时间",
      "new_node": {
        "id": "TH_NEW_01",
        "type": "BULLISH_LOGIC" | "BEARISH_LOGIC",
        "title": "新增论点标题（仅当 op == 'ADD_NODE' 时提供，否则为 null）",
        "category": "EVENT",
        "status": "ACTIVE",
        "weight": 0.80,
        "confidence": 0.85,
        "created_at": "YYYY-MM-DD",
        "updated_at": "YYYY-MM-DD",
        "priced_in_ratio": 0.15,
        "evidence_pointers": ["当前事件唯一证据ID"],
        "invalidation_condition": "具体可验证的证伪条件（不超过40个汉字）"
      }
    }
  ],
  "contagion_impact": "跨公司/产业链传导影响分析（不超过80个汉字，无则填 null）",
  "t1_forecast": {"direction": "BULLISH" | "NEUTRAL" | "BEARISH", "confidence": 0.80, "reasoning": "T+1 推演依据（不超过80个汉字）"},
  "t5_forecast": {"direction": "BULLISH" | "NEUTRAL" | "BEARISH", "confidence": 0.80, "reasoning": "T+5 推演依据（不超过80个汉字）"},
  "t20_forecast": {"direction": "BULLISH" | "NEUTRAL" | "BEARISH", "confidence": 0.75, "reasoning": "T+20 推演依据（不超过80个汉字）"},
  "watch_indicators": ["后续观察指标1", "后续观察指标2"]
}"""


def _load_l0_rules() -> str:
    return L0_PATH.read_text(encoding="utf-8").strip() if L0_PATH.exists() else ""


def build_demo_event_prompt(
    title: str,
    content: str,
    source: str = "",
    stock_code: str = "",
    stock_name: str = "",
) -> tuple[str, str]:
    """构建第一版 Qwen Demo 的系统 Prompt 与用户输入，要求只输出纯 JSON，不输出 Markdown 或解释文字。"""
    system_prompt = (
        "你是金融事件结构化分析助手。请针对用户输入的金融事件进行结构化分析，"
        "只输出一个合法的紧凑 JSON 对象，不输出 Markdown 代码块标记，不输出任何解释文字。\n"
        "输出预算限制：event_summary 最多 120 字；evidence 最多 3 条（每条不超过 60 字）。\n"
        "JSON 格式如下：\n"
        "{\n"
        '  "event_summary": "事件摘要（最多120字）",\n'
        '  "entities": [\n'
        "    {\n"
        '      "name": "实体名称",\n'
        '      "type": "公司、产品、地区或其他"\n'
        "    }\n"
        "  ],\n"
        '  "event_type": "供应链、技术、政策或其他",\n'
        '  "impact_direction": "positive、negative 或 neutral",\n'
        '  "risk_level": "low、medium 或 high",\n'
        '  "confidence": 0.0,\n'
        '  "evidence": [\n'
        '    "支持判断的原文证据（最多3条）"\n'
        "  ]\n"
        "}"
    )
    meta_parts: list[str] = []
    if stock_code or stock_name:
        meta_parts.append(f"关联标的：{stock_name} ({stock_code})")
    if source:
        meta_parts.append(f"信息来源：{source}")
    meta_header = ("\n".join(meta_parts) + "\n") if meta_parts else ""
    user_prompt = f"{meta_header}事件标题：{title.strip()}\n事件摘要：{content.strip()}"
    return system_prompt, user_prompt


def build_cold_start_prompt(
    stock_code: str,
    stock_name: str,
    as_of_date: str,
    market_data: dict,
    priced_in_info: dict,
    seed_event_id: str = "",
) -> tuple[str, str]:
    """构建陌生股票冷启动 Prompt，要求绑定合法 L4 证据 ID 与明确证伪条件。"""
    SOP_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SOP_PATH.exists():
        SOP_PATH.write_text(SOP_COLD_START_MD, encoding="utf-8")

    system_prompt = (
        f"{_load_l0_rules()}\n\n"
        "你是资深A股量化基本面分析师。请基于截至基准日的新闻与 L3 量价指标构建初始 L2Graph：\n"
        "1) 严格区分 close_rank_pct_60d（60日收盘价真实经验分位数 count(P_i<=P_t)/N）与 range_pos_60d（60日高低点区间位置）；\n"
        "2) net_sentiment_score 是区间 [-2.0, +2.0] 的多空逻辑净势能指数，严禁将其表述为上涨概率；\n"
        f"3) 所有 ACTIVE 节点的 evidence_pointers 必须引用合法 L4 证据 ID（如 ['{seed_event_id}']），且必须填写具体可证伪的 invalidation_condition。\n"
        "请直接输出包含 stock_code, stock_name, last_updated, market_regime, thesis_nodes, edges 的紧凑纯 JSON 对象。"
    )
    user_prompt = (
        f"【冷启动目标】股票代码: {stock_code} | 股票名称: {stock_name} | 基准日(as_of_date): {as_of_date} | 初始归档证据ID: {seed_event_id}\n"
        f"【L3 量价位置与预期兑现诊断】:\n{json.dumps(priced_in_info, ensure_ascii=False)}\n"
        f"【截至 {as_of_date} 的近 15 条新闻/事件】:\n{json.dumps(market_data.get('news', [])[:15], ensure_ascii=False)}\n"
        "请直接输出符合 L2Graph Schema 的纯 JSON 对象。"
    )
    return system_prompt, user_prompt


def build_belief_revision_prompt(
    l2_graph: L2Graph,
    priced_in_info: dict,
    new_event: dict,
    as_of_date: str,
    event_id: str = "",
    contagion_paths: Optional[list[dict]] = None,
    event_polarity: int = 0,
    enable_invalidation: bool = True,
    enable_priced_in: bool = True,
) -> tuple[str, str]:
    """构建图谱记忆方法（Ours 及消融变体）的推演 Prompt，使用统一任务要求与 InferenceResponse 输出契约。"""
    paths_json = json.dumps(contagion_paths or [], ensure_ascii=False)
    ablation_constraints: list[str] = []
    if not enable_invalidation:
        ablation_constraints.append("【当前消融约束 (w/o Invalidation)】禁止使用 INVALIDATE 操作作废已有节点，仅允许 CONFIRM 或 ADD_NODE。")
    if not enable_priced_in:
        ablation_constraints.append("【当前消融约束 (w/o Priced-in)】忽略前期涨幅与 priced_in_ratio 折算，禁止使用 PRICED_IN 操作。")
    constraint_block = ("\n" + "\n".join(ablation_constraints)) if ablation_constraints else ""

    candidate_ids = [
        {"id": n.id, "type": n.type, "title": n.title}
        for n in l2_graph.thesis_nodes
    ]
    polarity_desc = "+1(正面/利好)" if event_polarity > 0 else ("-1(负面/利空)" if event_polarity < 0 else "0(中性/待定)")
    system_prompt = (
        f"{_load_l0_rules()}\n\n"
        "你是金融事件投资论点推演引擎。请基于截至当时的历史记忆、市场量价指标与最新事件，一次性输出单事件结构化分析、论点更新操作（patch_ops）与多周期方向判断：\n"
        "1) 金融指标规范：close_rank_pct_60d 代表收盘价在过去60日的真实经验分位数 count(P_i<=P_t)/N，range_pos_60d 代表60日高低点区间位置；net_sentiment_score 为 [-2.0, +2.0] 的多空净势能指数，非上涨概率。\n"
        f"2) 严格证据闭环：每个 PatchOp 必须设置 evidence_id='{event_id}'；任何新增 ACTIVE 节点必须包含 evidence_pointers=['{event_id}'] 且填写具体的 invalidation_condition。\n"
        "3) 状态转移与方向判定准则：\n"
        "   - 【逻辑反转 (INVALIDATE)】：若最新事件证伪已有论点（如客户砍单、核心机柜推迟交付），对该 target_node_id 输出 INVALIDATE，且 t1_forecast 与 t5_forecast 判定为 BEARISH（或反向对应方向）；\n"
        "   - 【利好出尽 (PRICED_IN Trap)】：若字面利好（event_polarity=+1，如业绩预增符合预期上限）但前期已大幅上涨、预期高度透支（priced_in_ratio >= 0.85），必须对核心多头节点输出 PRICED_IN（严禁 CONFIRM 或新增多头节点），且因高位获利盘集中兑现回吐（Sell-the-news），t1_forecast 与 t5_forecast 必须判定为 BEARISH；\n"
        "   - 【跨公司负向传导 (Negative Contagion)】：当 contagion_paths 非空且 path_factor < 0（transmission_sign == '-1'，如上游晶圆停产检修导致光芯片紧缺、下游光模块厂面临物料配额收紧）时，必须输出 ADD_NODE(BEARISH_LOGIC) 或 INVALIDATE（严禁在此负向供应链冲击下 CONFIRM 既有节点），impact_direction 设为 'negative'，且 t1_forecast 与 t5_forecast 必须判定为 BEARISH。\n"
        "4) 内部一致性要求：event_summary / impact_direction 必须与 patch_ops 及 t1/t5_forecast 逻辑自洽。\n"
        "5) 输出长度硬预算：只输出紧凑 JSON；每条 reason/reasoning 不超过 80 个汉字；patch_ops 最多 3 条；watch_indicators 最多 3 条。"
        f"{constraint_block}\n\n"
        f"{UNIFIED_OUTPUT_SCHEMA_DOC}"
    )
    regime_payload = priced_in_info if enable_priced_in else {
        k: v for k, v in priced_in_info.items() if k not in ("priced_in_ratio", "priced_in_desc")
    }
    user_prompt = (
        f"【推演基准日 (as_of_date)】: {as_of_date} | 【当前事件唯一证据ID】: {event_id}\n"
        f"【标的】: {l2_graph.stock_code} ({l2_graph.stock_name})\n"
        f"【候选目标论点 ID 清单 (candidate_thesis_ids)】:\n{json.dumps(candidate_ids, ensure_ascii=False)}\n"
        f"【当前 L2 论点图谱完整状态】:\n{l2_graph.model_dump_json()}\n"
        f"【市场量价指标 (market_regime)】:\n{json.dumps(regime_payload, ensure_ascii=False)}\n"
        f"【产业链传导路径 (contagion_paths | 当前事件极性 event_polarity={polarity_desc}，路径 transmission_sign 与 path_factor 已按事件极性折算)】:\n{paths_json}\n"
        f"【最新事件 (latest_event)】:\n{json.dumps(new_event, ensure_ascii=False)}\n"
        "请直接输出符合 InferenceResponse 契约的紧凑纯 JSON 对象（每条 reason/reasoning ≤80字，patch_ops ≤3条，watch_indicators ≤3条）。"
    )
    return system_prompt, user_prompt


def build_baseline_llm_prompt(
    method_tag: str,
    stock_code: str,
    stock_name: str,
    as_of_date: str,
    event_id: str,
    candidate_theses: list[dict[str, Any]],
    retrieved_or_full_docs: list[str],
    market_regime: dict[str, Any],
    new_event: dict[str, Any],
    supply_chain_text_prior: Optional[list[str]] = None,
) -> tuple[str, str]:
    """构建 B1（长上下文）与 B2（词法检索 Top-K + LLM）的公平对比 Prompt。"""
    minimal_candidates = [
        {"id": t["id"], "type": t["type"], "title": t["title"]}
        for t in candidate_theses
    ]
    system_prompt = (
        "你是金融事件投资论点推演引擎。请基于提供的历史文本材料、市场量价指标、候选目标论点清单与最新事件，输出结构化事件分析、论点更新操作与多周期方向判断：\n"
        f"1) 严格证据闭环：每个 PatchOp 必须设置 evidence_id='{event_id}'；若操作针对候选目标论点清单中的条目，请填写对应的 target_node_id（如 'TH_01'）。\n"
        "2) 操作类型：CONFIRM（印证既有论点）、INVALIDATE（证伪既有论点）、PRICED_IN（利好/利空预期已充分反映）、ADD_NODE（新增论点）。\n"
        "3) 输出长度硬预算：只输出紧凑 JSON；每条 reason/reasoning 不超过 80 个汉字；patch_ops 最多 3 条；watch_indicators 最多 3 条。\n\n"
        f"{UNIFIED_OUTPUT_SCHEMA_DOC}"
    )
    prior_section = (
        f"【同源产业链文本先验 (supply_chain_text_prior)】:\n{json.dumps(supply_chain_text_prior, ensure_ascii=False)}\n"
        if supply_chain_text_prior
        else ""
    )
    user_prompt = (
        f"【方法标识】: {method_tag}\n"
        f"【推演基准日 (as_of_date)】: {as_of_date} | 【当前事件唯一证据ID】: {event_id}\n"
        f"【标的】: {stock_code} ({stock_name})\n"
        f"【候选目标论点 ID 清单 (candidate_thesis_ids，仅含ID与标题)】:\n{json.dumps(minimal_candidates, ensure_ascii=False)}\n"
        f"【市场量价指标 (market_regime)】:\n{json.dumps(market_regime, ensure_ascii=False)}\n"
        f"{prior_section}"
        f"【截至 {as_of_date} 的历史文本材料 ({len(retrieved_or_full_docs)} 条)】:\n"
        + "\n".join(f"- {doc}" for doc in retrieved_or_full_docs)
        + f"\n【最新事件 (latest_event)】:\n{json.dumps(new_event, ensure_ascii=False)}\n"
        "请直接输出符合 InferenceResponse 契约的紧凑纯 JSON 对象。"
    )
    return system_prompt, user_prompt
