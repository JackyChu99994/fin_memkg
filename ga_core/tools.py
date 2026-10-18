"""9 个原子工具的实现。

安全边界：文件与代码执行默认限制在 workspace/ 内；
code_run 会执行模型生成的任意代码，这是 Agent 的设计前提，不要对不可信任务开启。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_WORKSPACE = BASE_DIR / "workspace"
MAX_OUTPUT_CHARS = 12000


def ensure_workspace(path: Path | str | None = None) -> Path:
    workspace = Path(path).resolve() if path else DEFAULT_WORKSPACE
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def resolve_path(path: str, workspace: Path) -> Path:
    if not path or not str(path).strip():
        raise ValueError("path 不能为空")
    candidate = Path(path)
    resolved = (candidate if candidate.is_absolute() else workspace / candidate).resolve()
    if not resolved.is_relative_to(workspace):
        raise PermissionError(f"路径越出 workspace：{resolved}")
    return resolved


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[截断，共 {len(text)} 字符]"


def code_run(script: str, code_type: str = "python", timeout: int = 60, cwd: Path | str | None = None) -> dict[str, Any]:
    workspace = ensure_workspace(cwd)
    if not script or not script.strip():
        return {"status": "error", "msg": "script 为空"}
    timeout = max(1, min(int(timeout), 600))
    run_dir = workspace / ".runs"
    run_dir.mkdir(exist_ok=True)

    if code_type == "python":
        script_path = run_dir / f"run_{uuid.uuid4().hex[:8]}.py"
        script_path.write_text(script, encoding="utf-8")
        command = [sys.executable, str(script_path)]
    elif code_type in ("shell", "powershell", "bash", "sh"):
        if sys.platform == "win32" and code_type in ("shell", "powershell"):
            command = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
        else:
            command = ["bash", "-c", script]
    else:
        return {"status": "error", "msg": f"不支持的 code_type: {code_type}"}

    try:
        result = subprocess.run(
            command,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "exit_code": result.returncode,
            "stdout": _truncate(result.stdout),
            "stderr": _truncate(result.stderr),
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "msg": f"执行超时（>{timeout}s）"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "msg": f"{type(exc).__name__}: {exc}"}


def file_read(path: str, workspace: Path | str | None = None, start: int = 1, count: int = 200, keyword: str | None = None) -> dict[str, Any]:
    workspace = ensure_workspace(workspace)
    try:
        target = resolve_path(path, workspace)
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "msg": f"{type(exc).__name__}: {exc}"}

    if keyword:
        for index, line in enumerate(lines):
            if keyword.lower() in line.lower():
                lo = max(0, index - 3)
                hi = min(len(lines), index + 4)
                return {"status": "ok", "path": str(target), "match_line": index + 1, "content": _truncate("\n".join(f"{i + 1}|{lines[i]}" for i in range(lo, hi)))}
        return {"status": "not_found", "path": str(target), "keyword": keyword}

    start = max(1, int(start))
    chunk = lines[start - 1 : start - 1 + max(1, int(count))]
    numbered = "\n".join(f"{start + i}|{line}" for i, line in enumerate(chunk))
    return {"status": "ok", "path": str(target), "total_lines": len(lines), "content": _truncate(numbered)}


def file_write(path: str, content: str, workspace: Path | str | None = None, mode: str = "overwrite") -> dict[str, Any]:
    workspace = ensure_workspace(workspace)
    if not content:
        return {"status": "error", "msg": "content 为空；空写入不被接受"}
    try:
        target = resolve_path(path, workspace)
        target.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append":
            with target.open("a", encoding="utf-8") as handle:
                handle.write(content)
        elif mode == "prepend":
            old = target.read_text(encoding="utf-8") if target.exists() else ""
            target.write_text(content + old, encoding="utf-8")
        else:
            target.write_text(content, encoding="utf-8")
        return {"status": "ok", "path": str(target), "bytes": len(content.encode("utf-8")), "mode": mode}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "msg": f"{type(exc).__name__}: {exc}"}


def file_patch(path: str, old_content: str, new_content: str, workspace: Path | str | None = None) -> dict[str, Any]:
    workspace = ensure_workspace(workspace)
    if not old_content:
        return {"status": "error", "msg": "old_content 不能为空"}
    try:
        target = resolve_path(path, workspace)
        text = target.read_text(encoding="utf-8")
        occurrences = text.count(old_content)
        if occurrences != 1:
            return {"status": "error", "msg": f"old_content 出现 {occurrences} 次，必须恰好 1 次"}
        target.write_text(text.replace(old_content, new_content), encoding="utf-8")
        return {"status": "ok", "path": str(target), "replaced_chars": len(old_content)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "msg": f"{type(exc).__name__}: {exc}"}


def web_scan(url: str, max_chars: int = 20000, timeout: float = 15.0) -> dict[str, Any]:
    """基础网页读取：requests + 文本抽取。真实浏览器控制留作扩展点。"""
    if not url or not re.match(r"^https?://", url):
        return {"status": "error", "msg": "需要 http(s) URL"}
    try:
        import requests

        response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 FinMemKG/0.1"})
        html = response.text
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "msg": f"{type(exc).__name__}: {exc}"}

    title = ""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        title = re.sub(r"\s+", " ", match.group(1)).strip()
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
    except Exception:  # noqa: BLE001
        text = re.sub(r"<[^>]+>", " ", html)
    return {"status": "ok", "url": url, "http_status": response.status_code, "title": title, "content": _truncate(text.strip(), max_chars)}


def web_execute_js(script: str) -> dict[str, Any]:
    """真实浏览器 JS 执行扩展点：接入 TMWebDriver 后实现。"""
    return {
        "status": "not_configured",
        "msg": "浏览器桥未配置。当前版本请使用 web_scan 做静态读取；接入 TMWebDriver 后可执行 JS。",
        "script_preview": (script or "")[:200],
    }


def ask_user(question: str, candidates: list[str] | None = None, input_fn: Callable[[str], str] | None = None) -> dict[str, Any]:
    prompt = question or "请提供输入："
    if candidates:
        prompt += "\n候选：" + " / ".join(candidates)
    if input_fn is None:
        return {"status": "needs_user_input", "question": prompt}
    return {"status": "ok", "answer": input_fn(prompt + "\n> ")}


def update_working_checkpoint(key_info: str, working: dict[str, Any]) -> dict[str, Any]:
    if key_info:
        working["key_info"] = key_info
    return {"status": "ok", "key_info": working.get("key_info", "")}


def start_long_term_update(memory_dir: Path, turn: int, min_turn: int = 10) -> dict[str, Any]:
    """返回记忆提纯指令；真正的写入由 Agent 用 file_read/file_patch 完成。"""
    if turn < min_turn:
        return {"status": "skipped", "msg": "start_long_term_update 只在较长任务收尾时使用"}
    sop = memory_dir / "L3_skills" / "sop_memory_update.md"
    instruction = (
        "按 L0 提取本轮【事实验证成功且长期有效】的步骤，写入 L3 技能文件；"
        "先读后 patch，合并重复、压缩冗述；禁止记录临时状态、推测和未验证信息。"
        "完成后仍需向用户报告任务结果。"
    )
    return {"status": "ok", "instruction": instruction, "sop_path": str(sop), "sop_exists": sop.exists()}


TOOLS_SCHEMA: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "code_run",
        "description": "执行 Python 或 shell 代码。用于计算、数据获取、调试。单次输出有限，长任务请分步。",
        "parameters": {"type": "object", "properties": {
            "script": {"type": "string", "description": "要执行的完整代码"},
            "type": {"type": "string", "enum": ["python", "shell", "powershell"]},
            "timeout": {"type": "integer", "description": "秒，最大 600"},
        }, "required": ["script"]},
    }},
    {"type": "function", "function": {
        "name": "file_read",
        "description": "读取文件，可指定起始行、行数或关键词定位。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "start": {"type": "integer"},
            "count": {"type": "integer"}, "keyword": {"type": "string"},
        }, "required": ["path"]},
    }},
    {"type": "function", "function": {
        "name": "file_write",
        "description": "整文件写入；精细修改请用 file_patch。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"},
            "mode": {"type": "string", "enum": ["overwrite", "append", "prepend"]},
        }, "required": ["path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "file_patch",
        "description": "按 old_content 精确替换一处内容。",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "old_content": {"type": "string"}, "new_content": {"type": "string"},
        }, "required": ["path", "old_content", "new_content"]},
    }},
    {"type": "function", "function": {
        "name": "web_scan",
        "description": "读取网页标题与正文（静态请求，不含登录态）。",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "web_execute_js",
        "description": "在真实浏览器中执行 JS（需先配置浏览器桥）。",
        "parameters": {"type": "object", "properties": {"script": {"type": "string"}}, "required": ["script"]},
    }},
    {"type": "function", "function": {
        "name": "ask_user",
        "description": "向用户确认关键信息或请求授权。",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string"}, "candidates": {"type": "array", "items": {"type": "string"}},
        }, "required": ["question"]},
    }},
    {"type": "function", "function": {
        "name": "update_working_checkpoint",
        "description": "保存本任务后续需要的关键上下文。",
        "parameters": {"type": "object", "properties": {"key_info": {"type": "string"}}, "required": ["key_info"]},
    }},
    {"type": "function", "function": {
        "name": "start_long_term_update",
        "description": "任务完成或到重要检查点时，把可复用经验写入长期记忆。",
        "parameters": {"type": "object", "properties": {}},
    }},
]


def as_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)
