"""L0–L4 分层记忆的读取与系统提示拼装。

沿用项目现有目录：memory/L0_meta_rules.md、L1_insight_index.md、
L2_graphs/*.json、L3_skills/*.md、L4_archive/。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_DIR = BASE_DIR / "memory"
L0_PATH = MEMORY_DIR / "L0_meta_rules.md"
L1_PATH = MEMORY_DIR / "L1_insight_index.md"
L2_DIR = MEMORY_DIR / "L2_graphs"
L3_DIR = MEMORY_DIR / "L3_skills"
L4_DIR = MEMORY_DIR / "L4_archive"


def _read(path: Path, limit: int | None = None) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return text[:limit] if limit else text


def load_l0() -> str:
    return _read(L0_PATH)


def load_l1(limit: int = 2000) -> str:
    return _read(L1_PATH, limit=limit)


def list_skills() -> list[str]:
    if not L3_DIR.exists():
        return []
    return sorted(path.name for path in L3_DIR.glob("*.md"))


def load_skill(name: str) -> str:
    return _read(L3_DIR / name)


def load_l2_graph(stock_code: str) -> dict[str, Any] | None:
    path = L2_DIR / f"{stock_code}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def recent_l4_events(stock_code: str, limit: int = 10) -> list[dict[str, Any]]:
    path = L4_DIR / f"{stock_code}_events.jsonl"
    if not path.exists():
        return []
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return events[-limit:]


def crystallize_skill(name: str, content: str) -> Path:
    """把一段可复用流程写成 L3 技能文件。文件名需以 .md 结尾。"""
    if not name.endswith(".md"):
        name += ".md"
    L3_DIR.mkdir(parents=True, exist_ok=True)
    path = L3_DIR / name
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


SYSTEM_TEMPLATE = """# Role: 金融项目考古与量化分析 Agent
你拥有文件读写、代码执行、网页读取的工具权限。不要空想，用工具探测现实。

## 硬约束（L0）
{l0}

## 行动原则
- 每轮回复开头用 <summary> 写不超过 30 字的进展总结。
- 先探测再行动：失败时先读错误、查环境，再重试或换方案；不可逆操作先 ask_user。
- 失败升级：1 次读错误，2 次探测环境，3 次换方案或询问用户。禁止无新信息的重复尝试。
- 所有金融分析必须锚定 as_of_date，严格禁止使用该日期之后的信息（前视偏差）。
- 结论必须能追溯到证据：文件路径、行号、事件 ID 或数据来源，不得编造。
- 能查明或安全推断的不要问用户；只就用户独有事实、授权或高影响分歧提问。

## 可用记忆
- L2 图谱：memory/L2_graphs/<股票代码>.json
- L3 技能：memory/L3_skills/*.md（{skills}）
- L4 归档：memory/L4_archive/<股票代码>_events.jsonl

## L1 索引
{l1}
"""


def build_system_prompt(include_l1: bool = True, max_l1_chars: int = 2000) -> str:
    skills = "、".join(list_skills()) or "暂无"
    return SYSTEM_TEMPLATE.format(
        l0=load_l0() or "（L0 规则文件缺失）",
        l1=load_l1(limit=max_l1_chars) if include_l1 else "（按需读取）",
        skills=skills,
    )
