# -*- coding: utf-8 -*-
"""可视化层：把 L2 子图渲染成 pyvis 的交互 HTML / Mermaid 文本。

颜色约定（A 股习惯）：
    利好事件 = 红，利空事件 = 绿，已被证伪 = 灰色虚线
    节点：公司=蓝，行业=橙，产品=紫，事件=青
"""
from __future__ import annotations

import html
import json
from typing import Optional

from config import (COLOR_INVALID, NODE_COLOR, REL_COLOR, STATUS_ACTIVE,
                    STATUS_INVALID)

NODE_SIZE = {"公司": 26, "行业": 20, "产品": 16, "事件": 16}

VIS_OPTIONS = {
    "physics": {
        "enabled": True,
        "barnesHut": {"gravitationalConstant": -9000, "springLength": 150,
                      "springConstant": 0.03, "damping": 0.25},
        "stabilization": {"iterations": 240},
    },
    "interaction": {"hover": True, "tooltipDelay": 120, "navigationButtons": False},
    "edges": {"smooth": {"type": "continuous", "roundness": 0.25}, "arrows": {"to": {"enabled": True, "scaleFactor": 0.7}}},
    "nodes": {"font": {"size": 15, "face": "Microsoft YaHei, PingFang SC, sans-serif"}},
}


def _edge_style(edge: dict, highlight: bool) -> dict:
    status = edge.get("status", STATUS_ACTIVE)
    if status == STATUS_INVALID:
        return {"color": COLOR_INVALID, "dashes": True, "width": 1.5}
    color = REL_COLOR.get(edge["type"], "#8b949e")
    return {"color": color, "dashes": False, "width": 4.5 if highlight else 2.4}


def _tooltip_node(node: dict) -> str:
    lines = [f"<b>{html.escape(node.get('name',''))}</b>",
             f"类型：{node.get('type','')}"]
    if node.get("code"):
        lines.append(f"代码：{node['code']}")
    props = node.get("props") or {}
    if props.get("updated_at"):
        lines.append(f"更新时间：{props['updated_at']}")
    return "<br>".join(lines)


def _tooltip_edge(edge: dict) -> str:
    p = edge.get("props") or {}
    lines = [f"<b>{html.escape(edge['source_name'])} → {html.escape(edge['target_name'])}</b>",
             f"关系：{edge['type']}",
             f"状态：{p.get('status', edge.get('status',''))}",
             f"日期：{p.get('date','')}",
             f"置信度：{p.get('confidence','')}"]
    if p.get("reason"):
        lines.append(f"理由：{html.escape(str(p['reason']))}")
    if p.get("archive_ref"):
        lines.append(f"证据：{html.escape(str(p['archive_ref']))}")
    if p.get("invalidated_by"):
        lines.append(f"被谁推翻：{html.escape(str(p['invalidated_by']))}")
    return "<br>".join(lines)


def build_network_html(subgraph: dict, *, height: int = 560,
                       highlight_ids: Optional[set[str]] = None,
                       title: str = "") -> str:
    """返回可塞进 st.components.v1.html 的完整 HTML。"""
    nodes = subgraph.get("nodes", [])
    edges = subgraph.get("edges", [])
    highlight_ids = highlight_ids or set()

    try:
        from pyvis.network import Network
    except ImportError:
        return ("<div style='padding:24px;font-family:sans-serif;color:#c9d1d9;background:#0d1117'>"
                "<b>缺少 pyvis</b>：请先执行 <code>pip install pyvis</code>，"
                "或使用下方 Mermaid 文本视图。</div>")

    net = Network(height=f"{height}px", width="100%", bgcolor="#0d1117",
                  font_color="#e6edf3", directed=True, cdn_resources="in_line")
    net.set_options(json.dumps(VIS_OPTIONS))

    centers = set(subgraph.get("centers") or [])
    degree: dict[str, int] = {}
    for e in edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1

    for n in nodes:
        ntype = n.get("type", "公司")
        color = NODE_COLOR.get(ntype, "#8b949e")
        is_center = n["id"] in centers
        size = NODE_SIZE.get(ntype, 18) + min(10, degree.get(n["id"], 0) * 2)
        if is_center:
            size += 8
        net.add_node(
            n["id"],
            label=n.get("name", n["id"]),
            title=_tooltip_node(n),
            color={"background": color, "border": "#ffffff" if is_center else color,
                   "highlight": {"background": color, "border": "#ffffff"}},
            borderWidth=3 if is_center else 1,
            size=size,
            shape="dot",
        )

    for e in edges:
        style = _edge_style(e, e["id"] in highlight_ids)
        label = f"{e['type']}" + ("（已被证伪）" if e.get("status") == STATUS_INVALID else "")
        net.add_edge(
            e["source"], e["target"],
            label=label,
            title=_tooltip_edge(e),
            color=style["color"],
            width=style["width"],
            dashes=style["dashes"],
            arrows="to",
            font={"size": 11, "color": "#9aa4b2", "strokeWidth": 0},
        )

    body = net.generate_html(notebook=False)
    legend = _legend_html(len(nodes), len(edges), sum(1 for e in edges if e.get("status") == STATUS_INVALID))
    head = f"<div style='font:600 14px/1.4 sans-serif;color:#e6edf3;padding:0 0 6px 2px'>{html.escape(title)}</div>" if title else ""
    return legend + head + body


def _legend_html(n: int, e: int, inv: int) -> str:
    chip = ("display:inline-block;margin-right:14px;font:12px/1.6 sans-serif;color:#c9d1d9")
    dot = "display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px"
    return f"""
<div style="font:12px/1.8 sans-serif;color:#9aa4b2;background:#0d1117;padding:6px 2px 0">
  <span style="{chip}">节点 {n} · 边 {e} · 已证伪 {inv}</span>
  <span style="{chip}"><i style="{dot};background:#4c8dff"></i>公司</span>
  <span style="{chip}"><i style="{dot};background:#f5a524"></i>行业</span>
  <span style="{chip}"><i style="{dot};background:#9b6dff"></i>产品</span>
  <span style="{chip}"><i style="display:inline-block;width:14px;height:3px;background:#e5484d;margin-right:5px;vertical-align:middle"></i>利好</span>
  <span style="{chip}"><i style="display:inline-block;width:14px;height:3px;background:#30a46c;margin-right:5px;vertical-align:middle"></i>利空</span>
  <span style="{chip}"><i style="display:inline-block;width:14px;height:0;border-top:2px dashed #8b8b8b;margin-right:5px;vertical-align:middle"></i>已被证伪</span>
</div>"""


def mermaid_source(subgraph: dict) -> str:
    """给报告/PPT 用的静态图（Mermaid），不依赖浏览器。"""
    def nid(raw: str) -> str:
        return "n" + "".join(ch if ch.isalnum() else "_" for ch in raw)

    lines = ["graph LR"]
    for n in subgraph.get("nodes", []):
        lines.append(f'  {nid(n["id"])}["{n.get("name","")}<br/>{n.get("type","")}"]')
    for e in subgraph.get("edges", []):
        arrow = "-.->" if e.get("status") == STATUS_INVALID else "-->"
        label = e["type"] + ("(已被证伪)" if e.get("status") == STATUS_INVALID else "")
        lines.append(f'  {nid(e["source"])} {arrow}|{label}| {nid(e["target"])}')
    lines += [
        "  classDef company fill:#4c8dff,color:#fff;",
        "  classDef industry fill:#f5a524,color:#000;",
        "  classDef product fill:#9b6dff,color:#fff;",
    ]
    return "\n".join(lines)
