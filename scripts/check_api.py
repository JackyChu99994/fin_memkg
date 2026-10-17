"""单次 Qwen API 验证脚本：仅使用 Qwen OpenAI 兼容 Chat Completions 接口发送一次短请求验证 {"status": "ok"}。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_loop import QwenAPIError, verify_single_api_call


def main() -> int:
    try:
        res = verify_single_api_call()
        print(json.dumps({"status": res["status"], "model": res["model"], "base_url_host": res["base_url_host"]}, ensure_ascii=False, indent=2))
        return 0
    except QwenAPIError as q_err:
        print(json.dumps({"status": "error", **q_err.to_dict()}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
