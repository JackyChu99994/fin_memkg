# -*- coding: utf-8 -*-
"""Demo 数据：一条“宁德时代”主线 + 三个可复现的场景。

所有 Demo 事件都真的写进 L4（news.jsonl），所以图上的每条边都能点开看原文，
满足 L0-2「无证据不入图」——这一点答辩时最好现场演示一次。
"""
from __future__ import annotations

import l4_archive as l4

DEMO_EVENTS = [
    # (source, source_type, source_code, rel, target, target_type, target_code, status, conf, date, reason, text)
    ("宁德时代", "公司", "300750", "利好事件", "特斯拉", "公司", "", "发酵中", 0.88, "2026-10-16",
     "签订新电池供应合同，明年出货量预计增长30%",
     "宁德时代宣布与特斯拉签订新的电池供应合同，预计明年出货量将增长30%。"),
    ("宁德时代", "公司", "300750", "利好事件", "上海时代宸远创业投资合伙企业", "公司", "", "发酵中", 0.72, "2026-10-13",
     "认缴出资4亿元，持有基金26.64%份额",
     "宁德时代公告称，公司作为有限合伙人参与投资上海时代宸远创业投资合伙企业，认缴出资4亿元，持有基金26.64%的认缴比例。"),
    ("宁德时代", "公司", "300750", "利好事件", "储能电池", "产品", "", "已兑现", 0.70, "2026-09-20",
     "储能出货超预期，海外大储订单落地",
     "宁德时代储能电池三季度出货超预期，海外大储订单集中落地。"),
    ("天齐锂业", "公司", "002466", "供应商", "宁德时代", "公司", "300750", "已兑现", 0.90, "2026-08-15",
     "锂盐长协供应",
     "天齐锂业与宁德时代签订锂盐长期供货协议。"),
    ("天齐锂业", "公司", "002466", "属于行业", "锂矿", "行业", "", "已兑现", 0.95, "2026-08-15",
     "上游锂资源",
     "天齐锂业主营锂精矿开采与锂盐加工。"),
    ("宁德时代", "公司", "300750", "属于行业", "动力电池", "行业", "", "已兑现", 0.95, "2026-08-15",
     "中游电池制造",
     "宁德时代主营动力电池与储能电池系统。"),
    ("宁德时代", "公司", "300750", "竞争对手", "比亚迪", "公司", "002594", "已兑现", 0.85, "2026-08-15",
     "动力电池外供市场直接竞争",
     "比亚迪刀片电池外供，与宁德时代在动力电池市场份额上直接竞争。"),
]

SCENARIOS = {
    "A": {
        "name": "A · 逻辑反转（新信息推翻旧逻辑）",
        "text": "突发：由于监管审查未通过，宁德时代宣布暂停对上海时代宸远创业投资合伙企业的4亿元投资计划。",
        "date": "2026-10-22",
        "stock_code": "300750",
        "expect": "旧“利好事件”被置为已被证伪，新增“利空事件”，图上出现灰色虚线 + 绿色新边",
    },
    "B": {
        "name": "B · 竞争替代（跨公司传导）",
        "text": "特斯拉证实将部分电池订单转给比亚迪，宁德时代对特斯拉的供货份额预计下降。",
        "date": "2026-10-22",
        "stock_code": "300750",
        "expect": "宁德时代→特斯拉 的利好被证伪，同时提示比亚迪的替代受益",
    },
    "C": {
        "name": "C · 产业链传导（两跳推理）",
        "text": "碳酸锂期货主力合约涨停，锂矿供给持续收紧，现货价格单月上涨30%。",
        "date": "2026-10-21",
        "stock_code": "300750",
        "expect": "上游锂矿利好（天齐锂业）、下游电池成本承压（宁德时代），沿供应链两跳传导",
    },
}


def seed(store, reset: bool = True) -> dict:
    """重建演示图谱；重复执行不会重复写 L4（内容寻址去重）。"""
    if reset:
        store.reset_demo()

    for (src, stype, scode, rel, tgt, ttype, tcode, status, conf, date, reason, text) in DEMO_EVENTS:
        rec = l4.append_event(text=text, stock_code=scode or "000000", stock_name=src,
                              publish_date=date, source="demo_seed")
        store.upsert_event({
            "event_id": rec["event_id"], "source": src, "source_type": stype, "source_code": scode,
            "target": tgt, "target_type": ttype, "target_code": tcode,
            "relation": rel, "status": status, "confidence": conf, "date": date, "reason": reason,
        }, rec["ref"])

    return store.stats()


def ensure_seeded(store) -> None:
    if store.stats().get("edges", 0) == 0:
        seed(store)
