"""单次 Qwen API 验证脚本：仅使用 Qwen OpenAI 兼容 Chat Completions 接口发送一次短请求验证 {"status": "ok"}。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_loop import QwenAPIError, verify_single_api_call


def main() -> int:
    try:
        res = verify_single_api_call()
        base_url = str(res.get("base_url", ""))
        host = urlparse(base_url).netloc or base_url
        print(
            json.dumps(
                {
                    "ok": bool(res.get("ok")),
                    "status": "ok" if res.get("ok") else "failed",
                    "model": res.get("model"),
                    "base_url": base_url,
                    "base_url_host": host,
                    "latency_ms": res.get("latency_ms"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if res.get("ok") else 1
    except QwenAPIError as q_err:
        print(json.dumps({"ok": False, "status": "error", **q_err.to_dict()}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "error", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
