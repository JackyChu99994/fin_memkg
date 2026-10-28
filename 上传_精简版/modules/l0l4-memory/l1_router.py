# -*- coding: utf-8 -*-
"""L1：概念路由（Concept Routing）—— 把“全市场”收缩成“3~5 只候选标的”。

它解决的是 Prompt 成本问题：
    朴素做法：[全部 14 只标的 + 各自产业链描述] + 新闻  -> 每次 ~1200 token
    L1 路由后：[命中的 3~5 只标的] + 新闻               -> 每次 ~300 token

匹配是确定性的（词典 + 最长别名优先），不调用任何模型，
因此 L1 本身是 0 token 的，可以放心放在在线链路上。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from config import L1_INDEX_PATH


@dataclass
class Stock:
    code: str
    name: str
    chain: str
    role: str
    cluster_id: str
    cluster_name: str
    matched_by: str = ""  # 命中的别名 / 代码 / 名称

    def line(self) -> str:
        return f"- {self.code} {self.name}（{self.chain}）：{self.role}"


@dataclass
class RoutingDecision:
    text: str
    clusters: list[dict] = field(default_factory=list)
    stocks: list[Stock] = field(default_factory=list)
    named: list[Stock] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    prompt_block: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.stocks)

    def explain(self) -> str:
        if not self.ok:
            return "⚠️ L1 未命中任何概念簇：本条新闻可能需要人工指定标的，或扩充 L1 词典。"
        hit = "、".join(f"{c['name']}({c['score']:.0f})" for c in self.clusters)
        codes = "、".join(f"{s.name}" for s in self.stocks)
        return f"L1 命中概念：{hit}\n路由标的（{len(self.stocks)} 只）：{codes}" + (
            "\n点名标的：" + "、".join(s.name for s in self.named) if self.named else ""
        )


@lru_cache(maxsize=8)
def _load_index(path: str, mtime: float) -> dict:
    from pathlib import Path

    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_index(path=L1_INDEX_PATH) -> dict:
    p = str(path)
    try:
        import os

        mtime = os.path.getmtime(p)
    except OSError:
        mtime = 0.0
    return _load_index(p, mtime)


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _estimate_tokens(chars: int) -> int:
    """中文场景的粗估：1 token ≈ 1.5 个汉字（DeepSeek 分词器实测区间 1.3~1.7）。"""
    return max(1, int(round(chars / 1.5)))


def universe_block(index: Optional[dict] = None) -> str:
    """对照基线：不分路由，把全部标的塞进 Prompt 的样子。"""
    idx = index or load_index()
    lines = []
    for c in idx["clusters"]:
        for s in c["stocks"]:
            lines.append(f"- {s['code']} {s['name']}（{s['chain']}）：{s['role']}")
    return "【全市场候选标的】\n" + "\n".join(lines)


def route(text: str, index: Optional[dict] = None, top_clusters: int = 2, max_stocks: int = 6) -> RoutingDecision:
    idx = index or load_index()
    norm = _norm(text)
    decision = RoutingDecision(text=text)

    named_codes: set[str] = set()
    scored: list[dict] = []

    for cluster in idx["clusters"]:
        score = 0.0
        hits: list[str] = []
        for alias in cluster.get("aliases", []):
            cnt = norm.count(alias.lower())
            if cnt:
                # 长别名权重更高：避免“电池”这种泛词压过“固态电池”
                score += cnt * (len(alias) + 2)
                hits.append(alias)
        for s in cluster.get("stocks", []):
            if s["code"] in norm or s["name"] in norm:
                score += 50
                named_codes.add(s["code"])
                hits.append(s["name"])
        if score > 0:
            scored.append({"id": cluster["id"], "name": cluster["name"], "score": score,
                           "hits": sorted(set(hits), key=len, reverse=True)})

    scored.sort(key=lambda x: x["score"], reverse=True)
    decision.clusters = scored[:top_clusters]

    seen: set[str] = set()
    for cluster in idx["clusters"]:
        if cluster["id"] not in {c["id"] for c in decision.clusters}:
            continue
        for s in cluster["stocks"]:
            if len(decision.stocks) >= max_stocks:
                break
            if s["code"] in seen:
                continue
            by = "名称" if s["name"] in norm else ("代码" if s["code"] in norm else "")
            if not by:
                hit = next((a for a in cluster.get("aliases", []) if a.lower() in norm), "")
                by = f"概念:{hit}" if hit else "同簇"
            stock = Stock(s["code"], s["name"], s["chain"], s["role"],
                          cluster["id"], cluster["name"], by)
            decision.stocks.append(stock)
            seen.add(s["code"])
            if by in ("名称", "代码"):
                decision.named.append(stock)

    # 点名标的优先排在前面
    decision.stocks.sort(key=lambda s: s.matched_by not in ("名称", "代码"))

    total = sum(len(c["stocks"]) for c in idx["clusters"])
    full_chars = len(universe_block(idx))
    routed_chars = len(build_prompt_block(decision)) if decision.stocks else 0
    decision.prompt_block = build_prompt_block(decision) if decision.stocks else ""
    decision.stats = {
        "universe": total,
        "kept": len(decision.stocks),
        "ratio": round(len(decision.stocks) / total, 3) if total else 0.0,
        "full_tokens_est": _estimate_tokens(full_chars),
        "routed_tokens_est": _estimate_tokens(routed_chars),
        "saved_tokens_est": _estimate_tokens(full_chars) - _estimate_tokens(routed_chars),
        "saved_pct": round(1 - routed_chars / full_chars, 3) if full_chars and routed_chars else 0.0,
    }
    return decision


def build_prompt_block(decision: RoutingDecision) -> str:
    if not decision.stocks:
        return ""
    lines = [
        "【L1 路由结果：本批候选标的（仅限以下公司，禁止出现名单外的公司名）】",
        *[s.line() for s in decision.stocks],
    ]
    if decision.clusters:
        lines.append("【相关产业链概念】" + "、".join(c["name"] for c in decision.clusters))
    lines.append("【规则】若新闻主体不在候选名单内，按“行业/概念”维度抽取，target_type 用“行业”。")
    return "\n".join(lines)


if __name__ == "__main__":
    samples = [
        "今日锂矿拍卖价大涨，碳酸锂期货主力合约涨停，盐湖提锂板块集体走强。",
        "宁德时代宣布与特斯拉签订新的电池供应合同，预计明年出货量增长30%。",
        "宁德时代成功注册一枚“宁的易购”商标，国际分类为37类建筑修理。",
        "英伟达 GB200 放量，800G 光模块需求超预期，北美云厂商上调资本开支。",
    ]
    for s in samples:
        d = route(s)
        print("=" * 70)
        print("新闻：", s)
        print(d.explain())
        print("统计：", d.stats)
