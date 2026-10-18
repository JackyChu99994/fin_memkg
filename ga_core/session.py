"""会话与消息结构：OpenAI function-calling 格式。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] | None = None


class Session:
    """持有完整对话历史；工具结果按标准 role=tool 追加。"""

    def __init__(self, system_prompt: str):
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, response: LLMResponse) -> None:
        message: dict[str, Any] = {"role": "assistant", "content": response.content or ""}
        if response.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": _dumps(call.arguments)},
                }
                for call in response.tool_calls
            ]
        self.messages.append(message)

    def add_tool_result(self, call_id: str, content: str) -> None:
        self.messages.append({"role": "tool", "tool_call_id": call_id, "content": content})

    def to_messages(self) -> list[dict[str, Any]]:
        return list(self.messages)


def _dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)
