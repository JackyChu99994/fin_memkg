from __future__ import annotations
from pathlib import Path
from typing import Any, Literal, Optional
import networkx as nx
from pydantic import BaseModel, Field, model_validator

EvidenceType = Literal[
    "EMPIRICAL_NEWS_FILING",
    "PRICE_VOLUME_SUMMARY",
    "SUPPLY_CHAIN_TRANSMISSION",
    "COLD_START_PRIOR",
]


class MarketRegime(BaseModel):
    """量价状态契约：net_sentiment_score 为区间 [-2.0, +2.0] 的多空逻辑净势能指数（非上涨概率）。"""
    close_rank_pct_60d: float = Field(..., ge=0.0, le=1.0, description="当前收盘价在过去60日收盘价序列中的真实经验分位数 count(P_i <= P_t)/N")
    range_pos_60d: float = Field(..., ge=0.0, le=1.0, description="60日高低点区间位置 (P_t - min(P_60)) / (max(P_60) - min(P_60))")
    return_20d_pct: float
    turnover_anomaly: Literal["LOW", "NORMAL", "HIGH"]
    net_sentiment_score: float = Field(..., ge=-2.0, le=2.0, description="区间[-2.0, +2.0]的多空逻辑净势能指数，非上涨概率")

    @model_validator(mode="before")
    @classmethod
    def _compat_legacy_percentile(cls, data: Any) -> Any:
        if isinstance(data, dict) and "price_percentile_60d" in data:
            p = float(data["price_percentile_60d"])
            data = dict(data)
            data.setdefault("close_rank_pct_60d", p)
            data.setdefault("range_pos_60d", p)
        return data

    @property
    def price_percentile_60d(self) -> float:
        return self.close_rank_pct_60d


class ThesisNode(BaseModel):
    id: str
    type: Literal["BULLISH_LOGIC", "BEARISH_LOGIC"]
    title: str
    category: str
    status: Literal["ACTIVE", "PRICED_IN", "INVALIDATED"]
    weight: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    created_at: str
    updated_at: str
    priced_in_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    status_reason: Optional[str] = None
    superseded_by: Optional[str] = None
    evidence_pointers: list[str] = Field(default_factory=list)
    invalidation_condition: Optional[str] = None

    @model_validator(mode="after")
    def _check_active_constraints(self) -> "ThesisNode":
        if self.status == "ACTIVE":
            if not self.evidence_pointers or any(not p.strip() for p in self.evidence_pointers):
                raise ValueError(f"ACTIVE 节点 [{self.id}] 必须包含非空的 evidence_pointers")
            if not self.invalidation_condition or not self.invalidation_condition.strip():
                raise ValueError(f"ACTIVE 节点 [{self.id}] 必须包含非空的 invalidation_condition")
        return self

    def snapshot_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "weight": self.weight,
            "confidence": self.confidence,
            "priced_in_ratio": self.priced_in_ratio,
            "updated_at": self.updated_at,
            "status_reason": self.status_reason,
            "superseded_by": self.superseded_by,
            "evidence_pointers": list(self.evidence_pointers),
            "invalidation_condition": self.invalidation_condition,
        }

    def restore_from_snapshot(self, snap: dict[str, Any]) -> None:
        for field_name in (
            "status", "weight", "confidence", "priced_in_ratio",
            "updated_at", "status_reason", "superseded_by", "invalidation_condition",
        ):
            if field_name in snap:
                setattr(self, field_name, snap[field_name])
        if "evidence_pointers" in snap and snap["evidence_pointers"] is not None:
            self.evidence_pointers = list(snap["evidence_pointers"])

    def node_score(self, alpha: float = 0.8) -> float:
        if self.status != "ACTIVE":
            return 0.0
        polarity = 1.0 if self.type == "BULLISH_LOGIC" else -1.0
        return round(polarity * self.weight * self.confidence * (1.0 - alpha * self.priced_in_ratio), 4)


class Edge(BaseModel):
    source: str
    target: str
    relation: Literal["CONFIRM", "INVALIDATES", "UPSTREAM_DRIVES", "COMPETES_WITH"]
    hop: int = Field(default=1, ge=1, le=2)
    transmission_sign: Literal["+1", "-1"] = "+1"
    created_at: str = "2026-08-20"
    description: str = ""


class StateHistoryEntry(BaseModel):
    as_of_date: str
    op: str
    node_id: str
    prev_status: Optional[str] = None
    new_status: str
    prev_weight: Optional[float] = None
    new_weight: Optional[float] = None
    evidence_id: Optional[str] = None
    node_before_full: Optional[dict[str, Any]] = None


class L2Graph(BaseModel):
    stock_code: str
    stock_name: str
    last_updated: str
    market_regime: MarketRegime
    thesis_nodes: list[ThesisNode]
    edges: list[Edge] = Field(default_factory=list)
    history_log: list[dict[str, Any]] = Field(default_factory=list)
    baseline_snapshot: dict[str, Any] = Field(default_factory=dict)
    is_historical_view: bool = Field(default=False, exclude=True)

    def compute_net_score(self, alpha: float = 0.8, lambda_decay: float = 0.6, use_edges: bool = True) -> float:
        node_map = {n.id: n for n in self.thesis_nodes}
        base_scores = {n.id: n.node_score(alpha) for n in self.thesis_nodes}
        eff_scores = dict(base_scores)

        if use_edges and self.edges:
            g = nx.DiGraph()
            for n_id in node_map:
                g.add_node(n_id)
            for e in self.edges:
                if e.source in node_map and e.target in node_map:
                    g.add_edge(e.source, e.target, relation=e.relation, hop=e.hop, sign=e.transmission_sign)

            invalidated_targets: set[str] = set()
            for u, v, d in g.edges(data=True):
                if d.get("relation") == "INVALIDATES" and node_map[u].status == "ACTIVE":
                    eff_scores[v] = 0.0
                    invalidated_targets.add(v)

            for u, v, d in g.edges(data=True):
                rel = d.get("relation")
                if rel in ("CONFIRM", "UPSTREAM_DRIVES", "COMPETES_WITH"):
                    if node_map[u].status == "ACTIVE" and u not in invalidated_targets and node_map[v].status == "ACTIVE" and v not in invalidated_targets:
                        sigma = 1.0 if d.get("sign", "+1") == "+1" else -1.0
                        gamma = 0.5
                        hop = max(1, min(2, int(d.get("hop", 1))))
                        if rel == "COMPETES_WITH":
                            v_pol = 1.0 if node_map[v].type == "BULLISH_LOGIC" else -1.0
                            attenuation = gamma * (lambda_decay ** (hop - 1)) * abs(base_scores[u])
                            new_mag = max(0.0, abs(eff_scores[v]) - attenuation)
                            eff_scores[v] = round(v_pol * new_mag, 4)
                        else:
                            contagion = sigma * gamma * (lambda_decay ** (hop - 1)) * base_scores[u]
                            eff_scores[v] = round(eff_scores[v] + contagion, 4)

        raw_total = sum(eff_scores.values())
        clamped = round(max(-2.0, min(2.0, raw_total)), 4)
        self.market_regime.net_sentiment_score = clamped
        return clamped


class PatchOp(BaseModel):
    op: Literal["CONFIRM", "INVALIDATE", "PRICED_IN", "ADD_NODE"]
    target_node_id: Optional[str] = None
    reason: str
    new_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    new_node: Optional[ThesisNode] = None
    new_edge: Optional[Edge] = None
    evidence_id: Optional[str] = None
    published_at: Optional[str] = None


class ExecutionMeta(BaseModel):
    storage_read_mode: Literal["LIVE_FETCH", "DISK_CACHE", "IN_MEMORY"]
    underlying_data_origin: Literal["REAL_MARKET_API", "CURATED_REAL_ARCHIVE", "SYNTHETIC_SIMULATION"]
    inference_mode: Literal["LLM_API", "RESPONSE_CACHE_HIT"] = "LLM_API"
    call_origin: Literal["LIVE_API_CALL", "RESPONSE_CACHE_HIT"] = "LIVE_API_CALL"
    model_name: str
    base_url: Optional[str] = None
    token_count_type: Literal["EXACT_API_USAGE", "MISSING_OR_ESTIMATED"]
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    cached_tokens: Optional[int] = None
    estimated_tokens: Optional[int] = None
    request_hash: Optional[str] = None
    fallback_reason: Optional[str] = None

    @property
    def market_data_source(self) -> str:
        return f"{self.storage_read_mode}:{self.underlying_data_origin}"


class HorizonPred(BaseModel):
    direction: Literal["BULLISH", "NEUTRAL", "BEARISH"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str


class InferenceResponse(BaseModel):
    patch_ops: list[PatchOp] = Field(default_factory=list)
    contagion_impact: Optional[str] = None
    t1_forecast: HorizonPred
    t5_forecast: HorizonPred
    t20_forecast: HorizonPred
    watch_indicators: list[str] = Field(default_factory=list)
    execution_meta: Optional[ExecutionMeta] = None


class DemoEntity(BaseModel):
    name: str
    type: str = "其他"


class DemoEventAnalysis(BaseModel):
    """第一版 Qwen Demo 结构化事件分析输出 Schema。"""
    event_summary: str
    entities: list[DemoEntity] = Field(default_factory=list)
    event_type: str
    impact_direction: Literal["positive", "negative", "neutral"]
    risk_level: Literal["low", "medium", "high"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        raw_ents = out.get("entities", [])
        norm_ents: list[dict[str, str]] = []
        if isinstance(raw_ents, list):
            for item in raw_ents:
                if isinstance(item, str):
                    norm_ents.append({"name": item, "type": "实体"})
                elif isinstance(item, dict) and item.get("name"):
                    norm_ents.append({"name": str(item["name"]), "type": str(item.get("type", "其他"))})
        out["entities"] = norm_ents

        raw_dir = str(out.get("impact_direction", "neutral")).strip().lower()
        dir_map = {"bullish": "positive", "positive": "positive", "bearish": "negative", "negative": "negative", "neutral": "neutral"}
        out["impact_direction"] = dir_map.get(raw_dir, raw_dir)

        raw_risk = str(out.get("risk_level", "medium")).strip().lower()
        out["risk_level"] = raw_risk
        return out
