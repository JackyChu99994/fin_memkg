# -*- coding: utf-8 -*-
"""L0：元规则（Meta Rules）与输出契约。

设计要点：L0 不只是 Prompt 里的一段文字，它同时被 config.py 的白名单
在“写库前”强制执行 —— Prompt 是第一道闸，代码是第二道闸。
"""
from config import ENTITY_TYPES, REL_TYPES, STATUSES

META_RULES = [
    {
        "id": "L0-1",
        "name": "时间戳隔离（Temporal Isolation）",
        "text": "所有实体、关系、行情特征只能使用 <= 事件日 as_of 的信息，"
                "严禁引入未来函数；关系的 date 必须是新闻发布日，不是抓取日。",
    },
    {
        "id": "L0-2",
        "name": "无证据不入图（Verification Before Ingestion）",
        "text": "每条关系必须绑定一个可回溯的 L4 证据指针 archive_ref；"
                "没有原文指针的关系不得写入 L2。",
    },
    {
        "id": "L0-3",
        "name": "按需展开（On-Demand Expansion）",
        "text": "常驻上下文只放 L0 规则 + L1 概念索引 + 命中的少数标的，"
                "不得把全市场股票或整本 L2 图谱塞进 Prompt。",
    },
    {
        "id": "L0-4",
        "name": "本体约束（Ontology Constraints）",
        "text": f"实体类型只能是 {ENTITY_TYPES}；关系类型只能是 {REL_TYPES}；"
                "数字（百分比、金额、股价）只能作为属性，禁止抽成独立节点。",
    },
    {
        "id": "L0-5",
        "name": "噪音过滤（Noise Rejection）",
        "text": "与股价、产业链、财务、监管、供需无关的新闻（商标注册、人事任免、"
                "纯行情快照、广告导流）直接返回空列表，不得产出三元组。",
    },
    {
        "id": "L0-6",
        "name": "状态机（Thesis State Machine）",
        "text": f"关系状态只能是 {STATUSES}。新事件若与旧逻辑方向相反，"
                "必须把旧关系置为“已被证伪”并记录 invalidated_by，而不是删除它。",
    },
]

L0_BLOCK = "\n".join(f"[{r['id']}] {r['name']}：{r['text']}" for r in META_RULES)

OUTPUT_CONTRACT = """只输出一个 JSON 对象，不要 markdown 代码围栏，不要解释：
{
  "events": [
    {
      "source": "宁德时代",
      "source_code": "300750",
      "relation": "利好事件",
      "target": "特斯拉",
      "target_code": "",
      "target_type": "公司",
      "status": "发酵中",
      "confidence": 0.86,
      "date": "2026-10-21",
      "reason": "签订新电池供应合同，出货量预计增长30%",
      "amount": "30%",
      "invalidates": []
    }
  ]
}
字段说明：
- relation ∈ {利好事件, 利空事件, 供应商, 客户, 竞争对手, 属于行业}
- target_type ∈ {公司, 行业, 产品, 事件}
- reason <= 40 字，必须来自原文，不得编造
- invalidates: 若本条新闻推翻了某条旧逻辑，填旧关系的 event_id（可为空列表）
- 若新闻与市场无关，输出 {"events": []}
"""

EXTRACT_SYSTEM = """你是金融知识图谱抽取器，服从 L0 元规则，输出严格 JSON。
你只抽“会改变投资逻辑”的事实，不抽数字节点，不抽情绪形容词。"""


def render_l0_block() -> str:
    return "【L0 元规则（必须遵守）】\n" + L0_BLOCK
