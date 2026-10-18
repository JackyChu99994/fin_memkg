"""命令行入口：python -m ga_core.cli "你的任务" [--fake]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .handler import AgentHandler
from .llm import FakeClient, OpenAICompatibleClient, load_config
from .loop import AgentLoop
from .memory import build_system_prompt
from .session import LLMResponse, ToolCall


def _fake_client(workspace: Path) -> FakeClient:
    demo_path = str(workspace / "demo_note.txt")
    return FakeClient(
        [
            LLMResponse(
                content="<summary>写入演示文件</summary>",
                tool_calls=[ToolCall(id="call_1", name="file_write", arguments={"path": demo_path, "content": "GA 框架自检成功\n"})],
            ),
            LLMResponse(
                content="<summary>读取并确认</summary>",
                tool_calls=[ToolCall(id="call_2", name="file_read", arguments={"path": demo_path})],
            ),
            LLMResponse(content="框架自检完成：写入并读回了 demo_note.txt。"),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fin-MemKG GenericAgent 内核")
    parser.add_argument("task", nargs="?", default="验证框架是否可用")
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--fake", action="store_true", help="不调用 API，用脚本化响应自检")
    parser.add_argument("--no-l1", action="store_true", help="系统提示不加载 L1 索引")
    parser.add_argument("--json", action="store_true", help="只输出最终 JSON")
    args = parser.parse_args()

    handler = AgentHandler(workspace=args.workspace, verbose=not args.json)
    workspace = handler.workspace

    if args.fake:
        client = _fake_client(workspace)
    else:
        config = load_config()
        if not config.ready:
            print("缺少 QWEN_API_KEY：请在 .env 或环境变量中配置，或先用 --fake 自检。", file=sys.stderr)
            return 2
        client = OpenAICompatibleClient(config)

    loop = AgentLoop(
        client=client,
        handler=handler,
        system_prompt=build_system_prompt(include_l1=not args.no_l1),
        max_turns=args.max_turns,
        verbose=not args.json,
    )
    result = loop.run(args.task)
    print(json.dumps({"result": result["result"], "turns": result["turns"], "content": result["content"], "working": result["working"]}, ensure_ascii=False, indent=2))
    return 0 if result["result"] == "DONE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
