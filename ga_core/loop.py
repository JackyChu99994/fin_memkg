"""通用 Agent 循环：感知 → 推理 → 调工具 → 回灌结果 → 继续，直到无工具调用或达到上限。"""
from __future__ import annotations

from typing import Any, Callable

from .handler import AgentHandler
from .session import Session
from .tools import TOOLS_SCHEMA, as_text


class AgentLoop:
    def __init__(
        self,
        client: Any,
        handler: AgentHandler,
        system_prompt: str,
        tools_schema: list[dict[str, Any]] | None = None,
        max_turns: int = 40,
        verbose: bool = True,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.client = client
        self.handler = handler
        self.system_prompt = system_prompt
        self.tools_schema = tools_schema or TOOLS_SCHEMA
        self.max_turns = max_turns
        self.verbose = verbose
        self.on_event = on_event

    def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event:
            self.on_event(event)
        elif self.verbose:
            kind = event.get("type")
            if kind == "turn":
                print(f"\n--- turn {event['turn']} ---")
            elif kind == "tool":
                print(f"  [tool] {event['name']} {event['args'][:120]}")
            elif kind == "tool_result":
                print(f"  [result] {event['status']} {event['preview'][:200]}")
            elif kind == "final":
                print(f"\n[done] {event['content'][:1000]}")

    def run(self, user_input: str) -> dict[str, Any]:
        session = Session(self.system_prompt)
        session.add_user(user_input)
        last_content = ""

        for turn in range(1, self.max_turns + 1):
            self.handler.current_turn = turn
            self._emit({"type": "turn", "turn": turn})
            response = self.client.chat(session.to_messages(), self.tools_schema)
            session.add_assistant(response)
            last_content = response.content or last_content

            if not response.tool_calls:
                self._emit({"type": "final", "content": response.content or ""})
                return {"result": "DONE", "turns": turn, "content": response.content, "working": self.handler.working}

            next_prompts: list[str] = []
            for call in response.tool_calls:
                self._emit({"type": "tool", "turn": turn, "name": call.name, "args": str(call.arguments)[:300]})
                outcome = self.handler.dispatch(call.name, call.arguments, response)
                session.add_tool_result(call.id, as_text(outcome.data))
                status = outcome.data.get("status", "ok") if isinstance(outcome.data, dict) else "ok"
                self._emit({"type": "tool_result", "turn": turn, "name": call.name, "status": status, "preview": as_text(outcome.data)})

                if outcome.should_exit:
                    return {"result": "WAITING_USER", "turns": turn, "content": as_text(outcome.data), "working": self.handler.working}
                if outcome.next_prompt:
                    next_prompts.append(outcome.next_prompt)

            if next_prompts:
                session.add_user("\n\n".join(next_prompts))

        return {"result": "MAX_TURNS_EXCEEDED", "turns": self.max_turns, "content": last_content, "working": self.handler.working}
