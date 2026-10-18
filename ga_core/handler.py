"""工具调度：把 LLM 的 tool_call 映射到具体实现。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import tools
from .session import LLMResponse


@dataclass
class ToolOutcome:
    data: Any
    next_prompt: str | None = None
    should_exit: bool = False


class AgentHandler:
    def __init__(
        self,
        workspace: Path | str | None = None,
        memory_dir: Path | str | None = None,
        input_fn: Callable[[str], str] | None = None,
        verbose: bool = True,
    ):
        self.workspace = tools.ensure_workspace(workspace)
        self.memory_dir = Path(memory_dir).resolve() if memory_dir else tools.BASE_DIR / "memory"
        self.input_fn = input_fn
        self.verbose = verbose
        self.working: dict[str, Any] = {}
        self.current_turn = 0
        self.trace: list[dict[str, Any]] = []

    def dispatch(self, name: str, args: dict[str, Any], response: LLMResponse | None = None) -> ToolOutcome:
        self.trace.append({"turn": self.current_turn, "tool": name, "args": _preview(args)})
        if "_invalid_json" in args:
            return ToolOutcome({"status": "error", "msg": "工具参数不是合法 JSON，请重新调用"}, next_prompt="工具参数解析失败，请修正后重试。")

        try:
            if name == "code_run":
                data = tools.code_run(args.get("script", ""), args.get("type", "python"), args.get("timeout", 60), self.workspace)
            elif name == "file_read":
                data = tools.file_read(args.get("path", ""), self.workspace, args.get("start", 1), args.get("count", 200), args.get("keyword"))
            elif name == "file_write":
                data = tools.file_write(args.get("path", ""), args.get("content", ""), self.workspace, args.get("mode", "overwrite"))
            elif name == "file_patch":
                data = tools.file_patch(args.get("path", ""), args.get("old_content", ""), args.get("new_content", ""), self.workspace)
            elif name == "web_scan":
                data = tools.web_scan(args.get("url", ""))
            elif name == "web_execute_js":
                data = tools.web_execute_js(args.get("script", ""))
            elif name == "ask_user":
                data = tools.ask_user(args.get("question", ""), args.get("candidates"), self.input_fn)
                if data.get("status") == "needs_user_input":
                    return ToolOutcome(data, should_exit=True)
            elif name == "update_working_checkpoint":
                data = tools.update_working_checkpoint(args.get("key_info", ""), self.working)
            elif name == "start_long_term_update":
                data = tools.start_long_term_update(self.memory_dir, self.current_turn)
            else:
                return ToolOutcome({"status": "error", "msg": f"未知工具：{name}"}, next_prompt=f"未知工具 {name}，请改用已提供的工具。")
        except Exception as exc:  # noqa: BLE001 - 工具异常必须回灌给模型
            return ToolOutcome({"status": "error", "msg": f"{type(exc).__name__}: {exc}"}, next_prompt="工具执行失败，请读取错误后调整。")

        next_prompt = None
        if name == "start_long_term_update" and data.get("status") == "ok":
            next_prompt = data["instruction"] + f"（SOP: {data['sop_path']}）"
        return ToolOutcome(data, next_prompt=next_prompt)


def _preview(args: dict[str, Any], limit: int = 160) -> str:
    text = json.dumps(args, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "..."
