from __future__ import annotations
import hashlib, json, logging, math, re, threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import networkx as nx
import pandas as pd
from schema import Edge, EvidenceType, L2Graph, PatchOp, StateHistoryEntry, ThesisNode

logger = logging.getLogger("fin_memkg.tools")
BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory"
L1_INDEX_PATH = MEMORY_DIR / "L1_insight_index.md"
L2_DIR, L4_DIR, CACHE_DIR = MEMORY_DIR / "L2_graphs", MEMORY_DIR / "L4_archive", MEMORY_DIR / "L4_archive/cache"
SECTOR_CHAINS_PATH = L2_DIR / "sector_chains.json"
CACHE_SERIES_VERSION = "v2_date_anchored"


def _clean_symbol(stock_code: str) -> str:
    """剥离 .SZ / .SH 等后缀，提取 6 位纯数字代码供 akshare 调用。"""
    digits = re.sub(r"\D", "", stock_code.strip())
    return digits[:6] if len(digits) >= 6 else digits.zfill(6)


def generate_event_id(title: str, published_at: str, seq: int = 1) -> str:
    """生成唯一事件 ID：EV_{YYYYMMDD}_{SEQ:02d}_{HASH4}（基于标题+时间戳 MD5 前 4 位）。"""
    dt8 = str(published_at)[:10].replace("-", "")
    h4 = hashlib.md5(f"{title}_{published_at}".encode("utf-8")).hexdigest()[:4]
    return f"EV_{dt8}_{seq:02d}_{h4}"


def record_l4_event(
    stock_code: str,
    event_or_pub: dict[str, Any] | str,
    as_of_or_source: str = "",
    title: str = "",
    snippet: str = "",
    event_id: Optional[str] = None,
    evidence_type: EvidenceType = "EMPIRICAL_NEWS_FILING",
    persist: bool = True,
) -> dict[str, Any]:
    """构建标准化 L4 事件记录（含必填 evidence_type）；当 persist=False 时仅返回内存字典绝不写盘。"""
    L4_DIR.mkdir(parents=True, exist_ok=True)
    code = stock_code.upper()
    if isinstance(event_or_pub, dict):
        ev = event_or_pub
        as_of_cutoff = as_of_or_source[:10] if as_of_or_source else ""
        raw_pub = str(ev.get("published_at") or ev.get("date") or as_of_cutoff or "2026-10-14")
        pub_norm = raw_pub if len(raw_pub.strip()) > 10 else f"{raw_pub.strip()} 09:00:00"
        if as_of_cutoff and pub_norm[:10] > as_of_cutoff:
            raise ValueError(f"时间隔离违规：事件发布时间 {pub_norm} 晚于基准日 {as_of_cutoff}")
        source = str(ev.get("source", "实时催化"))
        title = str(ev.get("title", ""))
        snippet = str(ev.get("content") or ev.get("snippet") or ev.get("summary") or "")
        event_id = ev.get("event_id") or event_id
        ev_type: str = str(ev.get("evidence_type") or evidence_type)
    else:
        pub_norm = event_or_pub if len(event_or_pub.strip()) > 10 else f"{event_or_pub.strip()} 09:00:00"
        source = as_of_or_source
        ev_type = evidence_type

    p = L4_DIR / f"{code}_events.jsonl"
    existing = [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()] if p.exists() else []
    if not event_id:
        same_day = sum(1 for item in existing if str(item.get("published_at", ""))[:10] == pub_norm[:10])
        event_id = generate_event_id(title, pub_norm, seq=same_day + 1)
    for item in existing:
        if item.get("event_id") == event_id:
            item.setdefault("evidence_type", ev_type)
            return item
    rec = {
        "event_id": event_id,
        "published_at": pub_norm,
        "source": source,
        "title": title,
        "snippet": snippet,
        "stock_code": code,
        "evidence_type": ev_type,
    }
    if persist:
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def query_l4_archive(stock_code: str, pointer_id: Optional[str] = None, as_of_date: Optional[str] = None) -> list[dict]:
    """查询 L4 历史事件 JSONL，支持唯一 event_id 精确查询与 published_at[:10] <= as_of_date 严格过滤。"""
    p = L4_DIR / f"{stock_code.upper()}_events.jsonl"
    if not p.exists():
        return []
    results: list[dict] = []
    clean_ptr = pointer_id.lstrip("#") if pointer_id else None
    for raw in p.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        item = json.loads(raw)
        item.setdefault("evidence_type", "EMPIRICAL_NEWS_FILING")
        ev_date = str(item.get("published_at") or item.get("timestamp") or item.get("date") or "")[:10]
        if as_of_date and ev_date > as_of_date[:10]:
            continue
        if clean_ptr and str(item.get("event_id", "")).lstrip("#") != clean_ptr:
            continue
        results.append(item)
    return results


def find_contagion_paths(event_text: str, target_stock: str, lambda_decay: float = 0.6, max_hops: int = 2) -> list[dict]:
    """基于真实两跳三节点 NetworkX DiGraph 搜索从冲击源头节点 hit_node 到目标股 <=max_hops 跳的简单路径。"""
    if max_hops <= 0:
        return []
    chain_file = SECTOR_CHAINS_PATH if SECTOR_CHAINS_PATH.exists() else (MEMORY_DIR / "sector_chains.json")
    if not chain_file.exists():
        return []
    data = json.loads(chain_file.read_text(encoding="utf-8"))
    edges = data.get("edges", [])
    entities = data.get("entities", {})
    g = nx.DiGraph()
    for e in edges:
        g.add_edge(e["source"], e["target"], **e)

    target = target_stock.upper()
    if target not in g:
        return []
    text_low = event_text.lower()
    paths_out: list[dict] = []

    node_hits: dict[str, list[str]] = {}
    for nd in g.nodes():
        if nd == target or not nx.has_path(g, nd, target):
            continue
        hits: list[str] = []
        for _, _, ed in g.out_edges(nd, data=True):
            hits.extend(kw for kw in ed.get("keywords", []) if kw.lower() in text_low)
        if hits:
            node_hits[nd] = hits

    for hit_node, start_hits in node_hits.items():
        if any(pred in node_hits for pred in g.predecessors(hit_node)):
            continue

        for sp in nx.all_simple_paths(g, source=hit_node, target=target, cutoff=max_hops):
            actual_hops = len(sp) - 1
            if actual_hops < 1 or actual_hops > max_hops:
                continue
            sigma_total, gamma_total = 1.0, 1.0
            matched_kws = list(start_hits)
            rels, step_descs = [], []
            for i in range(actual_hops):
                u_i, v_i = sp[i], sp[i + 1]
                ed = g[u_i][v_i]
                matched_kws.extend(kw for kw in ed.get("keywords", []) if kw.lower() in text_low)
                s_i = 1.0 if ed.get("transmission_sign", "+1") == "+1" else -1.0
                g_i = float(ed.get("gamma", 0.75))
                sigma_total *= s_i
                gamma_total *= g_i
                rels.append(ed.get("relation", "UPSTREAM_DRIVES"))
                step_descs.append(f"Hop {i+1} ({u_i}->{v_i}, σ={ed.get('transmission_sign','+1')}, γ={g_i}): {ed.get('description','')}")

            if "COST_SQUEEZE" in rels and any(k in event_text for k in ("产能扩充", "超额交付", "跌破7.3万", "跌破7万", "成本再降", "拍卖价下调", "让利")):
                sigma_total = 1.0
            elif "DEMAND_PROXY" in rels and any(k in event_text for k in ("收缩", "急跌", "跌破2250", "倒挂")):
                sigma_total = -1.0

            path_factor = round(sigma_total * gamma_total * (lambda_decay ** (actual_hops - 1)), 4)
            inter_nodes = [
                {"id": nid, "name": entities.get(nid, {}).get("name", nid)}
                for nid in sp[1:-1]
            ]
            paths_out.append({
                "source": hit_node,
                "source_name": entities.get(hit_node, {}).get("name", hit_node),
                "intermediate_nodes": inter_nodes,
                "target": target,
                "path_nodes": sp,
                "path": " -> ".join(sp),
                "relation": rels[-1],
                "hop": actual_hops,
                "actual_hops": actual_hops,
                "transmission_sign": "+1" if sigma_total >= 0 else "-1",
                "gamma_total": round(gamma_total, 4),
                "lambda_decay": lambda_decay,
                "path_factor": path_factor,
                "matched_keywords": sorted(set(matched_kws)),
                "description": " ==> ".join(step_descs),
            })
    return sorted(paths_out, key=lambda x: (x["actual_hops"], abs(x["path_factor"])), reverse=True)


def _generate_synthetic_klines(stock_code: str, as_of_date: str, days: int = 60) -> list[dict]:
    """基于绝对日历时间轴锚定的无前视偏差合成量价序列：确保不同 as_of_date 截断后的动态量价指标真实随时间演化。"""
    end_dt = datetime.strptime(as_of_date[:10], "%Y-%m-%d")
    seed = sum(ord(c) for c in stock_code)
    anchor_dt = min(datetime(2026, 5, 1), end_dt - timedelta(days=int(days * 1.75)))
    rally_start = datetime(2026, 9, 16)
    rally_peak = datetime(2026, 10, 11)

    all_bars: list[dict] = []
    price = 100.0 + (seed % 30)
    cur_dt = anchor_dt
    while cur_dt <= end_dt:
        if cur_dt.weekday() < 5:
            cal_idx = (cur_dt - anchor_dt).days
            if rally_start <= cur_dt <= rally_peak:
                pct_chg = round((0.0155 + math.sin(cal_idx * 0.6) * 0.007) * 100, 2)
                turn_mult = 1.45
            elif cur_dt > rally_peak:
                pct_chg = -1.15
                turn_mult = 1.55
            else:
                pct_chg = round((0.0004 + math.sin(cal_idx * 0.45 + seed) * 0.014) * 100, 2)
                turn_mult = 1.0 + 0.12 * math.cos(cal_idx)
            price = round(price * (1.0 + pct_chg / 100.0), 2)
            base_turn = 3.0 + (seed % 4) * 0.25
            turnover = round(base_turn * turn_mult, 2)
            all_bars.append({"date": cur_dt.strftime("%Y-%m-%d"), "close": price, "pct_chg": pct_chg, "turnover": turnover})
        cur_dt += timedelta(days=1)

    df = pd.DataFrame(all_bars)
    if df.empty:
        return []
    df = df[df["date"] <= as_of_date[:10]].tail(days)
    return df.to_dict(orient="records")


def read_l1_index(keyword_filter: Optional[str] = None) -> str:
    """读取 memory/L1_insight_index.md，支持按关键词过滤板块或个股。"""
    if not L1_INDEX_PATH.exists():
        return ""
    content = L1_INDEX_PATH.read_text(encoding="utf-8")
    if not keyword_filter or not keyword_filter.strip():
        return content
    kw, matched = keyword_filter.strip().lower(), []
    for sec in re.split(r"(?=^##\s+)", content, flags=re.MULTILINE):
        if kw in sec.lower():
            lines = sec.strip().splitlines()
            if lines and kw in lines[0].lower():
                matched.append(sec.strip())
            elif hit := [ln for ln in lines[1:] if kw in ln.lower()]:
                matched.append("\n".join([lines[0]] + hit))
    return "\n\n".join(matched)


def fetch_market_data(stock_code: str, as_of_date: str) -> dict:
    """获取严格截断至 date <= as_of_date 的 60 日行情 DataFrame 与新闻，杜绝跨日期复用最新指标缓存。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = as_of_date[:10]
    cache_file = CACHE_DIR / f"{stock_code.upper()}_{cutoff}.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if cached.get("series_version") == CACHE_SERIES_VERSION and cached.get("as_of_date") == cutoff:
            df_c = pd.DataFrame(cached.get("klines_60d", []))
            if not df_c.empty:
                df_c["date"] = df_c["date"].astype(str).str.slice(0, 10)
                df_c = df_c[df_c["date"] <= cutoff].sort_values("date").tail(60)
                cached["klines_60d"] = df_c.to_dict(orient="records")
            origin = cached.get("origin") or cached.get("underlying_data_origin") or "SYNTHETIC_SIMULATION"
            cached["origin"] = origin
            cached["storage_read_mode"] = "DISK_CACHE"
            cached["underlying_data_origin"] = origin
            cached["data_source"] = f"DISK_CACHE:{origin}"
            cached.setdefault("fallback_reason", None)
            return cached

    clean_code, box = _clean_symbol(stock_code), {"klines": [], "news": [], "err": None}

    def _worker() -> None:
        try:
            import akshare as ak
            df_k = ak.stock_zh_a_hist(symbol=clean_code, period="daily", end_date=cutoff.replace("-", ""), adjust="qfq")
            if df_k is not None and not df_k.empty:
                df_k["日期"] = df_k["日期"].astype(str).str.slice(0, 10)
                df_k = df_k[df_k["日期"] <= cutoff].sort_values("日期").tail(60)
                box["klines"] = [
                    {"date": str(r["日期"])[:10], "close": float(r["收盘"]), "pct_chg": float(r.get("涨跌幅", 0.0)), "turnover": float(r.get("换手率", 0.0))}
                    for _, r in df_k.iterrows()
                ]
            df_n = ak.stock_news_em(symbol=clean_code)
            if df_n is not None and not df_n.empty:
                if "新闻标题" in df_n.columns:
                    df_n = df_n[df_n["新闻标题"].astype(str).str.contains("", regex=False, na=False)]
                items = [
                    {"date": str(r.get("发布时间", ""))[:10], "title": str(r.get("新闻标题", "")), "summary": str(r.get("新闻内容", ""))[:160]}
                    for _, r in df_n.iterrows() if str(r.get("发布时间", ""))[:10] <= cutoff
                ]
                box["news"] = sorted(items, key=lambda x: x["date"], reverse=True)[:15]
        except Exception as exc:
            box["err"] = exc

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=5.0)
    if not t.is_alive() and box["err"] is None and len(box["klines"]) >= 20:
        klines, news_list = box["klines"], box["news"]
        read_mode, origin, fb_reason = "LIVE_FETCH", "REAL_MARKET_API", None
    else:
        fb_reason = "akshare request timeout (>5.0s)" if t.is_alive() else f"akshare error or insufficient bars: {box['err']}"
        logger.warning("fetch_market_data fallback to SYNTHETIC_SIMULATION for %s (as_of=%s): %s", stock_code, cutoff, fb_reason)
        read_mode, origin = "LIVE_FETCH", "SYNTHETIC_SIMULATION"
        klines = _generate_synthetic_klines(stock_code.upper(), cutoff, days=60)
        news_list = [
            {"date": str(ev.get("published_at", cutoff))[:10], "title": f"[{ev.get('event_id')}] {ev.get('title', '')}", "summary": ev.get("snippet", ev.get("summary", ""))}
            for ev in query_l4_archive(stock_code.upper(), as_of_date=cutoff)[-15:]
        ]
    payload = {
        "series_version": CACHE_SERIES_VERSION,
        "stock_code": stock_code.upper(),
        "as_of_date": cutoff,
        "origin": origin,
        "storage_read_mode": read_mode,
        "underlying_data_origin": origin,
        "data_source": f"{read_mode}:{origin}",
        "fallback_reason": fb_reason,
        "klines_60d": klines,
        "news": news_list,
    }
    cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def verify_priced_in(stock_code: str, as_of_date: str, sentiment_sign: int = 1) -> dict:
    """严格基于截断至 date <= as_of_date 的 DataFrame 动态计算 60 日经验分位数、20 日涨跌幅、RSI 与预期兑现度。"""
    cutoff = as_of_date[:10]
    m_data = fetch_market_data(stock_code, cutoff)
    df = pd.DataFrame(m_data.get("klines_60d", []))
    if not df.empty:
        df["date"] = df["date"].astype(str).str.slice(0, 10)
        df = df[df["date"] <= cutoff].sort_values("date").tail(60).reset_index(drop=True)
        closes = df["close"].astype(float).tolist()
        turnovers = df["turnover"].astype(float).tolist()
    else:
        closes, turnovers = [], []

    p_t = closes[-1] if closes else 0.0
    ret_20d = round((p_t / closes[-21] - 1.0) * 100.0, 2) if len(closes) >= 21 else 0.0
    close_rank_pct_60d = round(sum(1 for p in closes if p <= p_t) / len(closes), 4) if closes else 0.5
    c_min, c_max = (min(closes), max(closes)) if closes else (0.0, 0.0)
    range_pos_60d = round((p_t - c_min) / (c_max - c_min), 4) if c_max > c_min else 0.5

    t_ratio = (sum(turnovers[-5:]) / 5.0) / (sum(turnovers) / len(turnovers)) if turnovers else 1.0
    turnover_anomaly = "HIGH" if t_ratio > 1.25 else ("LOW" if t_ratio < 0.75 else "NORMAL")
    diffs = [closes[i] - closes[i - 1] for i in range(max(1, len(closes) - 14), len(closes))]
    avg_g, avg_l = sum(max(d, 0.0) for d in diffs) / 14.0, sum(max(-d, 0.0) for d in diffs) / 14.0
    rsi_14 = round(100.0 - (100.0 / (1.0 + avg_g / avg_l)), 2) if avg_l > 0 else 85.0

    pos_metric = 0.5 * close_rank_pct_60d + 0.5 * range_pos_60d
    if sentiment_sign >= 0:
        if ret_20d > 15.0 and pos_metric > 0.7:
            ratio = min(0.95, round(0.55 + 0.25 * pos_metric + 0.006 * min(ret_20d, 35.0), 2))
            desc = f"近20日已累计上涨{ret_20d:.1f}%，经验分位{close_rank_pct_60d*100:.0f}%/区间位置{range_pos_60d*100:.0f}%，利好预期已高度透支"
        else:
            ratio = max(0.05, min(0.65, round(0.35 * pos_metric + 0.01 * max(ret_20d, 0.0), 2)))
            desc = f"近20日涨跌幅{ret_20d:.1f}%，经验分位{close_rank_pct_60d*100:.0f}%，利好尚有反应空间"
    else:
        if ret_20d < -15.0 and pos_metric < 0.3:
            ratio = min(0.95, round(0.60 + 0.25 * (1.0 - pos_metric) + 0.006 * min(abs(ret_20d), 35.0), 2))
            desc = f"近20日已累计下跌{abs(ret_20d):.1f}%，处于60日低分位，利空已充分释放"
        else:
            ratio = max(0.05, min(0.65, round(0.35 * (1.0 - pos_metric) + 0.01 * max(-ret_20d, 0.0), 2)))
            desc = f"近20日涨跌幅{ret_20d:.1f}%，利空冲击尚未出清"
    return {
        "stock_code": stock_code.upper(),
        "as_of_date": cutoff,
        "storage_read_mode": m_data.get("storage_read_mode", "DISK_CACHE"),
        "underlying_data_origin": m_data.get("underlying_data_origin", "SYNTHETIC_SIMULATION"),
        "data_source": m_data.get("data_source"),
        "fallback_reason": m_data.get("fallback_reason"),
        "return_20d_pct": ret_20d,
        "close_rank_pct_60d": close_rank_pct_60d,
        "range_pos_60d": range_pos_60d,
        "price_percentile_60d": close_rank_pct_60d,
        "turnover_anomaly": turnover_anomaly,
        "rsi_14": rsi_14,
        "priced_in_ratio": ratio,
        "priced_in_desc": desc,
    }


def load_l2_graph(stock_code: str, as_of_date: Optional[str] = None) -> Optional[L2Graph]:
    """在内存深拷贝上加载并回放截至 as_of_date 的图谱；若触发历史回滚则标记 is_historical_view=True 并动态重算历史量价状态。"""
    p = L2_DIR / f"{stock_code.upper()}.json"
    if not p.exists():
        return None
    raw_graph = L2Graph.model_validate_json(p.read_text(encoding="utf-8"))
    graph = raw_graph.model_copy(deep=True)
    graph.is_historical_view = False
    if not as_of_date:
        return graph

    cutoff = as_of_date[:10]
    triggered_rollback = (
        cutoff < raw_graph.last_updated[:10]
        or any(n.created_at[:10] > cutoff for n in raw_graph.thesis_nodes)
        or any(e.created_at[:10] > cutoff for e in raw_graph.edges)
        or any(str(h.get("as_of_date", ""))[:10] > cutoff for h in raw_graph.history_log)
    )

    kept_nodes = [n.model_copy(deep=True) for n in graph.thesis_nodes if n.created_at[:10] <= cutoff]
    node_map = {n.id: n for n in kept_nodes}

    for entry in reversed(graph.history_log):
        if str(entry.get("as_of_date", ""))[:10] > cutoff:
            triggered_rollback = True
            nid = entry.get("node_id")
            if nid in node_map:
                target = node_map[nid]
                full_before = entry.get("node_before_full")
                if isinstance(full_before, dict) and full_before:
                    target.restore_from_snapshot(full_before)
                elif entry.get("prev_status"):
                    target.status = entry["prev_status"]
                    if entry.get("prev_weight") is not None:
                        target.weight = float(entry["prev_weight"])
                    if entry.get("op") == "PRICED_IN":
                        target.priced_in_ratio = min(target.priced_in_ratio, 0.25)
                    target.updated_at = cutoff

    for n in kept_nodes:
        n.evidence_pointers = [
            ptr for ptr in n.evidence_pointers
            if len(ptr) < 11 or not ptr.startswith("EV_") or f"{ptr[3:7]}-{ptr[7:9]}-{ptr[9:11]}" <= cutoff
        ]

    graph.thesis_nodes = kept_nodes
    graph.edges = [
        e for e in graph.edges
        if e.source in node_map and e.target in node_map and e.created_at[:10] <= cutoff
    ]
    graph.history_log = [h for h in graph.history_log if str(h.get("as_of_date", ""))[:10] <= cutoff]
    graph.last_updated = cutoff

    if triggered_rollback:
        graph.is_historical_view = True
        hist_pi = verify_priced_in(stock_code, cutoff)
        graph.market_regime.close_rank_pct_60d = hist_pi["close_rank_pct_60d"]
        graph.market_regime.range_pos_60d = hist_pi["range_pos_60d"]
        graph.market_regime.return_20d_pct = hist_pi["return_20d_pct"]
        graph.market_regime.turnover_anomaly = hist_pi["turnover_anomaly"]

    graph.compute_net_score(use_edges=True)
    return graph


def validate_temporal_and_evidence(
    stock_code: str,
    patch_ops: list[PatchOp],
    as_of_date: str,
    extra_l4_events: Optional[list[dict]] = None,
    initial_graph: Optional[L2Graph] = None,
) -> None:
    """入图前硬校验：检查时间戳隔离、L4 证据真实存在性、ACTIVE 证伪条件及证据类型语义匹配。"""
    cutoff = as_of_date[:10]
    all_l4 = {str(item.get("event_id", "")).lstrip("#"): item for item in query_l4_archive(stock_code)}
    if initial_graph is not None:
        for nd in initial_graph.thesis_nodes:
            for ptr in nd.evidence_pointers:
                clean_ptr = ptr.lstrip("#")
                all_l4.setdefault(
                    clean_ptr,
                    {
                        "event_id": clean_ptr,
                        "published_at": f"{nd.created_at[:10]} 09:00:00",
                        "evidence_type": "EMPIRICAL_NEWS_FILING",
                    },
                )
    for ex in extra_l4_events or []:
        if ex.get("event_id"):
            all_l4[str(ex["event_id"]).lstrip("#")] = ex

    for op in patch_ops:
        if op.published_at and op.published_at[:10] > cutoff:
            raise ValueError(f"时间隔离违规：PatchOp 关联事件时间 {op.published_at} 晚于基准日 {cutoff}")
        ev_ids: list[str] = [op.evidence_id.lstrip("#")] if op.evidence_id else []
        if op.new_node:
            if op.new_node.created_at[:10] > cutoff or op.new_node.updated_at[:10] > cutoff:
                raise ValueError(f"时间隔离违规：新节点 [{op.new_node.id}] 时间戳晚于基准日 {cutoff}")
            if op.new_node.status == "ACTIVE" and (not op.new_node.invalidation_condition or not op.new_node.invalidation_condition.strip()):
                raise ValueError(f"契约违规：ACTIVE 节点 [{op.new_node.id}] 缺少 invalidation_condition")
            ev_ids.extend(p.lstrip("#") for p in op.new_node.evidence_pointers)

        if op.op in ("CONFIRM", "INVALIDATE", "ADD_NODE") and not ev_ids:
            raise ValueError(f"无验证不入图违规：操作 {op.op} 必须携带至少一条合法的 L4 证据 ID")

        for eid in dict.fromkeys(ev_ids):
            if eid not in all_l4:
                raise ValueError(f"无验证不入图违规：证据 ID [{eid}] 在 {stock_code} 的 L4_archive 中不存在")
            ev_obj = all_l4[eid]
            pub_dt = str(ev_obj.get("published_at") or ev_obj.get("timestamp") or "")[:10]
            if pub_dt > cutoff:
                raise ValueError(f"时间隔离违规：L4 证据 [{eid}] 发布日期 {pub_dt} 晚于基准日 {cutoff}")
            ev_type = ev_obj.get("evidence_type", "EMPIRICAL_NEWS_FILING")
            if ev_type == "PRICE_VOLUME_SUMMARY" and op.op in ("ADD_NODE", "CONFIRM"):
                raise ValueError("证据类型不匹配：纯量价摘要不能直接支撑基本面逻辑生成")


def patch_l2_graph(
    stock_code: str,
    patch_ops: list[PatchOp],
    as_of_date: str,
    use_edges: bool = True,
    persist: bool = True,
    extra_l4_events: Optional[list[dict]] = None,
    initial_graph: Optional[L2Graph] = None,
) -> L2Graph:
    """事务级状态更新：支持内存 initial_graph 直传与防历史图谱覆写保护 (is_historical_view)。"""
    cutoff = as_of_date[:10]
    if initial_graph is not None:
        graph = initial_graph.model_copy(deep=True)
        graph.is_historical_view = initial_graph.is_historical_view
    else:
        graph = load_l2_graph(stock_code, as_of_date=cutoff)
    if graph is None:
        raise FileNotFoundError(f"L2 graph not found for {stock_code}")

    if graph.is_historical_view and persist:
        raise ValueError("严重违规：严禁将历史回放图谱覆写至当前正式存储中！")

    validate_temporal_and_evidence(
        stock_code, patch_ops, cutoff, extra_l4_events=extra_l4_events, initial_graph=graph
    )

    node_map = {n.id: n for n in graph.thesis_nodes}
    for op in patch_ops:
        target = node_map.get(op.target_node_id or "")
        if op.op == "CONFIRM" and target:
            if not target.invalidation_condition or not target.invalidation_condition.strip():
                raise ValueError(f"ACTIVE 节点 [{target.id}] 缺少 invalidation_condition")
            before_full = target.snapshot_dict()
            prev_st, prev_w = target.status, target.weight
            target.status = "ACTIVE"
            target.weight = op.new_weight if op.new_weight is not None else target.weight
            if op.new_weight is None:
                target.confidence = min(1.0, round(target.confidence + 0.05, 4))
            if op.evidence_id and op.evidence_id not in target.evidence_pointers:
                target.evidence_pointers.append(op.evidence_id)
            target.status_reason, target.updated_at = op.reason, cutoff
            graph.history_log.append(
                StateHistoryEntry(
                    as_of_date=cutoff, op="CONFIRM", node_id=target.id,
                    prev_status=prev_st, new_status="ACTIVE", prev_weight=prev_w,
                    new_weight=target.weight, evidence_id=op.evidence_id,
                    node_before_full=before_full,
                ).model_dump()
            )
        elif op.op == "INVALIDATE" and target:
            before_full = target.snapshot_dict()
            prev_st, prev_w = target.status, target.weight
            target.status, target.weight, target.status_reason, target.updated_at = "INVALIDATED", 0.0, op.reason, cutoff
            if op.evidence_id and op.evidence_id not in target.evidence_pointers:
                target.evidence_pointers.append(op.evidence_id)
            graph.history_log.append(
                StateHistoryEntry(
                    as_of_date=cutoff, op="INVALIDATE", node_id=target.id,
                    prev_status=prev_st, new_status="INVALIDATED", prev_weight=prev_w,
                    new_weight=0.0, evidence_id=op.evidence_id,
                    node_before_full=before_full,
                ).model_dump()
            )
        elif op.op == "PRICED_IN" and target:
            before_full = target.snapshot_dict()
            prev_st, prev_w = target.status, target.weight
            target.status, target.priced_in_ratio, target.status_reason, target.updated_at = "PRICED_IN", 1.0, op.reason, cutoff
            if op.evidence_id and op.evidence_id not in target.evidence_pointers:
                target.evidence_pointers.append(op.evidence_id)
            graph.history_log.append(
                StateHistoryEntry(
                    as_of_date=cutoff, op="PRICED_IN", node_id=target.id,
                    prev_status=prev_st, new_status="PRICED_IN", prev_weight=prev_w,
                    new_weight=target.weight, evidence_id=op.evidence_id,
                    node_before_full=before_full,
                ).model_dump()
            )
        elif op.op == "ADD_NODE" and op.new_node:
            new_n = op.new_node.model_copy(deep=True)
            graph.thesis_nodes.append(new_n)
            node_map[new_n.id] = new_n
            if op.new_edge:
                new_e = op.new_edge.model_copy(deep=True)
                new_e.created_at = cutoff
                graph.edges.append(new_e)
            ev_ptr = new_n.evidence_pointers[0] if new_n.evidence_pointers else op.evidence_id
            graph.history_log.append(
                StateHistoryEntry(
                    as_of_date=cutoff, op="ADD_NODE", node_id=new_n.id,
                    prev_status=None, new_status=new_n.status, prev_weight=None,
                    new_weight=new_n.weight, evidence_id=ev_ptr,
                    node_before_full=None,
                ).model_dump()
            )

    net_score = graph.compute_net_score(use_edges=use_edges)
    graph.last_updated = cutoff

    if persist:
        if graph.is_historical_view:
            raise ValueError("严重违规：严禁将历史回放图谱覆写至当前正式存储中！")
        for ex in extra_l4_events or []:
            record_l4_event(stock_code, ex, cutoff, persist=True)
        (L2_DIR / f"{stock_code.upper()}.json").write_text(graph.model_dump_json(indent=2), encoding="utf-8")
        if L1_INDEX_PATH.exists():
            bull_cnt = sum(1 for n in graph.thesis_nodes if n.status == "ACTIVE" and n.type == "BULLISH_LOGIC")
            bear_cnt = sum(1 for n in graph.thesis_nodes if n.status == "ACTIVE" and n.type == "BEARISH_LOGIC")
            state_str = "偏多" if net_score > 0.2 else ("偏空" if net_score < -0.2 else "震荡筑底")
            badge = f"[当前净状态: {state_str}({net_score:+.2f}) | 活跃利好:{bull_cnt} | 活跃利空:{bear_cnt}]"
            pat = rf"(`{re.escape(stock_code.upper())}`\s+\*\*[^*]+\*\*)(\s*\[当前净状态:[^\]]+\])?"
            L1_INDEX_PATH.write_text(re.sub(pat, lambda m: f"{m.group(1)} {badge}", L1_INDEX_PATH.read_text(encoding="utf-8")), encoding="utf-8")
    return graph
