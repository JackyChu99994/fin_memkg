# -*- coding: utf-8 -*-
"""L2：逻辑图谱存储层（双后端）。

同一个接口两套实现：
  * Neo4jStore —— 你的 AuraDB，答辩时展示“真正的图数据库”；
  * LocalStore —— 本地 JSON，断网/额度用完时的兜底，保证 Demo 永不翻车。

两者数据结构一致，`app.py` 不需要知道用的是哪个。
"""
from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import (ENTITY_TYPES, LOCAL_GRAPH, NEO4J_DATABASE, NEO4J_PASSWORD,
                    NEO4J_URI, NEO4J_USER, REL_TYPES, STATUS_ACTIVE,
                    STATUS_INVALID, STORE_MODE, has_neo4j)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_key(key: str) -> str:
    return re.sub(r"[^0-9a-zA-Z_\u4e00-\u9fa5]", "_", str(key))[:40] or "attr"


def _clean_props(props: dict) -> dict:
    out = {}
    for k, v in (props or {}).items():
        if v is None:
            continue
        key = _safe_key(k)
        if isinstance(v, (list, tuple)):
            out[key] = [str(x)[:300] for x in v][:20]
        elif isinstance(v, (int, float, bool)):
            out[key] = v
        else:
            out[key] = str(v)[:500]
    return out


class BaseStore:
    mode = "base"

    def upsert_event(self, ev: dict, archive_ref: str) -> str:
        raise NotImplementedError

    def invalidate(self, *, event_id: Optional[str] = None, source: Optional[str] = None,
                   target: Optional[str] = None, rel_type: Optional[str] = None,
                   by_event: str = "", reason: str = "", date: str = "") -> list[str]:
        raise NotImplementedError

    def subgraph(self, *, code: Optional[str] = None, name: Optional[str] = None, hops: int = 1) -> dict:
        raise NotImplementedError

    def find_active(self, source: str, target: str, rel_type: str) -> Optional[dict]:
        """找到 (source)-[rel_type {发酵中}]->(target) 的现有边：同向证据要合并，不要重复建边。"""
        raise NotImplementedError

    def reinforce(self, edge_id: str, ev: dict, archive_ref: str) -> None:
        """把新证据挂到已有边上（多条新闻支持同一条逻辑）。"""
        raise NotImplementedError

    def edges(self) -> list[dict]:
        raise NotImplementedError

    def stats(self) -> dict:
        raise NotImplementedError

    def reset_demo(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


# --------------------------------------------------------------------------- #
# 本地 JSON 后端
# --------------------------------------------------------------------------- #
class LocalStore(BaseStore):
    mode = "local"

    def __init__(self, path: Path = LOCAL_GRAPH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"nodes": {}, "edges": {}}
        self.data.setdefault("nodes", {})
        self.data.setdefault("edges", {})

    # ---------- 内部 ----------
    def _flush(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _node_id(self, name: str, ntype: str) -> str:
        prefix = {"公司": "C", "行业": "I", "产品": "P", "事件": "E"}.get(ntype, "N")
        return f"{prefix}:{name}"

    def _ensure_node(self, name: str, ntype: str, code: str = "") -> str:
        nid = self._node_id(name, ntype)
        node = self.data["nodes"].get(nid) or {"id": nid, "name": name, "type": ntype, "code": "", "props": {}}
        if code and not node.get("code"):
            node["code"] = code
        node["updated_at"] = _now()
        self.data["nodes"][nid] = node
        return nid

    # ---------- 写 ----------
    def upsert_event(self, ev: dict, archive_ref: str) -> str:
        stype = ev.get("source_type") or "公司"
        ttype = ev.get("target_type") or "公司"
        rel = ev.get("relation") or "利好事件"
        if rel not in REL_TYPES:
            raise ValueError(f"关系类型 {rel} 不在 L0 白名单内")
        if stype not in ENTITY_TYPES or ttype not in ENTITY_TYPES:
            raise ValueError(f"实体类型 {stype}/{ttype} 不在 L0 白名单内")

        sid = self._ensure_node(ev["source"], stype, ev.get("source_code", ""))
        tid = self._ensure_node(ev["target"], ttype, ev.get("target_code", ""))
        eid = ev["event_id"]
        props = _clean_props({
            "status": ev.get("status", STATUS_ACTIVE),
            "confidence": float(ev.get("confidence", 0.7)),
            "reason": ev.get("reason", ""),
            "date": ev.get("date", ""),
            "archive_ref": archive_ref,
        })
        current = self.data["edges"].get(eid)
        self.data["edges"][eid] = {
            "id": eid, "source": sid, "target": tid, "type": rel,
            "status": props.get("status", STATUS_ACTIVE), "props": props,
            "created_at": (current or {}).get("created_at", _now()),
            "updated_at": _now(),
        }
        self._flush()
        return eid

    def invalidate(self, *, event_id=None, source=None, target=None, rel_type=None,
                   by_event="", reason="", date="") -> list[str]:
        hit = []
        for eid, e in self.data["edges"].items():
            if e.get("status") != STATUS_ACTIVE:
                continue
            if event_id and eid != event_id:
                continue
            if rel_type and e["type"] != rel_type:
                continue
            if source and self.data["nodes"][e["source"]]["name"] != source:
                continue
            if target and self.data["nodes"][e["target"]]["name"] != target:
                continue
            e["status"] = STATUS_INVALID
            e["props"].update({"status": STATUS_INVALID, "invalidated_at": date or _now(),
                               "invalidated_by": by_event, "invalidated_reason": reason})
            hit.append(eid)
        if hit:
            self._flush()
        return hit

    # ---------- 读 ----------
    def edges(self) -> list[dict]:
        out = []
        for e in self.data["edges"].values():
            s, t = self.data["nodes"].get(e["source"], {}), self.data["nodes"].get(e["target"], {})
            out.append({**e, "source_name": s.get("name", e["source"]), "target_name": t.get("name", e["target"]),
                        "source_type": s.get("type", ""), "target_type": t.get("type", "")})
        return out

    def subgraph(self, *, code=None, name=None, hops=1) -> dict:
        centers = [nid for nid, n in self.data["nodes"].items()
                   if (code and n.get("code") == code) or (name and n.get("name") == name)]
        keep = set(centers)
        for _ in range(max(1, hops)):
            for e in self.data["edges"].values():
                if e["source"] in keep or e["target"] in keep:
                    keep.add(e["source"])
                    keep.add(e["target"])
        nodes = [self.data["nodes"][n] for n in keep if n in self.data["nodes"]]
        edges = [e for e in self.edges() if e["source"] in keep and e["target"] in keep and
                 (e["source"] in centers or e["target"] in centers or hops >= 2)]
        return {"nodes": nodes, "edges": edges, "centers": centers}

    def stats(self) -> dict:
        es = self.edges()
        return {
            "mode": self.mode,
            "nodes": len(self.data["nodes"]),
            "edges": len(es),
            "active_bull": sum(1 for e in es if e["type"] == "利好事件" and e["status"] == STATUS_ACTIVE),
            "active_bear": sum(1 for e in es if e["type"] == "利空事件" and e["status"] == STATUS_ACTIVE),
            "invalidated": sum(1 for e in es if e["status"] == STATUS_INVALID),
        }

    def reset_demo(self) -> None:
        self.data = {"nodes": {}, "edges": {}}
        self._flush()

    def find_active(self, source, target, rel_type):
        nodes = self.data["nodes"]
        for e in self.data["edges"].values():
            if e["type"] != rel_type or e.get("status") != STATUS_ACTIVE:
                continue
            if (nodes.get(e["source"], {}).get("name") == source
                    and nodes.get(e["target"], {}).get("name") == target):
                return {**e, "source_name": source, "target_name": target}
        return None

    def reinforce(self, edge_id, ev, archive_ref):
        e = self.data["edges"].get(edge_id)
        if not e:
            return
        props = e["props"]
        refs = props.get("evidence_refs") or []
        if isinstance(refs, str):
            refs = [refs]
        refs.append(archive_ref)
        props.update({
            "date": ev.get("date", props.get("date", "")),
            "confidence": max(float(props.get("confidence", 0)), float(ev.get("confidence", 0.7))),
            "reason": ev.get("reason", props.get("reason", "")),
            "archive_ref": archive_ref,
            "evidence_refs": refs[-20:],
            "n_evidence": len(refs),
            "updated_at": _now(),
        })
        self._flush()


# --------------------------------------------------------------------------- #
# Neo4j 后端
# --------------------------------------------------------------------------- #
class Neo4jStore(BaseStore):
    mode = "neo4j"

    def __init__(self):
        from neo4j import GraphDatabase  # 延迟导入，local 模式不需要驱动

        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        db = NEO4J_DATABASE or None
        self._db = db
        self._ensure_constraints()

    def _session(self):
        return self.driver.session(database=self._db) if self._db else self.driver.session()

    def _ensure_constraints(self) -> None:
        for label in ("公司", "行业", "产品", "事件"):
            try:
                with self._session() as s:
                    s.run(f"CREATE CONSTRAINT `uniq_{label}` IF NOT EXISTS "
                          f"FOR (n:`{label}`) REQUIRE n.name IS UNIQUE")
            except Exception:
                pass  # 免费版/旧版本不支持时静默跳过，不影响主流程

    def upsert_event(self, ev: dict, archive_ref: str) -> str:
        stype = ev.get("source_type") or "公司"
        ttype = ev.get("target_type") or "公司"
        rel = ev.get("relation") or "利好事件"
        if rel not in REL_TYPES or stype not in ENTITY_TYPES or ttype not in ENTITY_TYPES:
            raise ValueError(f"L0 白名单校验失败：{stype}-[{rel}]->{ttype}")

        props = _clean_props({
            "status": ev.get("status", STATUS_ACTIVE),
            "confidence": float(ev.get("confidence", 0.7)),
            "reason": ev.get("reason", ""),
            "date": ev.get("date", ""),
            "archive_ref": archive_ref,
            "event_id": ev["event_id"],
        })
        cypher = f"""
        MERGE (a:`{stype}` {{name: $source}})
          ON CREATE SET a.created_at = $now
        SET a.code = coalesce($source_code, a.code), a.updated_at = $now
        MERGE (b:`{ttype}` {{name: $target}})
          ON CREATE SET b.created_at = $now
        SET b.code = coalesce($target_code, b.code), b.updated_at = $now
        MERGE (a)-[r:`{rel}` {{event_id: $eid}}]->(b)
        SET r += $props
        """
        with self._session() as s:
            s.run(cypher, source=ev["source"], source_code=ev.get("source_code") or None,
                  target=ev["target"], target_code=ev.get("target_code") or None,
                  eid=ev["event_id"], props=props, now=_now())
        return ev["event_id"]

    def invalidate(self, *, event_id=None, source=None, target=None, rel_type=None,
                   by_event="", reason="", date="") -> list[str]:
        where, params = [], {"status": STATUS_INVALID, "now": date or _now(),
                             "by": by_event, "reason": reason}
        if event_id:
            where.append("r.event_id = $eid")
            params["eid"] = event_id
        if source:
            where.append("a.name = $source")
            params["source"] = source
        if target:
            where.append("b.name = $target")
            params["target"] = target
        if rel_type:
            where.append("type(r) = $rel")
            params["rel"] = rel_type
        where.append("coalesce(r.status,'') <> $status")
        cypher = f"""
        MATCH (a)-[r]->(b) WHERE {' AND '.join(where)}
        SET r.status = $status, r.invalidated_at = $now,
            r.invalidated_by = $by, r.invalidated_reason = $reason
        RETURN r.event_id AS eid
        """
        with self._session() as s:
            return [rec["eid"] for rec in s.run(cypher, **params)]

    def edges(self) -> list[dict]:
        cypher = """
        MATCH (a)-[r]->(b)
        RETURN coalesce(r.event_id, elementId(r)) AS id, a.name AS sn, labels(a)[0] AS st,
               b.name AS tn, labels(b)[0] AS tt, type(r) AS rel, properties(r) AS props
        """
        out = []
        with self._session() as s:
            for rec in s.run(cypher):
                props = dict(rec["props"] or {})
                out.append({
                    "id": rec["id"], "source": f"n:{rec['sn']}", "target": f"n:{rec['tn']}",
                    "source_name": rec["sn"], "source_type": rec["st"], "target_name": rec["tn"],
                    "target_type": rec["tt"], "type": rec["rel"],
                    "status": props.get("status", STATUS_ACTIVE), "props": props,
                })
        return out

    def subgraph(self, *, code=None, name=None, hops=1) -> dict:
        hop = max(1, min(int(hops), 2))
        cypher = f"""
        MATCH (c:公司) WHERE c.code = $code OR c.name = $name
        CALL {{
          WITH c
          MATCH p = (c)-[*1..{hop}]-(n)
          RETURN p
          UNION
          WITH c
          RETURN NULL AS p
        }}
        WITH c, p
        WHERE p IS NOT NULL
        UNWIND relationships(p) AS r
        WITH DISTINCT r, startNode(r) AS s, endNode(r) AS e
        RETURN s.name AS sn, labels(s)[0] AS st, s.code AS sc, properties(s) AS sp,
               e.name AS en, labels(e)[0] AS et, e.code AS ec, properties(e) AS ep,
               coalesce(r.event_id, elementId(r)) AS eid, type(r) AS rel, properties(r) AS rp
        """
        nodes, edges, centers = {}, {}, []
        try:
            with self._session() as s:
                for rec in s.run(cypher, code=code or "", name=name or ""):
                    for nm, tp, cd, pr in ((rec["sn"], rec["st"], rec["sc"], rec["sp"]),
                                           (rec["en"], rec["et"], rec["ec"], rec["ep"])):
                        nodes[f"n:{nm}"] = {"id": f"n:{nm}", "name": nm, "type": tp or "公司",
                                            "code": cd or "", "props": dict(pr or {})}
                    edges[rec["eid"]] = {
                        "id": rec["eid"], "source": f"n:{rec['sn']}", "target": f"n:{rec['en']}",
                        "source_name": rec["sn"], "target_name": rec["en"],
                        "source_type": rec["st"], "target_type": rec["et"],
                        "type": rec["rel"], "status": (rec["rp"] or {}).get("status", STATUS_ACTIVE),
                        "props": dict(rec["rp"] or {}),
                    }
        except Exception as exc:  # 空图/超时都不要让 UI 崩
            return {"nodes": [], "edges": [], "centers": [], "error": str(exc), "nodes_map": {}}

        for n in nodes.values():
            if (code and n.get("code") == code) or (name and n["name"] == name):
                centers.append(n["id"])
        return {"nodes": list(nodes.values()), "edges": list(edges.values()), "centers": centers}

    def stats(self) -> dict:
        es = self.edges()
        return {
            "mode": self.mode,
            "nodes": len({e["source"] for e in es} | {e["target"] for e in es}),
            "edges": len(es),
            "active_bull": sum(1 for e in es if e["type"] == "利好事件" and e["status"] == STATUS_ACTIVE),
            "active_bear": sum(1 for e in es if e["type"] == "利空事件" and e["status"] == STATUS_ACTIVE),
            "invalidated": sum(1 for e in es if e["status"] == STATUS_INVALID),
        }

    def reset_demo(self) -> None:
        with self._session() as s:
            s.run("MATCH (n) DETACH DELETE n")

    def find_active(self, source, target, rel_type):
        cypher = """
        MATCH (a)-[r]->(b)
        WHERE a.name = $s AND b.name = $t AND type(r) = $rel AND coalesce(r.status,'') = $st
        RETURN coalesce(r.event_id, elementId(r)) AS id, properties(r) AS props
        LIMIT 1
        """
        with self._session() as s:
            rec = s.run(cypher, s=source, t=target, rel=rel_type, st=STATUS_ACTIVE).single()
        if not rec:
            return None
        return {"id": rec["id"], "props": dict(rec["props"] or {}), "type": rel_type,
                "source_name": source, "target_name": target}

    def reinforce(self, edge_id, ev, archive_ref):
        props = _clean_props({
            "date": ev.get("date", ""),
            "confidence": float(ev.get("confidence", 0.7)),
            "reason": ev.get("reason", ""),
            "archive_ref": archive_ref,
        })
        cypher = """
        MATCH ()-[r]->() WHERE coalesce(r.event_id, elementId(r)) = $eid
        SET r += $props
        SET r.evidence_refs = coalesce(r.evidence_refs, []) + $ref
        SET r.n_evidence = size(r.evidence_refs)
        """
        with self._session() as s:
            s.run(cypher, eid=edge_id, props=props, ref=archive_ref)

    def close(self) -> None:
        try:
            self.driver.close()
        except Exception:
            pass


def get_store(mode: Optional[str] = None) -> BaseStore:
    """auto: 有 Neo4j 配置且驱动可用就上 Aura，否则本地 JSON。"""
    mode = (mode or STORE_MODE).lower()
    if mode == "local":
        return LocalStore()
    if mode == "neo4j":
        return Neo4jStore()
    if has_neo4j() and importlib.util.find_spec("neo4j"):
        try:
            return Neo4jStore()
        except Exception:
            return LocalStore()
    return LocalStore()


if __name__ == "__main__":
    st = LocalStore()
    print(json.dumps(st.stats(), ensure_ascii=False, indent=2))
