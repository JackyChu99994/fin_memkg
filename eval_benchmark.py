"""Fin-MemKG 真实大模型同底座公平评测与正交消融流水线（严格禁止无Key规则降级，独立 run_id 审计归档）。"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent_loop import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
    _call_llm_json,
    check_llm_connectivity,
    resolve_llm_config,
    run_agent_pipeline,
)
from prompts import INPUT_SCHEMA_VERSION, build_baseline_llm_prompt
from schema import Edge, InferenceResponse, L2Graph, MarketRegime, ThesisNode
from tools import L4_DIR, SECTOR_CHAINS_PATH

BENCHMARK_PATH = L4_DIR / "fin_event_30.json"
REAL_EVENTS_PATH = L4_DIR / "real_fin_events_12.json"
RESULTS_PATH = L4_DIR / "benchmark_results.json"
RUNS_DIR = L4_DIR / "runs"

LEXICAL_TOP_K = 3
MAX_CONTEXT_CHARS = 12000

CORE_METHODS = [
    "B1: Long-History Context + LLM (Full-Text)",
    "B2: Lexical Top-K Retrieval + LLM (Char-Bigram Top-3)",
    "B2+Prior: Lexical Top-K + Supply-Chain Text Prior + LLM (Top-3)",
    "Ablation A: w/o Invalidation Only",
    "Ablation B: w/o Priced-in Only",
    "Ablation C1: w/o Supply-Chain Prior & KG Edges (Node-Only)",
    "Ablation C2: 1-Hop KG Only (cutoff=1)",
    "Ours: Fin-MemKG (Full: Revision + PricedIn + 2-Hop KG)",
]

KNOWLEDGE_DISCLOSURE = {
    "B1: Long-History Context + LLM (Full-Text)": {
        "historical_text": "All available historical chunks (deduplicated, char-capped at 12,000 chars)",
        "market_regime_indicators": True,
        "candidate_thesis_ids": "Minimal ID+Title list only (no weights/edges/priced_in state)",
        "supply_chain_prior": False,
        "l2_graph_structure": False,
    },
    "B2: Lexical Top-K Retrieval + LLM (Char-Bigram Top-3)": {
        "historical_text": f"Top-{LEXICAL_TOP_K} chunks by char-bigram cosine similarity",
        "market_regime_indicators": True,
        "candidate_thesis_ids": "Minimal ID+Title list only (no weights/edges/priced_in state)",
        "supply_chain_prior": False,
        "l2_graph_structure": False,
    },
    "B2+Prior: Lexical Top-K + Supply-Chain Text Prior + LLM (Top-3)": {
        "historical_text": f"Top-{LEXICAL_TOP_K} chunks by char-bigram cosine similarity",
        "market_regime_indicators": True,
        "candidate_thesis_ids": "Minimal ID+Title list only (no weights/edges/priced_in state)",
        "supply_chain_prior": "Flat text description of sector_chains.json edges",
        "l2_graph_structure": False,
    },
    "Ablation A: w/o Invalidation Only": {
        "historical_text": "Compressed into L2 ThesisGraph",
        "market_regime_indicators": True,
        "candidate_thesis_ids": "Full L2Graph nodes & edges (INVALIDATE disabled)",
        "supply_chain_prior": "2-Hop sector_chains.json DiGraph",
        "l2_graph_structure": True,
    },
    "Ablation B: w/o Priced-in Only": {
        "historical_text": "Compressed into L2 ThesisGraph",
        "market_regime_indicators": "Basic return/rank only (priced_in_ratio & PRICED_IN op disabled)",
        "candidate_thesis_ids": "Full L2Graph nodes & edges",
        "supply_chain_prior": "2-Hop sector_chains.json DiGraph",
        "l2_graph_structure": True,
    },
    "Ablation C1: w/o Supply-Chain Prior & KG Edges (Node-Only)": {
        "historical_text": "Compressed into L2 ThesisGraph",
        "market_regime_indicators": True,
        "candidate_thesis_ids": "L2Graph nodes only (edges & supply-chain graph disabled)",
        "supply_chain_prior": False,
        "l2_graph_structure": "Nodes only (max_hops=0, use_edges=False)",
    },
    "Ablation C2: 1-Hop KG Only (cutoff=1)": {
        "historical_text": "Compressed into L2 ThesisGraph",
        "market_regime_indicators": True,
        "candidate_thesis_ids": "Full L2Graph nodes & edges",
        "supply_chain_prior": "1-Hop sector_chains.json DiGraph (cutoff=1)",
        "l2_graph_structure": True,
    },
    "Ours: Fin-MemKG (Full: Revision + PricedIn + 2-Hop KG)": {
        "historical_text": "Compressed into L2 ThesisGraph",
        "market_regime_indicators": True,
        "candidate_thesis_ids": "Full L2Graph nodes & edges",
        "supply_chain_prior": "2-Hop sector_chains.json DiGraph (cutoff=2)",
        "l2_graph_structure": True,
    },
}

_FORBIDDEN_INPUT_KEYS = {
    "scenario",
    "ground_truth_t5",
    "ground_truth_t5_direction",
    "ground_truth_invalidated_id",
    "ground_truth_expected_op",
    "real_5d_return_pct",
    "bench_5d_return_pct",
    "car_5d_pct",
}


def _dedup_repeated_paragraph(text: str) -> str:
    """消除合成历史文档内部人为重复拼接的相同段落，保持原始单条文本真实长度。"""
    text = text.strip()
    if not text:
        return ""
    parts = re.split(r"(?=【(?:历史研报|近期机构风险跟踪))", text)
    seen: list[str] = []
    for p in parts:
        p_clean = p.strip()
        if p_clean and p_clean not in seen:
            seen.append(p_clean)
    return "".join(seen) if seen else text


def _strip_post_hoc_hints(text: str) -> str:
    """剥离事件标题或摘要中可能包含的事后解释括号或事后归因子句，确保严格盲测。"""
    cleaned = re.sub(r"（重大风险预警：[^）]+）", "", text)
    cleaned = re.sub(r"，利好落地后高位获利资金集中兑现。", "。", cleaned)
    cleaned = re.sub(r"，彻底(?:证伪|打破|扭转)[^。]+。", "。", cleaned)
    cleaned = re.sub(r"，直接逆转此前[^。]+。", "。", cleaned)
    return cleaned.strip()


def _normalize_case(raw: dict[str, Any]) -> dict[str, Any]:
    """统一读取测试集样例，提取真值仅供评测指标核对（绝不进入盲测输入）。"""
    scen = raw.get("scenario", "TEMPORAL_REVERSAL")
    if scen == "MULTI_HOP_CONTAGION":
        scen = "SECTOR_CONTAGION"
    theses = raw.get("prior_theses") or raw.get("prior_nodes") or []
    mr = raw.get("market_regime") or raw.get("market_stats") or {}
    if "prior_chunks" in raw:
        chunks = [_dedup_repeated_paragraph(str(c)) for c in raw["prior_chunks"]]
    else:
        chunks = [
            f"[{item.get('date', '')}] {_dedup_repeated_paragraph(str(item.get('text', '')))}"
            for item in raw.get("historical_stream", [])
        ]
    ev_raw = dict(raw.get("latest_event") or raw.get("new_event") or {})
    ev = {
        "event_id": ev_raw.get("event_id") or f"EV_{raw.get('as_of_date', '2026-09-15').replace('-', '')}_01_eval",
        "published_at": ev_raw.get("published_at") or f"{raw.get('as_of_date', '2026-09-15')} 09:00:00",
        "source": ev_raw.get("source", "财经快讯"),
        "title": _strip_post_hoc_hints(str(ev_raw.get("title", ""))),
        "content": _strip_post_hoc_hints(str(ev_raw.get("content") or ev_raw.get("snippet") or "")),
        "evidence_type": ev_raw.get("evidence_type", "EMPIRICAL_NEWS_FILING"),
    }

    gt_dir = raw.get("ground_truth_t5_direction") or raw.get("ground_truth_t5") or "BEARISH"
    gt_inv = raw.get("ground_truth_invalidated_id")
    if gt_inv is None and scen in ("PRICED_IN_TRAP", "SECTOR_CONTAGION") and theses:
        gt_sign = 1 if gt_dir == "BULLISH" else -1
        for t in theses:
            t_sign = 1 if t["type"] == "BULLISH_LOGIC" else -1
            if t_sign != gt_sign:
                gt_inv = t["id"]
                break

    return {
        "case_id": raw["case_id"],
        "scenario": scen,
        "stock_code": raw["stock_code"],
        "stock_name": raw["stock_name"],
        "as_of_date": raw["as_of_date"],
        "prior_theses": theses,
        "prior_chunks": chunks,
        "market_regime": {
            "return_20d_pct": float(mr.get("return_20d_pct", 0.0)),
            "close_rank_pct_60d": float(mr.get("close_rank_pct_60d", 0.5)),
            "range_pos_60d": float(mr.get("range_pos_60d", 0.5)),
            "priced_in_ratio": float(mr.get("priced_in_ratio", 0.25)),
            "turnover_anomaly": mr.get("turnover_anomaly", "NORMAL"),
        },
        "latest_event": ev,
        "ground_truth_t5_direction": gt_dir,
        "ground_truth_invalidated_id": gt_inv,
    }


def _make_blind_input(case: dict[str, Any]) -> dict[str, Any]:
    """构造严格盲测输入：剥离 scenario、所有 ground_truth_*、未来收益与事后解释。"""
    norm = _normalize_case(case)
    blind = {
        k: v
        for k, v in norm.items()
        if k not in _FORBIDDEN_INPUT_KEYS and not k.startswith("ground_truth_")
    }
    return blind


def assert_no_truth_leakage(blind_input: dict[str, Any], sys_prompt: str = "", usr_prompt: str = "") -> None:
    """运行前硬断言：确保输入字典及组装后的 Prompt 不含任何真值字段名或 scenario 标签。"""
    for k in blind_input:
        if k in _FORBIDDEN_INPUT_KEYS or k.startswith("ground_truth_"):
            raise AssertionError(f"检测到真值泄漏字段: {k}")
    combined = f"{sys_prompt}\n{usr_prompt}"
    for leak_token in ("ground_truth_", "real_5d_return_pct", "car_5d_pct", "TEMPORAL_REVERSAL", "PRICED_IN_TRAP", "SECTOR_CONTAGION", "MULTI_HOP_CONTAGION"):
        if leak_token in combined:
            raise AssertionError(f"Prompt 中检测到标签或真值泄漏: {leak_token}")


def build_fin_event_30() -> list[dict[str, Any]]:
    """只读加载 FinEvent-30 数据集（不覆写原始文件）。"""
    if not BENCHMARK_PATH.exists():
        raise FileNotFoundError(f"Missing {BENCHMARK_PATH}")
    return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))


def load_real_fin_events_12() -> list[dict[str, Any]]:
    """只读加载 RealFinEvent-12 数据集（不覆写原始文件）。"""
    if not REAL_EVENTS_PATH.exists():
        raise FileNotFoundError(f"Missing {REAL_EVENTS_PATH}")
    return json.loads(REAL_EVENTS_PATH.read_text(encoding="utf-8"))


def _char_tfidf_cosine(query: str, doc: str) -> float:
    q_grams = [query[i : i + 2] for i in range(max(1, len(query) - 1))]
    d_grams = [doc[i : i + 2] for i in range(max(1, len(doc) - 1))]
    vocab = set(q_grams) | set(d_grams)
    if not vocab:
        return 0.0
    v_q = [q_grams.count(w) for w in vocab]
    v_d = [d_grams.count(w) for w in vocab]
    norm = math.sqrt(sum(a * a for a in v_q)) * math.sqrt(sum(b * b for b in v_d))
    return sum(a * b for a, b in zip(v_q, v_d)) / norm if norm > 0 else 0.0


def _truncate_docs_reproducibly(docs: list[str], max_chars: int = MAX_CONTEXT_CHARS) -> tuple[list[str], dict[str, Any]]:
    """明确、可复现的截断策略：按时间顺序优先保留最新文档，直至达到字符上限 max_chars。"""
    kept_rev: list[str] = []
    used_chars = 0
    truncated = False
    for doc in reversed(docs):
        if used_chars + len(doc) > max_chars and kept_rev:
            truncated = True
            break
        kept_rev.append(doc)
        used_chars += len(doc)
    kept = list(reversed(kept_rev))
    return kept, {
        "strategy": "tail_chronological_char_cap",
        "max_chars": max_chars,
        "truncated": truncated,
        "total_docs": len(docs),
        "kept_docs": len(kept),
        "total_chars": sum(len(d) for d in docs),
        "kept_chars": used_chars,
    }


def _get_supply_chain_text_prior(stock_code: str) -> list[str]:
    """为文本基线构造同源的产业链关系纯文本先验，用于剥离‘额外知识’与‘图结构’因素。"""
    if not SECTOR_CHAINS_PATH.exists():
        return []
    data = json.loads(SECTOR_CHAINS_PATH.read_text(encoding="utf-8"))
    entities = data.get("entities", {})
    edges = data.get("edges", [])
    target = stock_code.upper()
    direct_sources = {e["source"] for e in edges if e["target"] == target}
    lines: list[str] = []
    for e in edges:
        if e["target"] == target or e["target"] in direct_sources:
            s_name = entities.get(e["source"], {}).get("name", e["source"])
            t_name = entities.get(e["target"], {}).get("name", e["target"])
            lines.append(
                f"{s_name} ({e['source']}) -> {t_name} ({e['target']}) [关系:{e['relation']}, 符号:{e['transmission_sign']}]: {e.get('description', '')}"
            )
    return lines


def _build_eval_graph(blind_case: dict[str, Any], priced_in_r: float) -> L2Graph:
    nodes: list[ThesisNode] = []
    for idx, t in enumerate(blind_case["prior_theses"]):
        nodes.append(
            ThesisNode(
                id=t["id"],
                type=t["type"],
                title=t["title"],
                category="BENCHMARK",
                status=t.get("status", "ACTIVE"),
                weight=float(t["weight"]),
                confidence=float(t["confidence"]),
                created_at="2024-05-01",
                updated_at=blind_case["as_of_date"],
                priced_in_ratio=priced_in_r if idx == 0 else round(priced_in_r * 0.5, 2),
                evidence_pointers=["EV_20240501_01_init"],
                invalidation_condition="核心假设证伪或大客户砍单",
            )
        )
    edges: list[Edge] = []
    if len(nodes) >= 2:
        rel = "COMPETES_WITH" if nodes[0].type != nodes[1].type else "CONFIRM"
        edges.append(
            Edge(
                source=nodes[0].id,
                target=nodes[1].id,
                relation=rel,
                hop=1,
                transmission_sign="-1" if rel == "COMPETES_WITH" else "+1",
                created_at="2024-05-01",
                description="前置节点逻辑关联边",
            )
        )
    return L2Graph(
        stock_code=blind_case["stock_code"],
        stock_name=blind_case["stock_name"],
        last_updated=blind_case["as_of_date"],
        market_regime=MarketRegime(
            close_rank_pct_60d=blind_case["market_regime"].get("close_rank_pct_60d", 0.5),
            range_pos_60d=blind_case["market_regime"].get("range_pos_60d", 0.5),
            return_20d_pct=blind_case["market_regime"]["return_20d_pct"],
            turnover_anomaly=blind_case["market_regime"]["turnover_anomaly"],
            net_sentiment_score=0.0,
        ),
        thesis_nodes=nodes,
        edges=edges,
    )


def _extract_invalidated_or_priced_in_id(inf_resp: InferenceResponse) -> Optional[str]:
    for op in inf_resp.patch_ops:
        if op.op in ("INVALIDATE", "PRICED_IN") and op.target_node_id:
            return op.target_node_id
    return None


def evaluate_single_case_method(
    method_name: str,
    blind_case: dict[str, Any],
    *,
    alpha: float = 0.8,
    lambda_decay: float = 0.6,
    use_cache: bool = True,
) -> dict[str, Any]:
    """对单个盲测样例与单个方法执行真实 LLM 调用；若 API 失败则记录 status=FAILED，绝不用规则结果代替。"""
    assert_no_truth_leakage(blind_case)
    ev = blind_case["latest_event"]
    ev_id = ev["event_id"]
    mr = blind_case["market_regime"]
    code, name, cutoff = blind_case["stock_code"], blind_case["stock_name"], blind_case["as_of_date"]

    try:
        # 分支 1：B1 长上下文方法 & B2 词法检索方法（统一调用同一 LLM 与相同输出 Schema）
        if method_name.startswith("B1:") or method_name.startswith("B2"):
            if method_name.startswith("B1:"):
                docs_for_llm, trunc_info = _truncate_docs_reproducibly(blind_case["prior_chunks"], max_chars=MAX_CONTEXT_CHARS)
                prior_txt = None
            else:
                ev_text = f"{ev.get('title', '')} {ev.get('content', '')}"
                scored = sorted(
                    blind_case["prior_chunks"],
                    key=lambda c: _char_tfidf_cosine(ev_text, c),
                    reverse=True,
                )[:LEXICAL_TOP_K]
                docs_for_llm = scored
                trunc_info = {"strategy": "lexical_char_bigram_top_k", "top_k": LEXICAL_TOP_K, "total_docs": len(blind_case["prior_chunks"]), "kept_docs": len(scored)}
                prior_txt = _get_supply_chain_text_prior(code) if "B2+Prior" in method_name else None

            sys_p, usr_p = build_baseline_llm_prompt(
                method_tag=method_name,
                stock_code=code,
                stock_name=name,
                as_of_date=cutoff,
                event_id=ev_id,
                candidate_theses=blind_case["prior_theses"],
                retrieved_or_full_docs=docs_for_llm,
                market_regime=mr,
                new_event=ev,
                supply_chain_text_prior=prior_txt,
            )
            assert_no_truth_leakage(blind_case, sys_p, usr_p)
            inf_resp, exec_meta, trace = _call_llm_json(
                sys_p,
                usr_p,
                InferenceResponse,
                {"priced_in_info": mr, "as_of_date": cutoff, "event_id": ev_id},
                method_tag=method_name,
                use_cache=use_cache,
            )
            inv_id = _extract_invalidated_or_priced_in_id(inf_resp)
            return {
                "status": "SUCCESS",
                "pred_dir": inf_resp.t5_forecast.direction,
                "inv_id": inv_id,
                "call_origin": exec_meta.call_origin,
                "token_count_type": exec_meta.token_count_type,
                "prompt_tokens": exec_meta.prompt_tokens,
                "completion_tokens": exec_meta.completion_tokens,
                "cached_tokens": exec_meta.cached_tokens,
                "estimated_tokens": exec_meta.estimated_tokens,
                "request_hash": exec_meta.request_hash,
                "truncation_info": trunc_info,
                "system_prompt": sys_p,
                "user_prompt": usr_p,
                "raw_response_text": trace.get("raw_response_text"),
                "parsed_output": inf_resp.model_dump(),
                "error": None,
            }

        # 分支 2：Ours 图谱记忆方法及其单变量正交消融（调用与应用完全一致的 run_agent_pipeline）
        enable_invalidation = method_name != "Ablation A: w/o Invalidation Only"
        enable_priced_in = method_name != "Ablation B: w/o Priced-in Only"
        use_edges = method_name != "Ablation C1: w/o Supply-Chain Prior & KG Edges (Node-Only)"
        max_hops = (
            0
            if method_name == "Ablation C1: w/o Supply-Chain Prior & KG Edges (Node-Only)"
            else (1 if method_name == "Ablation C2: 1-Hop KG Only (cutoff=1)" else 2)
        )
        r_pi = float(mr["priced_in_ratio"]) if enable_priced_in else 0.0
        init_g = _build_eval_graph(blind_case, priced_in_r=r_pi)

        ev_with_pi = {
            **ev,
            "priced_in_override": {
                "stock_code": code,
                "as_of_date": cutoff,
                "storage_read_mode": "IN_MEMORY",
                "underlying_data_origin": "CURATED_REAL_ARCHIVE",
                **mr,
                "priced_in_ratio": r_pi,
            },
        }
        pipe_out = run_agent_pipeline(
            code,
            ev_with_pi,
            as_of_date=cutoff,
            stock_name=name,
            persist=False,
            use_edges=use_edges,
            max_hops=max_hops,
            enable_invalidation=enable_invalidation,
            enable_priced_in=enable_priced_in,
            alpha=alpha,
            lambda_decay=lambda_decay,
            initial_graph=init_g,
            method_tag=method_name,
            use_cache=use_cache,
        )
        inf_resp: InferenceResponse = pipe_out["inference"]
        trace = pipe_out["llm_trace"]
        meta_d = pipe_out["execution_meta"]
        assert_no_truth_leakage(blind_case, trace["system_prompt"], trace["user_prompt"])
        inv_id = _extract_invalidated_or_priced_in_id(inf_resp)
        return {
            "status": "SUCCESS",
            "pred_dir": inf_resp.t5_forecast.direction,
            "graph_net_score_after": pipe_out["score_after"],
            "inv_id": inv_id,
            "call_origin": meta_d["call_origin"],
            "token_count_type": meta_d["token_count_type"],
            "prompt_tokens": meta_d["prompt_tokens"],
            "completion_tokens": meta_d["completion_tokens"],
            "cached_tokens": meta_d["cached_tokens"],
            "estimated_tokens": meta_d["estimated_tokens"],
            "request_hash": meta_d["request_hash"],
            "truncation_info": {"strategy": "l2_graph_state_compression", "node_count": len(init_g.thesis_nodes), "edge_count": len(init_g.edges)},
            "system_prompt": trace["system_prompt"],
            "user_prompt": trace["user_prompt"],
            "raw_response_text": trace.get("raw_response_text"),
            "parsed_output": inf_resp.model_dump(),
            "error": None,
        }
    except Exception as exc:
        cfg_safe = {}
        try:
            c = resolve_llm_config()
            cfg_safe = {"model": c["model"], "base_url": c["base_url"]}
        except Exception:
            pass
        return {
            "status": "FAILED",
            "pred_dir": None,
            "inv_id": None,
            "call_origin": "API_ERROR",
            "token_count_type": "MISSING_OR_ESTIMATED",
            "prompt_tokens": None,
            "completion_tokens": None,
            "cached_tokens": None,
            "estimated_tokens": None,
            "request_hash": None,
            "truncation_info": None,
            "system_prompt": None,
            "user_prompt": None,
            "raw_response_text": None,
            "parsed_output": None,
            "error": str(exc),
            **cfg_safe,
        }


def run_llm_evaluation_suite(
    dataset_name: str = "real12",
    limit: Optional[int] = None,
    methods: Optional[list[str]] = None,
    use_cache: bool = True,
    run_id: Optional[str] = None,
) -> dict[str, Any]:
    """执行真实 API 评测流水线：先执行最小连通性检查，再逐样例调用并写入独立 runs/{run_id}/ 目录。"""
    conn_info = check_llm_connectivity()
    cfg = resolve_llm_config()

    raw_cases = load_real_fin_events_12() if dataset_name == "real12" else build_fin_event_30()
    if limit is not None and limit > 0:
        raw_cases = raw_cases[:limit]
    active_methods = methods or CORE_METHODS

    ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = run_id or f"run_{dataset_name}_{ts_str}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    records_file = run_dir / "records.jsonl"

    summary: dict[str, dict[str, Any]] = {}
    by_scenario: dict[str, dict[str, Any]] = {}

    with records_file.open("w", encoding="utf-8") as rec_f:
        for m in active_methods:
            correct, valid_cnt, failed_cnt = 0, 0, 0
            live_calls, cache_hits = 0, 0
            exact_p_list: list[int] = []
            exact_c_list: list[int] = []
            cached_tok_list: list[int] = []
            est_tok_list: list[int] = []
            tp, fp, fn = 0, 0, 0
            scen_stats = {s: {"correct": 0, "total": 0, "failed": 0} for s in ("TEMPORAL_REVERSAL", "PRICED_IN_TRAP", "SECTOR_CONTAGION")}

            for raw_case in raw_cases:
                norm_case = _normalize_case(raw_case)
                blind_input = _make_blind_input(raw_case)
                out = evaluate_single_case_method(m, blind_input, use_cache=use_cache)

                gt_dir = norm_case["ground_truth_t5_direction"]
                gt_inv = norm_case["ground_truth_invalidated_id"]
                scen = norm_case["scenario"]
                scen_stats[scen]["total"] += 1

                if out["status"] == "FAILED":
                    failed_cnt += 1
                    scen_stats[scen]["failed"] += 1
                else:
                    valid_cnt += 1
                    if out["call_origin"] == "LIVE_API_CALL":
                        live_calls += 1
                    elif out["call_origin"] == "RESPONSE_CACHE_HIT":
                        cache_hits += 1

                    if out["prompt_tokens"] is not None and out["completion_tokens"] is not None:
                        exact_p_list.append(int(out["prompt_tokens"]))
                        exact_c_list.append(int(out["completion_tokens"]))
                    elif out["estimated_tokens"] is not None:
                        est_tok_list.append(int(out["estimated_tokens"]))
                    if out["cached_tokens"] is not None:
                        cached_tok_list.append(int(out["cached_tokens"]))

                    is_hit = int(out["pred_dir"] == gt_dir)
                    correct += is_hit
                    scen_stats[scen]["correct"] += is_hit

                    pred_inv = out["inv_id"]
                    if pred_inv is not None and pred_inv == gt_inv:
                        tp += 1
                    elif pred_inv is not None and pred_inv != gt_inv:
                        fp += 1
                    elif pred_inv is None and gt_inv is not None:
                        fn += 1

                rec_entry = {
                    "run_id": run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "dataset": dataset_name,
                    "case_id": norm_case["case_id"],
                    "stock_code": norm_case["stock_code"],
                    "as_of_date": norm_case["as_of_date"],
                    "method": m,
                    "model_name": cfg["model"],
                    "base_url": cfg["base_url"],
                    "generation_params": {
                        "temperature": DEFAULT_TEMPERATURE,
                        "max_tokens": DEFAULT_MAX_TOKENS,
                        "timeout": DEFAULT_TIMEOUT,
                        "max_retries": DEFAULT_MAX_RETRIES,
                    },
                    "input_version": INPUT_SCHEMA_VERSION,
                    "status": out["status"],
                    "call_origin": out["call_origin"],
                    "request_hash": out["request_hash"],
                    "token_count_type": out["token_count_type"],
                    "usage": {
                        "prompt_tokens": out["prompt_tokens"],
                        "completion_tokens": out["completion_tokens"],
                        "cached_tokens": out["cached_tokens"],
                        "estimated_tokens": out["estimated_tokens"],
                    },
                    "truncation_info": out["truncation_info"],
                    "pred_dir": out["pred_dir"],
                    "pred_inv_id": out["inv_id"],
                    "ground_truth_t5_direction": gt_dir,
                    "ground_truth_invalidated_id": gt_inv,
                    "system_prompt": out["system_prompt"],
                    "user_prompt": out["user_prompt"],
                    "raw_response_text": out["raw_response_text"],
                    "parsed_output": out["parsed_output"],
                    "error": out["error"],
                }
                rec_f.write(json.dumps(rec_entry, ensure_ascii=False) + "\n")
                rec_f.flush()

            n_total = len(raw_cases)
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
            avg_p = round(sum(exact_p_list) / len(exact_p_list), 1) if exact_p_list else None
            avg_c = round(sum(exact_c_list) / len(exact_c_list), 1) if exact_c_list else None
            avg_tot = round(avg_p + avg_c, 1) if (avg_p is not None and avg_c is not None) else None

            summary[m] = {
                "total_cases": n_total,
                "valid_cases": valid_cnt,
                "failed_cases": failed_cnt,
                "live_api_calls": live_calls,
                "response_cache_hits": cache_hits,
                "t5_acc_over_all_pct": round(correct / max(1, n_total) * 100, 1),
                "t5_acc_over_valid_pct": round(correct / max(1, valid_cnt) * 100, 1) if valid_cnt > 0 else None,
                "precision_pct": round(precision * 100, 1),
                "recall_pct": round(recall * 100, 1),
                "f1_pct": round(f1 * 100, 1),
                "avg_prompt_tokens": avg_p,
                "avg_completion_tokens": avg_c,
                "avg_total_tokens": avg_tot,
                "avg_cached_tokens": round(sum(cached_tok_list) / len(cached_tok_list), 1) if cached_tok_list else None,
                "avg_estimated_tokens": round(sum(est_tok_list) / len(est_tok_list), 1) if est_tok_list else None,
            }
            by_scenario[m] = {
                s: round(scen_stats[s]["correct"] / max(1, scen_stats[s]["total"]) * 100, 1)
                for s in scen_stats
            }

    manifest = {
        "run_id": run_id,
        "timestamp": ts_str,
        "evaluation_mode": "LIVE_LLM_BENCHMARK",
        "dataset": dataset_name,
        "sample_count": len(raw_cases),
        "model_name": cfg["model"],
        "base_url": cfg["base_url"],
        "generation_params": {
            "temperature": DEFAULT_TEMPERATURE,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "timeout": DEFAULT_TIMEOUT,
            "max_retries": DEFAULT_MAX_RETRIES,
            "lexical_top_k": LEXICAL_TOP_K,
            "b1_max_context_chars": MAX_CONTEXT_CHARS,
        },
        "input_version": INPUT_SCHEMA_VERSION,
        "connectivity_check": conn_info,
        "knowledge_disclosure": KNOWLEDGE_DISCLOSURE,
        "records_path": str(records_file),
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    out_payload = {"manifest": manifest, "summary": summary, "by_scenario": by_scenario}
    (run_dir / "summary.json").write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_payload


def run_all_benchmarks(limit: Optional[int] = 2, use_cache: bool = True) -> dict[str, Any]:
    """默认先用少量开发样例验证真实 API 评测流水线（避免在测试集清理前盲目批量消耗调用）。"""
    return run_llm_evaluation_suite(dataset_name="real12", limit=limit, use_cache=use_cache)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fin-MemKG 真实大模型同底座公平评测")
    parser.add_argument("--dataset", choices=["real12", "syn30"], default="real12")
    parser.add_argument("--limit", type=int, default=2, help="评测样例数上限（默认 2 例用于开发验证）")
    parser.add_argument("--no-cache", action="store_true", help="禁用请求哈希缓存，强制每次发起在线 API 请求")
    parser.add_argument("--check-only", action="store_true", help="仅执行 API 连通性与结构化输出检查")
    args = parser.parse_args()

    if args.check_only:
        info = check_llm_connectivity()
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        res = run_llm_evaluation_suite(
            dataset_name=args.dataset,
            limit=args.limit if args.limit > 0 else None,
            use_cache=not args.no_cache,
        )
        print(json.dumps(res["summary"], ensure_ascii=False, indent=2))
