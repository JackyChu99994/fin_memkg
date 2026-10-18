#!/usr/bin/env python3
"""
Fin-MemKG 真实 Qwen API 三场景冒烟测试脚本 (scripts/smoke_demo.py)
- 复用 app.py 预设场景 A / B / C（标的 300308.SZ 中际旭创，基准日 2026-10-14）；
- 对每个场景调用 run_agent_pipeline(..., use_cache=False, persist=False)；
- 验证：
  * 场景 A：t5_forecast.direction != "BULLISH" 且无异常；
  * 场景 B：存在 PRICED_IN 操作且 t5_forecast.direction == "BEARISH"；
  * 场景 C：contagion_paths[0].path_factor < 0 且 t5_forecast.direction == "BEARISH"；
- 打印每个场景的 latency_ms、prompt/completion tokens、finish_reason、retry_count；
- 任一失败以 exit(1) 退出。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent_loop import QwenAPIError, load_qwen_config, run_agent_pipeline

SCENARIOS = [
    (
        "Scenario A (逻辑反转 / Blackwell推迟)",
        {
            "published_at": "2026-10-14 09:30:00",
            "source": "海外供应链核心快讯",
            "title": "英伟达Blackwell B200机柜因连接器与散热背板公差缺陷推迟大批量交付一个季度",
            "content": "受机柜散热方案改版影响，北美云厂商配套1.6T光模块集中提货节点顺延至明年Q2。",
            "evidence_type": "EMPIRICAL_NEWS_FILING",
        },
    ),
    (
        "Scenario B (利好出尽 / PRICED_IN)",
        {
            "published_at": "2026-10-14 09:30:00",
            "source": "深交所业绩预告",
            "title": "中际旭创披露前三季度净利预增165%，符合卖方一致预期上限",
            "content": "公司800G出货保持高景气，但前期股价已连续大涨28%，处于60日96%极高分位，获利盘兑现压力显著。",
            "evidence_type": "EMPIRICAL_NEWS_FILING",
        },
    ),
    (
        "Scenario C (两跳传导 / InP停产->EML紧缺)",
        {
            "published_at": "2026-10-14 09:30:00",
            "source": "海外光电产业链快讯",
            "title": "上游磷化铟(InP)晶圆外延片大厂产线停产检修两周，Lumentum 200G EML光芯片现货跳涨15%",
            "content": "磷化铟衬底短缺传导至中游EML光芯片制造商Lumentum，导致下游800G/1.6T光模块厂面临物料配额收紧。",
            "evidence_type": "EMPIRICAL_NEWS_FILING",
        },
    ),
]


def main() -> int:
    cfg = load_qwen_config()
    if not cfg["ready"]:
        missing = ", ".join(cfg["missing_fields"])
        print(f"[SMOKE FAIL] 缺少 Qwen 配置项: {missing}", file=sys.stderr)
        return 1

    print(
        f"=== Fin-MemKG Live Qwen Smoke Test | model={cfg['model']} | base_url={cfg['base_url']} ==="
    )
    failures: list[str] = []

    for idx, (label, ev) in enumerate(SCENARIOS, start=1):
        t0 = time.time()
        try:
            out = run_agent_pipeline(
                stock_code="300308.SZ",
                new_event=ev,
                as_of_date="2026-10-14",
                stock_name="中际旭创",
                persist=False,
                use_cache=False,
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            meta = out.get("execution_meta", {})
            inf = out["inference"]
            t1_dir = inf.t1_forecast.direction
            t5_dir = inf.t5_forecast.direction
            ops_summary = [op.op for op in inf.patch_ops]
            paths = out.get("contagion_paths") or []
            pf_str = f"{paths[0]['path_factor']:+.4f}" if paths else "N/A"

            print(
                f"[{idx}/3] {label}\n"
                f"      latency_ms={meta.get('latency_ms') or elapsed_ms} | "
                f"prompt_tokens={meta.get('prompt_tokens')} | "
                f"completion_tokens={meta.get('completion_tokens')} | "
                f"finish_reason={meta.get('finish_reason')} | "
                f"retry_count={meta.get('retry_count', 0)} | "
                f"json_repaired={meta.get('json_repaired', False)}\n"
                f"      T+1={t1_dir} | T+5={t5_dir} | impact={inf.impact_direction} | "
                f"ops={ops_summary} | path_factor={pf_str} | "
                f"score={out['score_before']:+.2f}->{out['score_after']:+.2f}"
            )

            if idx == 1:
                if t5_dir == "BULLISH":
                    failures.append(f"{label}: 期望 T+5 != BULLISH，实际得到 {t5_dir}")
            elif idx == 2:
                has_priced_in = any(op.op == "PRICED_IN" for op in inf.patch_ops)
                if not has_priced_in:
                    failures.append(f"{label}: 期望包含 PRICED_IN 操作，实际 ops={ops_summary}")
                if t5_dir != "BEARISH":
                    failures.append(f"{label}: 期望 T+5 == BEARISH，实际得到 {t5_dir}")
            elif idx == 3:
                if not paths or float(paths[0]["path_factor"]) >= 0:
                    failures.append(f"{label}: 期望 contagion_paths[0].path_factor < 0，实际={pf_str}")
                if t5_dir != "BEARISH":
                    failures.append(f"{label}: 期望 T+5 == BEARISH，实际得到 {t5_dir}")

        except QwenAPIError as err:
            failures.append(f"{label}: QwenAPIError [{err.error_type}] {err.message}")
            print(f"[{idx}/3] {label} -> FAILED: [{err.error_type}] {err.message}", file=sys.stderr)
        except Exception as exc:
            failures.append(f"{label}: Unexpected {type(exc).__name__}: {exc}")
            print(f"[{idx}/3] {label} -> FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)

    if failures:
        print("\n=== SMOKE TEST FAILED ===", file=sys.stderr)
        for msg in failures:
            print(f" - {msg}", file=sys.stderr)
        return 1

    print("\n=== SMOKE TEST PASSED (3/3 Scenarios OK) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
