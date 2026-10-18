"""LLM 适配层：Qwen / 任意 OpenAI 兼容 Chat Completions 接口。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .session import LLMResponse, ToolCall

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-plus"


@dataclass
class LLMConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    max_tokens: int = 4096
    temperature: float = 0.2

    @property
    def ready(self) -> bool:
        return bool(self.api_key)


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_config(dotenv_path: Path | None = None) -> LLMConfig:
    """系统环境变量优先，其次项目根目录 .env。"""
    dotenv = _read_dotenv(dotenv_path or BASE_DIR / ".env")

    def get(name: str, default: str = "") -> str:
        return os.environ.get(name) or dotenv.get(name) or default

    return LLMConfig(
        api_key=get("QWEN_API_KEY"),
        base_url=get("QWEN_BASE_URL", DEFAULT_BASE_URL),
        model=get("QWEN_MODEL", DEFAULT_MODEL),
    )


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig, timeout: float = 60.0):
        if not config.ready:
            raise RuntimeError("缺少 QWEN_API_KEY：请在 .env 或系统环境变量中配置")
        from openai import OpenAI

        self.config = config
        self._client = OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=timeout, max_retries=0)

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        calls: list[ToolCall] = []
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {"_invalid_json": call.function.arguments}
            calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
        usage = getattr(response, "usage", None)
        return LLMResponse(
            content=message.content or "",
            tool_calls=calls,
            usage={"prompt": usage.prompt_tokens, "completion": usage.completion_tokens} if usage else None,
        )


class FakeClient:
    """测试用：按脚本依次返回响应，不发起网络请求。"""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self.calls: list[list[dict[str, Any]]] = []

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> LLMResponse:
        self.calls.append(messages)
        if not self._responses:
            return LLMResponse(content="done")
        return self._responses.pop(0)
