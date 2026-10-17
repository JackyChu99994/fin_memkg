from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Optional
from schema import L2Graph

BASE_DIR = Path(__file__).resolve().parent
L0_PATH = BASE_DIR / "memory/L0_meta_rules.md"
SOP_PATH = BASE_DIR / "memory/L3_skills/sop_cold_start.md"
INPUT_SCHEMA_VERSION = "v3_unified_fair_llm"
DEMO_PROMPT_VERSION = "demo_prompt_v1"
DEMO_SCHEMA_VERSION = "demo_schema_v1"

SOP_COLD_START_MD = """# L3 Skill SOP: 陌生个股 10 秒冷启动建图 (Cold-Start Graph Initialization)
1. **触发条件**：当查询标的未命中 `memory/L2_graphs/{stock_code}.json` 时自动触发。
2. **输入隔离**：严格使用 `published_at <= as_of_date` 的近 15 条新闻与 60 日量价指标（`close_rank_pct_60d` 经验分位与 `range_pos_60d` 区间位置），严禁前视偏差。
3. **证据闭环**：提取 2~4 个多空 `ThesisNode`（每个 `ACTIVE` 节点必须绑定合法的 L4 `EV_YYYYMMDD_...` 证据指针与明确的 `invalidation_condition`）及传导边 `Edge`。
"""

UNIFIED_OUTPUT_SCHEMA_DOC = """请严格输出符合以下契约的纯 JSON 对象（InferenceResponse）：
{
  "patch_ops": [
    {
      "op": "CONFIRM" | "INVALIDATE" | "PRICED_IN" | "ADD_NODE",
      "target_node_id": "若操作针对已有候选论点则填写其ID（如 'TH_01'），若为 ADD_NODE 则为 null",
      "reason": "状态更新或新增节点的具体依据",
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
        "invalidation_condition": "具体可验证的证伪条件"
      }
    }
  ],
  "contagion_impact": "跨公司/产业链传导影响分析（无则填 null）",
  "t1_forecast": {"direction": "BULLISH" | "NEUTRAL" | "BEARISH", "confidence": 0.80, "reasoning": "T+1 推演依据"},
  "t5_forecast": {"direction": "BULLISH" | "NEUTRAL" | "BEARISH", "confidence": 0.80, "reasoning": "T+5 推演依据"},
  "t20_forecast": {"direction": "BULLISH" | "NEUTRAL" | "BEARISH", "confidence": 0.75, "reasoning": "T+20 推演依据"},
  "watch_indicators": ["后续观察指标1", "后续观察指标2"]
}"""


def _load_l0_rules() -> str:
    return L0_PATH.read_text(encoding="utf-8").strip() if L0_PATH.exists() else ""


DEMO_PROMPT_VERSION = "qwen_demo_prompt_v1"
DEMO_SCHEMA_VERSION = "qwen_demo_schema_v1"


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
        "只输出一个合法的 JSON 对象，不输出 Markdown 代码块标记，不输出任何解释文字。\n"
        "JSON 格式如下：\n"
        "{\n"
        '  "event_summary": "事件摘要",\n'
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
        '    "支持判断的原文证据"\n'
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
        "请直接输出包含 stock_code, stock_name, last_updated, market_regime, thesis_nodes, edges 的纯 JSON 对象。"
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
    system_prompt = (
        f"{_load_l0_rules()}\n\n"
        "你是金融事件投资论点推演引擎。请基于截至当时的历史记忆、市场量价指标与最新事件，输出结构化论点更新操作与多周期方向判断：\n"
        "1) 金融指标规范：close_rank_pct_60d 代表收盘价在过去60日的真实经验分位数 count(P_i<=P_t)/N，range_pos_60d 代表60日高低点区间位置；net_sentiment_score 为 [-2.0, +2.0] 的多空净势能指数，非上涨概率。\n"
        f"2) 严格证据闭环：每个 PatchOp 必须设置 evidence_id='{event_id}'；任何新增 ACTIVE 节点必须包含 evidence_pointers=['{event_id}'] 且填写具体的 invalidation_condition。\n"
        "3) 状态转移准则：若最新事件证伪已有论点则对该 target_node_id 输出 INVALIDATE；若字面利好但前期已大幅上涨、预期高度透支（priced_in_ratio 处于高位）则对目标节点输出 PRICED_IN；若印证强化则输出 CONFIRM；若存在跨公司传导或新逻辑则输出 ADD_NODE。"
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
        f"【产业链传导路径 (contagion_paths)】:\n{paths_json}\n"
        f"【最新事件 (latest_event)】:\n{json.dumps(new_event, ensure_ascii=False)}\n"
        "请直接输出符合 InferenceResponse 契约的纯 JSON 对象。"
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
        "你是金融事件投资论点推演引擎。请基于提供的历史文本材料、市场量价指标、候选目标论点清单与最新事件，输出结构化论点更新操作与多周期方向判断：\n"
        f"1) 严格证据闭环：每个 PatchOp 必须设置 evidence_id='{event_id}'；若操作针对候选目标论点清单中的条目，请填写对应的 target_node_id（如 'TH_01'）。\n"
        "2) 操作类型：CONFIRM（印证既有论点）、INVALIDATE（证伪既有论点）、PRICED_IN（利好/利空预期已充分反映）、ADD_NODE（新增论点）。\n\n"
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
        "请直接输出符合 InferenceResponse 契约的纯 JSON 对象。"
    )
    return system_prompt, user_prompt
