from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import ssl
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Type

from pydantic import BaseModel, ValidationError

from prompts import (
    INPUT_SCHEMA_VERSION,
    build_belief_revision_prompt,
    build_cold_start_prompt,
    build_demo_event_prompt,
)
from schema import (
    DemoEntity,
    DemoEventAnalysis,
    Edge,
    ExecutionMeta,
    HorizonPred,
    InferenceResponse,
    L2Graph,
    MarketRegime,
    PatchOp,
    ThesisNode,
    check_inference_consistency,
)
from tools import (
    CACHE_DIR,
    L1_INDEX_PATH,
    L2_DIR,
    L4_DIR,
    classify_event_polarity,
    fetch_market_data,
    find_contagion_paths,
    load_l2_graph,
    patch_l2_graph,
    query_l4_archive,
    record_l4_event,
    verify_priced_in,
)

logger = logging.getLogger("fin_memkg.agent_loop")

PROJECT_DIR = Path(__file__).resolve().parent
DEMO_CACHE_DIR = PROJECT_DIR / "memory" / "demo_cache"
GRAPH_DEMO_CACHE_DIR = PROJECT_DIR / "memory" / "graph_demo_cache"
EVAL_LLM_CACHE_DIR = PROJECT_DIR / "memory" / "eval_llm_cache"

DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_QWEN_MODEL = "qwen-plus"

SINGLE_MAX_TOKENS = 1200
GRAPH_MAX_TOKENS = 2600
GRAPH_MAX_TOKENS_RETRY = 4096
LLM_TIMEOUT = 60.0

# Compatibility constants for eval_benchmark.py
DEFAULT_MAX_TOKENS = GRAPH_MAX_TOKENS
DEFAULT_MAX_TOKENS_RETRY = GRAPH_MAX_TOKENS_RETRY
DEFAULT_TIMEOUT = LLM_TIMEOUT
DEFAULT_MAX_RETRIES = 1
DEFAULT_TEMPERATURE = 0.0

RETRY_COMPACT_SUFFIX = (
    "\n\n只输出紧凑 JSON；每条 reason/reasoning 不超过 80 个汉字；"
    "patch_ops 最多 3 条；watch_indicators 最多 3 条"
)

BEAR_KWS = (
    "砍单", "下调", "推迟", "调查", "短缺", "下滑", "关税",
    "跌破", "利空", "减持", "停产", "检修", "跳涨", "断供",
)
BULL_KWS = (
    "超预期", "突破", "大单", "预增", "回暖", "提价", "上调",
    "放量", "中标", "利好", "满产", "扩产", "让利",
)

DEFAULT_SAMPLE_EVENT: Dict[str, Any] = {
    "event_id": "EV_20261014_01_demo",
    "stock_code": "300308.SZ",
    "stock_name": "中际旭创",
    "published_at": "2026-10-14 09:30:00",
    "source": "海外供应链核心快讯",
    "title": "英伟达Blackwell B200机柜因连接器与散热背板公差缺陷推迟大批量交付一个季度",
    "content": "受机柜散热方案改版影响，北美云厂商配套1.6T光模块集中提货节点顺延至明年Q2。",
    "evidence_type": "EMPIRICAL_NEWS_FILING",
}


class QwenAPIError(RuntimeError):
    """Structured error carrying error category, raw reason, retryability, and actionable next-step hint."""

    def __init__(
        self,
        error_type: str,
        message: str,
        hint: str,
        status_code: Optional[int] = None,
        raw_output: Optional[str] = None,
        retryable: bool = False,
        finish_reason: Optional[str] = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.hint = hint
        self.status_code = status_code
        self.raw_output = raw_output
        self.retryable = retryable
        self.finish_reason = finish_reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "message": self.message,
            "hint": self.hint,
            "status_code": self.status_code,
            "raw_output": self.raw_output,
            "retryable": self.retryable,
            "finish_reason": self.finish_reason,
        }


LLMExecutionError = QwenAPIError


def _estimate_tokens(text: str) -> int:
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    other_tokens = len(re.findall(r"[A-Za-z0-9_]+|[^\s\u4e00-\u9fff]", text))
    return max(1, int(round(cjk_chars * 0.65 + other_tokens * 0.85)))


def _count_tokens(sys_prompt: str, usr_prompt: str = "") -> int:
    return _estimate_tokens(f"{sys_prompt}\n{usr_prompt}")


def _read_dotenv_file(dotenv_path: Optional[Path] = None) -> Dict[str, str]:
    env_file = dotenv_path or (PROJECT_DIR / ".env")
    values: Dict[str, str] = {}
    if not env_file.exists():
        return values
    try:
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k:
                values[k] = v
    except Exception:
        pass
    return values


def load_qwen_config(dotenv_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Strictly read ONLY:
    - QWEN_API_KEY
    - QWEN_BASE_URL (default: https://dashscope.aliyuncs.com/compatible-mode/v1)
    - QWEN_MODEL (default: qwen-plus)

    Priority:
    1. System environment variables (os.environ)
    2. Project root .env file
    Does NOT read or infer OPENAI_*, LLM_*, DEEPSEEK_*, or OPENAI_WIRE_API.
    Never prints or exposes the API key value.
    """
    dotenv_vals = _read_dotenv_file(dotenv_path=dotenv_path)

    def _get_var(name: str, default: str = "") -> str:
        env_val = os.environ.get(name, "").strip()
        if env_val:
            return env_val
        file_val = dotenv_vals.get(name, "").strip()
        if file_val:
            return file_val
        return default

    api_key = _get_var("QWEN_API_KEY", "")
    base_url = _get_var("QWEN_BASE_URL", DEFAULT_QWEN_BASE_URL)
    model = _get_var("QWEN_MODEL", DEFAULT_QWEN_MODEL)

    missing_fields = []
    if not api_key:
        missing_fields.append("QWEN_API_KEY")
    if not base_url:
        missing_fields.append("QWEN_BASE_URL")
    if not model:
        missing_fields.append("QWEN_MODEL")

    return {
        "api_key": api_key,
        "has_api_key": bool(api_key),
        "base_url": base_url,
        "model": model,
        "missing_fields": missing_fields,
        "ready": len(missing_fields) == 0,
    }


resolve_llm_config = load_qwen_config


def load_sample_demo_event() -> Dict[str, Any]:
    """Load the default fixed sample financial event from memory/L4_archive/300308.SZ_events.jsonl or fallback constant."""
    jsonl_path = L4_DIR / "300308.SZ_events.jsonl"
    if jsonl_path.exists():
        try:
            lines = [ln.strip() for ln in jsonl_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            if lines:
                item = json.loads(lines[-1])
                return {
                    "event_id": item.get("event_id", DEFAULT_SAMPLE_EVENT["event_id"]),
                    "stock_code": item.get("stock_code", "300308.SZ"),
                    "stock_name": "中际旭创",
                    "published_at": item.get("published_at", DEFAULT_SAMPLE_EVENT["published_at"]),
                    "source": item.get("source", DEFAULT_SAMPLE_EVENT["source"]),
                    "title": item.get("title", DEFAULT_SAMPLE_EVENT["title"]),
                    "content": item.get("snippet", DEFAULT_SAMPLE_EVENT["content"]),
                    "evidence_type": item.get("evidence_type", "EMPIRICAL_NEWS_FILING"),
                }
        except Exception:
            pass
    return dict(DEFAULT_SAMPLE_EVENT)


def _extract_json_block(text: str) -> str:
    cleaned = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1]
    return cleaned


def _repair_truncated_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    仅用于修补“最后一小段闭合符被截断”的 JSON 字符串（例如末尾缺少引号、] 或 }）。
    若核心预测字段（t1_forecast / t5_forecast / t20_forecast）尚未输出，则拒绝修补并返回 None。
    """
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    if start == -1:
        return None
    fragment = cleaned[start:]

    if not all(k in fragment for k in ("t1_forecast", "t5_forecast", "t20_forecast")):
        return None

    for cut_back in range(0, min(120, len(fragment))):
        candidate = fragment if cut_back == 0 else fragment[:-cut_back].rstrip()
        candidate = re.sub(r"[,:\s]+$", "", candidate)
        if not candidate:
            continue

        in_str = False
        escape = False
        stack: list[str] = []
        for ch in candidate:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str:
                if ch in "{[":
                    stack.append("}" if ch == "{" else "]")
                elif ch in "}]" and stack and stack[-1] == ch:
                    stack.pop()

        closing = ('"' if in_str else "") + "".join(reversed(stack))
        test_str = candidate + closing
        try:
            obj = json.loads(test_str)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def _create_qwen_openai_client(api_key: str, base_url: str, timeout: float = LLM_TIMEOUT):
    from openai import DefaultHttpxClient, OpenAI

    http_client = None
    try:
        import certifi

        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        http_client = DefaultHttpxClient(verify=ssl_ctx, timeout=timeout)
    except Exception:
        http_client = None

    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        max_retries=0,
        timeout=timeout,
        http_client=http_client,
    )


def call_qwen_json(
    prompt: str,
    input_text: str,
    max_tokens: int = SINGLE_MAX_TOKENS,
    timeout: float = LLM_TIMEOUT,
    response_format: Optional[Dict[str, Any]] = None,
    client_factory: Optional[Callable[[str, str, float], Any]] = None,
    dotenv_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Single-request Qwen OpenAI-compatible Chat Completions JSON caller:
    - Uses client.chat.completions.create(..., temperature=0, max_tokens=max_tokens)
    - Passes response_format ONLY when response_format is not None
    - Checks response.choices[0].finish_reason; if finish_reason == "length", immediately raises
      QwenAPIError(error_type="输出被截断", retryable=True) without attempting json.loads
    - Raises QwenAPIError with clear classification, retryable flag, and hint on failure
    """
    cfg = load_qwen_config(dotenv_path=dotenv_path)
    if not cfg["ready"]:
        missing_str = ", ".join(cfg["missing_fields"])
        raise QwenAPIError(
            error_type="配置缺失",
            message=f"缺少必要配置项：{missing_str}。未发起任何网络请求。",
            hint="请在系统环境变量或项目根目录 .env 文件中设置 QWEN_API_KEY、QWEN_BASE_URL 和 QWEN_MODEL。",
            retryable=False,
        )

    api_key = cfg["api_key"]
    base_url = cfg["base_url"]
    model = cfg["model"]

    factory = client_factory or _create_qwen_openai_client
    try:
        client = factory(api_key, base_url, timeout)
    except Exception as exc:
        raise QwenAPIError(
            error_type="客户端初始化失败",
            message=f"初始化 OpenAI 兼容客户端失败：{type(exc).__name__}: {exc}",
            hint="请检查 openai 依赖版本与 QWEN_BASE_URL 格式是否正确。",
            retryable=False,
        ) from exc

    create_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": input_text},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        create_kwargs["response_format"] = response_format

    t0 = time.time()
    try:
        response = client.chat.completions.create(**create_kwargs)
    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        exc_name = type(exc).__name__
        exc_msg = str(exc)

        if status_code == 401 or "401" in exc_msg or "AuthenticationError" in exc_name:
            raise QwenAPIError(
                error_type="认证失败 (HTTP 401)",
                message=f"Qwen API Key 认证未通过：{exc_msg}",
                hint="请检查 QWEN_API_KEY 是否为有效的阿里云 DashScope API Key，且未包含多余空格。",
                status_code=401,
                retryable=False,
            ) from exc
        if status_code == 403 or "403" in exc_msg or "PermissionDeniedError" in exc_name:
            raise QwenAPIError(
                error_type="权限拒绝 (HTTP 403)",
                message=f"Qwen API 权限不足或被拒绝：{exc_msg}",
                hint="请检查 DashScope 账户权限与模型开通状态。",
                status_code=403,
                retryable=False,
            ) from exc
        if status_code == 404 or "404" in exc_msg or "NotFoundError" in exc_name:
            raise QwenAPIError(
                error_type="接口或模型不存在 (HTTP 404)",
                message=f"请求的模型 ({model}) 或接口地址 ({base_url}) 不存在：{exc_msg}",
                hint="请确认 QWEN_BASE_URL 为 https://dashscope.aliyuncs.com/compatible-mode/v1 且 QWEN_MODEL（如 qwen-plus）拼写正确。",
                status_code=404,
                retryable=False,
            ) from exc
        if status_code in (500, 502, 503, 504) or any(
            code in exc_msg for code in ("500", "502", "503", "504", "Bad Gateway")
        ):
            raise QwenAPIError(
                error_type=f"服务端网关异常 (HTTP {status_code or 502})",
                message=f"上游接口返回服务端错误：{exc_msg}",
                hint="上游服务暂时不可用。您可稍后重试，或点击页面上的“使用演示结果”按钮查看内置演示输出。",
                status_code=status_code or 502,
                retryable=True,
            ) from exc
        if "Timeout" in exc_name or "timeout" in exc_msg.lower() or "timed out" in exc_msg.lower():
            raise QwenAPIError(
                error_type="请求超时",
                message=f"调用 Qwen 接口超过 {timeout:.0f} 秒未响应：{exc_msg}",
                hint="请检查当前网络连接是否能访问 dashscope.aliyuncs.com，或点击“使用演示结果”按钮。",
                retryable=True,
            ) from exc

        raise QwenAPIError(
            error_type=f"API 请求失败 ({exc_name})",
            message=f"调用 Qwen Chat Completions 失败：{exc_msg}",
            hint="请检查网络连通性、QWEN_BASE_URL 与账户额度，或点击“使用演示结果”进行离线演示。",
            status_code=status_code,
            retryable=False,
        ) from exc

    latency_ms = int((time.time() - t0) * 1000)

    raw_text = ""
    finish_reason: Optional[str] = None
    try:
        if response and getattr(response, "choices", None):
            choice0 = response.choices[0]
            finish_reason = getattr(choice0, "finish_reason", None)
            msg = choice0.message
            raw_text = (getattr(msg, "content", "") or "").strip()
    except Exception:
        raw_text = ""

    if finish_reason == "length":
        raise QwenAPIError(
            error_type="输出被截断",
            message=f"模型输出因达到 max_tokens ({max_tokens}) 限制被截断 (finish_reason='length')。",
            hint="请提高 max_tokens 或精简每条 reason/reasoning 字数。",
            raw_output=raw_text[:600],
            retryable=True,
            finish_reason="length",
        )

    if not raw_text:
        raise QwenAPIError(
            error_type="模型返回空内容",
            message="Qwen 接口响应成功，但 choices[0].message.content 为空。",
            hint="请检查模型输出限制或更换为 qwen-plus 后重试。",
            raw_output=str(response),
            retryable=False,
            finish_reason=finish_reason,
        )

    json_str = _extract_json_block(raw_text)
    try:
        parsed_obj = json.loads(json_str)
    except Exception as exc:
        raise QwenAPIError(
            error_type="JSON 解析失败",
            message=f"模型输出不是合法的 JSON 对象：{exc}",
            hint="以下为模型原始输出片段，请检查提示词或输出长度限制。",
            raw_output=raw_text[:600],
            retryable=True,
            finish_reason=finish_reason,
        ) from exc

    if not isinstance(parsed_obj, dict):
        raise QwenAPIError(
            error_type="JSON 结构不匹配",
            message="模型返回的 JSON 顶层不是对象 (dict)。",
            hint="请确保模型输出符合顶层 JSON 对象结构。",
            raw_output=raw_text[:600],
            retryable=True,
            finish_reason=finish_reason,
        )

    usage = getattr(response, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
    total_tokens = int(getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)) if usage else 0

    return {
        "parsed": parsed_obj,
        "raw_text": raw_text,
        "model": model,
        "base_url": base_url,
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "finish_reason": finish_reason,
    }


def _demo_cache_file(event_id: str, model: str) -> Path:
    safe_model = re.sub(r"[^a-zA-Z0-9_.-]", "_", model or "qwen-plus")
    safe_event = re.sub(r"[^a-zA-Z0-9_.-]", "_", event_id or "default")
    return DEMO_CACHE_DIR / f"{safe_event}__{safe_model}.json"


def _graph_cache_file(stock_code: str, as_of_date: str, title: str, model: str) -> Path:
    safe_model = re.sub(r"[^a-zA-Z0-9_.-]", "_", model or "qwen-plus")
    digest = hashlib.md5(f"{stock_code}_{as_of_date}_{title}".encode("utf-8")).hexdigest()[:10]
    return GRAPH_DEMO_CACHE_DIR / f"graph_{stock_code}_{as_of_date}_{digest}__{safe_model}.json"


def _build_event_analysis_fields(
    ev: dict,
    stock_code: str,
    stock_name: str,
    polarity: int,
    paths: Optional[list[dict]] = None,
    pred_dir: str = "NEUTRAL",
    is_priced_in: bool = False,
) -> Dict[str, Any]:
    """构建统一的单事件结构化字段（嵌入 InferenceResponse），确保与图谱推演同源一致。"""
    title = str(ev.get("title", "")).strip()
    content = str(ev.get("content") or ev.get("snippet") or "").strip()
    text = f"{title} {content}"

    entities: list[DemoEntity] = [
        DemoEntity(name=stock_name or stock_code, type="公司"),
        DemoEntity(name=stock_code, type="股票代码"),
    ]
    if paths:
        top_p = paths[0]
        src_name = str(top_p.get("source_name") or top_p.get("source") or "")
        if src_name:
            entities.append(DemoEntity(name=src_name.split("(")[0].strip(), type="上游传导源"))
        for inter in top_p.get("intermediate_nodes", []):
            iname = str(inter.get("name") or inter.get("id") or "")
            if iname:
                entities.append(DemoEntity(name=iname.split("(")[0].strip(), type="中游传导节点"))
    else:
        for kw, etype in (
            ("1.6T光模块", "产品"),
            ("800G光模块", "产品"),
            ("北美云厂商", "客户/地区"),
            ("Blackwell", "产品/平台"),
            ("Lumentum", "上游供应商"),
        ):
            if kw.lower() in text.lower():
                entities.append(DemoEntity(name=kw, type=etype))

    if paths:
        ev_type = f"跨公司{paths[0].get('actual_hops', 1)}跳产业链传导"
    elif is_priced_in:
        ev_type = "业绩兑现与估值高位钝化"
    elif polarity < 0 or pred_dir == "BEARISH":
        ev_type = "基本面与供应链利空冲击"
    elif polarity > 0 or pred_dir == "BULLISH":
        ev_type = "业绩与订单正向催化"
    else:
        ev_type = "常规经营动态"

    if polarity < 0 or (polarity == 0 and pred_dir == "BEARISH"):
        imp_dir = "negative"
        risk_lvl = "high"
    elif polarity > 0:
        imp_dir = "positive"
        risk_lvl = "high" if is_priced_in else "low"
    else:
        imp_dir = "neutral"
        risk_lvl = "medium"

    summary_prefix = ""
    if is_priced_in:
        summary_prefix = "【利好出尽/高位钝化】"
    elif paths:
        summary_prefix = f"【{paths[0].get('actual_hops', 1)}跳产业链传导】"
    summary_str = f"{summary_prefix}{title}。{content[:72]}" if content else f"{summary_prefix}{title}"

    return {
        "event_summary": summary_str,
        "entities": entities,
        "event_type": ev_type,
        "impact_direction": imp_dir,
        "risk_level": risk_lvl,
        "event_confidence": 0.86 if polarity != 0 else 0.65,
    }


def get_builtin_demo_result(event: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Return the clearly labeled built-in demo result ONLY when explicitly called.
    Preserved for backward compatibility with existing unit tests.
    """
    ev = event or load_sample_demo_event()
    title = str(ev.get("title", DEFAULT_SAMPLE_EVENT["title"]))
    content = str(ev.get("content") or ev.get("snippet") or DEFAULT_SAMPLE_EVENT["content"])
    pol = classify_event_polarity(f"{title} {content}")
    is_neg = pol < 0

    analysis = DemoEventAnalysis(
        event_summary=f"【内置演示分析】{title}。{content[:80]}",
        entities=[
            DemoEntity(name=str(ev.get("stock_name", "中际旭创")), type="公司"),
            DemoEntity(name=str(ev.get("stock_code", "300308.SZ")), type="股票代码"),
            DemoEntity(name="1.6T/800G光模块", type="产品"),
            DemoEntity(name="北美云厂商", type="客户/地区"),
        ],
        event_type="供应链与排产催化" if is_neg else "业绩与订单催化",
        impact_direction="negative" if is_neg else ("positive" if pol > 0 else "neutral"),
        risk_level="high" if is_neg else "medium",
        confidence=0.86,
        evidence=[content[:120] or title],
    )
    return {
        "ok": True,
        "event": ev,
        "analysis": analysis.model_dump(),
        "model": "内置演示数据 (未调用 Qwen API)",
        "base_url": "-",
        "call_success": False,
        "from_cache": False,
        "is_demo_fallback": True,
        "status_label": "当前为演示数据，未调用 Qwen API",
        "latency_ms": 0,
    }


def analyze_demo_event(
    event: Optional[Dict[str, Any]] = None,
    use_cache: bool = True,
    client_factory: Optional[Callable[[str, str, float], Any]] = None,
    dotenv_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Execute the First-Edition Qwen Demo flow for a single financial event.
    Preserved for unit tests; app.py now uses the unified run_agent_inference pipeline.
    """
    ev = event or load_sample_demo_event()
    cfg = load_qwen_config(dotenv_path=dotenv_path)
    model = cfg["model"]
    base_url = cfg["base_url"]
    title = str(ev.get("title", DEFAULT_SAMPLE_EVENT["title"]))
    content = str(ev.get("content") or ev.get("snippet") or DEFAULT_SAMPLE_EVENT["content"])
    event_id = str(ev.get("event_id") or hashlib.md5(f"{title}_{content}".encode("utf-8")).hexdigest()[:8])

    cache_path = _demo_cache_file(event_id, model)
    if use_cache and cache_path.exists():
        try:
            cached_payload = json.loads(cache_path.read_text(encoding="utf-8"))
            cached_analysis = DemoEventAnalysis.model_validate(cached_payload["analysis"])
            return {
                "ok": True,
                "event": ev,
                "analysis": cached_analysis.model_dump(),
                "model": cached_payload.get("model", model),
                "base_url": cached_payload.get("base_url", base_url),
                "call_success": True,
                "from_cache": True,
                "is_demo_fallback": False,
                "status_label": "本地缓存命中（未重复发起网络请求）",
                "latency_ms": int(cached_payload.get("latency_ms", 0)),
            }
        except Exception:
            pass

    sys_prompt, usr_prompt = build_demo_event_prompt(
        title=title,
        content=content,
        source=str(ev.get("source", "")),
        stock_code=str(ev.get("stock_code", "")),
        stock_name=str(ev.get("stock_name", "")),
    )

    api_res = call_qwen_json(
        prompt=sys_prompt,
        input_text=usr_prompt,
        max_tokens=SINGLE_MAX_TOKENS,
        timeout=LLM_TIMEOUT,
        client_factory=client_factory,
        dotenv_path=dotenv_path,
    )

    try:
        analysis = DemoEventAnalysis.model_validate(api_res["parsed"])
        if not analysis.event_summary.strip() or not analysis.event_type.strip():
            raise ValueError("event_summary 或 event_type 为空")
    except (ValidationError, ValueError) as exc:
        raise QwenAPIError(
            error_type="JSON Schema 校验失败",
            message=f"模型返回的 JSON 字段不完整或类型不合法：{exc}",
            hint="模型返回必须包含 event_summary、entities、event_type、impact_direction、risk_level、confidence、evidence。",
            raw_output=api_res["raw_text"][:600],
            retryable=False,
            finish_reason=api_res.get("finish_reason"),
        ) from exc

    out_bundle = {
        "ok": True,
        "event": ev,
        "analysis": analysis.model_dump(),
        "model": api_res["model"],
        "base_url": api_res["base_url"],
        "call_success": True,
        "from_cache": False,
        "is_demo_fallback": False,
        "status_label": "真实 Qwen API 调用成功",
        "latency_ms": api_res["latency_ms"],
        "finish_reason": api_res.get("finish_reason"),
    }

    try:
        DEMO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(out_bundle, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

    return out_bundle


def verify_single_api_call(
    client_factory: Optional[Callable[[str, str, float], Any]] = None,
    dotenv_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Minimal single-request Qwen connectivity check (used by scripts/check_api.py and eval_benchmark.py)."""
    cfg = load_qwen_config(dotenv_path=dotenv_path)
    res = call_qwen_json(
        prompt="你是一个只输出JSON的接口连通性助手。不要输出任何Markdown或解释。",
        input_text='请仅输出以下JSON对象：{"status": "ok"}',
        max_tokens=32,
        timeout=20.0,
        client_factory=client_factory,
        dotenv_path=dotenv_path,
    )
    return {
        "ok": res["parsed"].get("status") == "ok",
        "model": cfg["model"],
        "base_url": cfg["base_url"],
        "latency_ms": res["latency_ms"],
        "parsed": res["parsed"],
    }


check_llm_connectivity = verify_single_api_call


def _heuristic_fallback(model_cls: Type[BaseModel], ctx: dict) -> BaseModel:
    """
    内置确定性图谱状态转移器（仅在用户明确点击“使用演示结果”离线演示时调用；
    严禁在真实 API 调用失败或 LIVE_LLM_BENCHMARK 评测时调用）。
    """
    as_of = ctx.get("as_of_date", "2026-10-14")[:10]
    pi = ctx.get("priced_in_info", {})
    ev_id = ctx.get("event_id", f"EV_{as_of.replace('-', '')}_01_0000")
    pub_at = ctx.get("published_at", f"{as_of} 09:30:00")

    if model_cls is L2Graph:
        code, name = ctx["stock_code"], ctx.get("stock_name") or ctx["stock_code"]
        is_prior = ctx.get("evidence_type") == "COLD_START_PRIOR"
        conf_bull = 0.50 if is_prior else 0.82
        conf_bear = 0.45 if is_prior else 0.65
        prefix = "[待实证核验] " if is_prior else ""
        g = L2Graph(
            stock_code=code,
            stock_name=name,
            last_updated=as_of,
            market_regime=MarketRegime(
                close_rank_pct_60d=pi.get("close_rank_pct_60d", 0.5),
                range_pos_60d=pi.get("range_pos_60d", 0.5),
                return_20d_pct=pi.get("return_20d_pct", 0.0),
                turnover_anomaly=pi.get("turnover_anomaly", "NORMAL"),
                net_sentiment_score=0.0,
            ),
            thesis_nodes=[
                ThesisNode(
                    id="TH_01",
                    type="BULLISH_LOGIC",
                    title=f"{prefix}{name}核心产品需求与批价景气回升",
                    category="DEMAND",
                    status="ACTIVE",
                    weight=0.75,
                    confidence=conf_bull,
                    created_at=as_of,
                    updated_at=as_of,
                    priced_in_ratio=0.30,
                    evidence_pointers=[ev_id],
                    invalidation_condition="终端动销或核心产品价格跌破阈值",
                ),
                ThesisNode(
                    id="TH_02",
                    type="BEARISH_LOGIC",
                    title=f"{prefix}{name}宏观消费复苏斜率与渠道库存压力",
                    category="MACRO",
                    status="ACTIVE",
                    weight=0.40,
                    confidence=conf_bear,
                    created_at=as_of,
                    updated_at=as_of,
                    priced_in_ratio=0.30,
                    evidence_pointers=[ev_id],
                    invalidation_condition="旺季渠道库存周转天数降至安全线内",
                ),
            ],
            edges=[
                Edge(
                    source="TH_01",
                    target="TH_02",
                    relation="UPSTREAM_DRIVES",
                    hop=1,
                    transmission_sign="-1",
                    created_at=as_of,
                    description="终端批价回暖直接缓解渠道库存压力",
                )
            ],
            baseline_snapshot={"as_of_date": as_of, "nodes": ["TH_01", "TH_02"], "edges": ["TH_01->TH_02"]},
        )
        g.compute_net_score(use_edges=True)
        return g

    graph: L2Graph = ctx["l2_graph"]
    ev: dict = ctx.get("new_event", {})
    paths: list[dict] = ctx.get("contagion_paths") or []
    text = f"{ev.get('title', '')} {ev.get('content', '')} {ev.get('snippet', '')}"
    polarity = int(ctx["event_polarity"]) if ctx.get("event_polarity") is not None else classify_event_polarity(text)
    ratio = float(pi.get("priced_in_ratio", 0.3))

    active_nodes = [n for n in graph.thesis_nodes if n.status == "ACTIVE"]
    active_bulls = [n for n in active_nodes if n.type == "BULLISH_LOGIC"]
    active_bears = [n for n in active_nodes if n.type == "BEARISH_LOGIC"]
    next_id = f"TH_{len(graph.thesis_nodes) + 1:02d}"
    ops: list[PatchOp] = []
    direct_mention = (graph.stock_name in text) or (graph.stock_code in text)

    # 0) 市场级 Priced-in Gate：若 priced_in_ratio >= 0.85 且 polarity > 0，只能输出 PRICED_IN 或 NEUTRAL，不得 ADD_NODE(BULLISH)
    if ratio >= 0.85 and polarity > 0:
        if active_bulls:
            ops.append(
                PatchOp(
                    op="PRICED_IN",
                    target_node_id=active_bulls[0].id,
                    reason=pi.get("priced_in_desc", f"前期涨幅巨大且预期兑现度达 {ratio:.0%}，利好已高度透支"),
                    evidence_id=ev_id,
                    published_at=pub_at[:10],
                )
            )
            pred_t1_dir, pred_t5_dir = "BEARISH", "BEARISH"
            t1_reason = "前期涨幅巨大且处于极高分位，公告利好落地触发Sell-the-news兑现"
            t5_reason = "核心多头节点切换为PRICED_IN，短期缺乏超预期新边际增量催化"
        else:
            pred_t1_dir, pred_t5_dir = "NEUTRAL", "NEUTRAL"
            t1_reason = f"市场预期兑现度高达 {ratio:.0%}，利好受制于市场级高位钝化门控"
            t5_reason = "高分位区间限制追高动能，维持中性观望"

        ev_fields = _build_event_analysis_fields(
            ev, graph.stock_code, graph.stock_name, polarity=polarity, paths=paths, pred_dir=pred_t5_dir, is_priced_in=True
        )
        return InferenceResponse(
            **ev_fields,
            patch_ops=ops,
            contagion_impact="龙头利好兑现（Priced-in 预期透支）引发板块高位获利盘阶段性分流。",
            t1_forecast=HorizonPred(direction=pred_t1_dir, confidence=0.80, reasoning=t1_reason),
            t5_forecast=HorizonPred(direction=pred_t5_dir, confidence=0.76, reasoning=t5_reason),
            t20_forecast=HorizonPred(direction="NEUTRAL", confidence=0.68, reasoning="等待估值消化与下一阶段新产品周期催化"),
            watch_indicators=["高位换手率回落信号", "机构获利盘减仓幅度", "新产品订单超预期催化"],
        )

    # 1) 跨公司/产业链多跳传导分支（无 direct_mention 时，直接按 top_p["transmission_sign"] 选方向）
    if not direct_mention:
        if not paths:
            if polarity < 0:
                d_now = "BEARISH"
            elif polarity > 0:
                d_now = "BULLISH"
            else:
                cur_s = graph.compute_net_score(use_edges=False)
                d_now = "BULLISH" if cur_s >= 0 else "BEARISH"
            ev_fields = _build_event_analysis_fields(
                ev, graph.stock_code, graph.stock_name, polarity=polarity, paths=[], pred_dir=d_now
            )
            return InferenceResponse(
                **ev_fields,
                patch_ops=[],
                contagion_impact="未启用跨公司传导边，无法关联外部实体事件。",
                t1_forecast=HorizonPred(direction=d_now, confidence=0.55, reasoning="事件未直接提及目标股且无传导边关联，维持基线方向判断"),
                t5_forecast=HorizonPred(direction=d_now, confidence=0.55, reasoning="维持既有活跃节点净势能方向"),
                t20_forecast=HorizonPred(direction="NEUTRAL", confidence=0.50, reasoning="缺乏直接基本面催化映射"),
                watch_indicators=["后续是否出现公司直接公告"],
            )

        top_p = paths[0]
        if top_p["transmission_sign"] == "-1":
            node_pol, pred_dir = "BEARISH_LOGIC", "BEARISH"
        else:
            node_pol, pred_dir = "BULLISH_LOGIC", "BULLISH"

        w_hop = round(min(0.90, max(0.35, abs(float(top_p["path_factor"])) + 0.22)), 2)
        c_node = ThesisNode(
            id=next_id,
            type=node_pol,
            title=f"[{top_p['source']}->{top_p['actual_hops']}跳传导] {ev.get('title', '')[:22]}",
            category="CONTAGION",
            status="ACTIVE",
            weight=w_hop,
            confidence=0.85,
            created_at=as_of,
            updated_at=as_of,
            priced_in_ratio=0.15,
            status_reason=f"路径 {top_p['path']} (actual_hops={top_p['actual_hops']}, γ_total={top_p['gamma_total']}, factor={top_p['path_factor']:+.4f})",
            evidence_pointers=[ev_id],
            invalidation_condition=f"上游 {top_p['source']} 供给或需求异动恢复常态",
        )
        c_edge = (
            Edge(
                source=next_id,
                target=active_nodes[0].id,
                relation="UPSTREAM_DRIVES",
                hop=min(2, int(top_p["actual_hops"])),
                transmission_sign="+1",
                created_at=as_of,
                description=top_p["description"],
            )
            if active_nodes
            else None
        )
        ops.append(
            PatchOp(
                op="ADD_NODE",
                reason=top_p["description"],
                new_node=c_node,
                new_edge=c_edge,
                evidence_id=ev_id,
                published_at=pub_at[:10],
            )
        )

        extra_mechanism = ""
        if polarity < 0 and pred_dir == "BULLISH":
            extra_mechanism = "（上游跌价让利/国产替代竞争受益逻辑：上游负向变动转化为下游成本下降或替代份额提升）"

        ev_fields = _build_event_analysis_fields(
            ev, graph.stock_code, graph.stock_name, polarity=polarity, paths=paths, pred_dir=pred_dir
        )
        return InferenceResponse(
            **ev_fields,
            patch_ops=ops,
            contagion_impact=(
                f"检测到 {top_p['actual_hops']} 跳产业链传导 [{top_p['path']}]"
                f"（总紧密系数 {top_p['gamma_total']}, 衰减因子 {top_p['path_factor']:+.4f}）{extra_mechanism}：{top_p['description']}"
            ),
            t1_forecast=HorizonPred(direction=pred_dir, confidence=0.82, reasoning=f"跨公司事件通过 {top_p['path']} 传导影响短线预期"),
            t5_forecast=HorizonPred(direction=pred_dir, confidence=0.79, reasoning=f"产业链 {top_p['relation']} 效应沿边权重叠加改变净多空势能"),
            t20_forecast=HorizonPred(direction="NEUTRAL" if pred_dir == "BEARISH" else "BULLISH", confidence=0.68, reasoning="需跟踪上游产能/价格修复节奏及公司长协备货缓冲能力"),
            watch_indicators=[f"{top_p['source']} 排产与现货报价走势", "中游环节库存缓冲周期", "替代方案导入进度"],
        )

    # 2) 直接事件碰撞分支（direct_mention == True：优先按 polarity 选方向，polarity == 0 才退回规则）
    is_bearish_direct = (polarity < 0) or (polarity == 0 and any(k in text for k in BEAR_KWS))
    if is_bearish_direct:
        if active_bulls:
            ops.append(
                PatchOp(
                    op="INVALIDATE",
                    target_node_id=active_bulls[0].id,
                    reason=f"触发证伪条件：{ev.get('title', '突发利空')}",
                    evidence_id=ev_id,
                    published_at=pub_at[:10],
                )
            )
        n_node = ThesisNode(
            id=next_id,
            type="BEARISH_LOGIC",
            title=ev.get("title", "基本面突发利空")[:36],
            category="CATALYST_SHOCK",
            status="ACTIVE",
            weight=0.88,
            confidence=0.90,
            created_at=as_of,
            updated_at=as_of,
            priced_in_ratio=0.10,
            status_reason=ev.get("content", "")[:60],
            evidence_pointers=[ev_id],
            invalidation_condition="下游客户重新上修订单指引",
        )
        edge_target = active_bulls[1].id if len(active_bulls) > 1 else (active_bulls[0].id if active_bulls else None)
        n_edge = (
            Edge(
                source=next_id,
                target=edge_target,
                relation="INVALIDATES",
                hop=1,
                transmission_sign="-1",
                created_at=as_of,
                description="指引下调通过证伪边压制关联多头逻辑",
            )
            if edge_target
            else None
        )
        ops.append(
            PatchOp(
                op="ADD_NODE",
                reason="注入突发利空节点",
                new_node=n_node,
                new_edge=n_edge,
                evidence_id=ev_id,
                published_at=pub_at[:10],
            )
        )
        ev_fields = _build_event_analysis_fields(
            ev, graph.stock_code, graph.stock_name, polarity=-1, paths=paths, pred_dir="BEARISH"
        )
        return InferenceResponse(
            **ev_fields,
            patch_ops=ops,
            contagion_impact="核心客户指引下调将沿产业链向二线厂商与上游芯片传导负向冲击。",
            t1_forecast=HorizonPred(direction="BEARISH", confidence=0.88, reasoning="突发砍单/推迟利空，短线资金避险情绪集中宣泄"),
            t5_forecast=HorizonPred(direction="BEARISH", confidence=0.80, reasoning="原核心多头逻辑被证伪，盈利预期面临下修"),
            t20_forecast=HorizonPred(direction="NEUTRAL", confidence=0.65, reasoning="待急跌释放风险后观察次季排产修复情况"),
            watch_indicators=["北美云厂商下季度CapEx指引", "散热组件良率修复进度", "机构持仓拥挤度出清信号"],
        )

    if ratio >= 0.85:
        if active_bulls:
            ops.append(
                PatchOp(
                    op="PRICED_IN",
                    target_node_id=active_bulls[0].id,
                    reason=pi.get("priced_in_desc", "利好预期已高度透支"),
                    evidence_id=ev_id,
                    published_at=pub_at[:10],
                )
            )
        ev_fields = _build_event_analysis_fields(
            ev, graph.stock_code, graph.stock_name, polarity=polarity, paths=paths, pred_dir="BEARISH", is_priced_in=True
        )
        return InferenceResponse(
            **ev_fields,
            patch_ops=ops,
            contagion_impact="龙头利好兑现引发板块高位获利盘阶段性分流。",
            t1_forecast=HorizonPred(direction="BEARISH", confidence=0.80, reasoning="前期涨幅巨大且处于高分位，公告落地触发Sell-the-news兑现"),
            t5_forecast=HorizonPred(direction="BEARISH", confidence=0.76, reasoning="核心多头节点切换为PRICED_IN，短期缺乏新边际增量催化"),
            t20_forecast=HorizonPred(direction="NEUTRAL", confidence=0.68, reasoning="等待估值消化与下一阶段新产品周期催化"),
            watch_indicators=["高位换手率回落信号", "机构获利盘减仓幅度", "新产品订单超预期催化"],
        )

    if any(k in text for k in ("扭转", "长协锁单")) and active_bears:
        ops.append(
            PatchOp(
                op="INVALIDATE",
                target_node_id=active_bears[0].id,
                reason=f"利空反转证伪：{ev.get('title', '')}",
                evidence_id=ev_id,
                published_at=pub_at[:10],
            )
        )
        edge_target = active_bears[1].id if len(active_bears) > 1 else active_bears[0].id
        n_edge = Edge(
            source=next_id,
            target=edge_target,
            relation="INVALIDATES",
            hop=1,
            transmission_sign="-1",
            created_at=as_of,
            description="新长协锁单证伪原产能过剩利空",
        )
    else:
        if active_bulls:
            ops.append(
                PatchOp(
                    op="CONFIRM",
                    target_node_id=active_bulls[0].id,
                    new_weight=min(1.0, round(active_bulls[0].weight + 0.1, 2)),
                    reason=f"事件印证：{ev.get('title', '景气强化')}",
                    evidence_id=ev_id,
                    published_at=pub_at[:10],
                )
            )
        n_edge = (
            Edge(
                source=next_id,
                target=active_bulls[0].id,
                relation="CONFIRM",
                hop=1,
                transmission_sign="+1",
                created_at=as_of,
                description="新催化事件与核心多头逻辑相互印证",
            )
            if active_bulls
            else None
        )

    n_node = ThesisNode(
        id=next_id,
        type="BULLISH_LOGIC",
        title=ev.get("title", "核心催化超预期")[:36],
        category="CATALYST",
        status="ACTIVE",
        weight=0.85,
        confidence=0.88,
        created_at=as_of,
        updated_at=as_of,
        priced_in_ratio=0.15,
        evidence_pointers=[ev_id],
        invalidation_condition="终端价格或销量再度回落",
    )
    ops.append(
        PatchOp(
            op="ADD_NODE",
            reason="新增景气催化节点",
            new_node=n_node,
            new_edge=n_edge,
            evidence_id=ev_id,
            published_at=pub_at[:10],
        )
    )
    ev_fields = _build_event_analysis_fields(
        ev, graph.stock_code, graph.stock_name, polarity=1 if polarity >= 0 else polarity, paths=paths, pred_dir="BULLISH"
    )
    return InferenceResponse(
        **ev_fields,
        patch_ops=ops,
        contagion_impact="龙头基本面催化对同板块估值中枢形成正向提振。",
        t1_forecast=HorizonPred(direction="BULLISH", confidence=0.82, reasoning="基本面催化落地，短线情绪偏强"),
        t5_forecast=HorizonPred(direction="BULLISH", confidence=0.78, reasoning="多头逻辑节点权重上修，净势能走阔"),
        t20_forecast=HorizonPred(direction="BULLISH", confidence=0.74, reasoning="中周期景气趋势得到基本面数据验证"),
        watch_indicators=["核心产品终端批价走势", "渠道库存消化速度", "机构资金净流入"],
    )


def _normalize_inference_dict(
    raw_dict: Dict[str, Any],
    ctx: Dict[str, Any],
    require_all_forecasts: bool = True,
) -> Dict[str, Any]:
    """
    Normalize Qwen JSON response into strict unified InferenceResponse schema compatibility.
    When require_all_forecasts=True, never fabricates missing t1_forecast/t5_forecast/t20_forecast.
    """
    out = dict(raw_dict)
    as_of = str(ctx.get("as_of_date", "2026-10-14"))[:10]
    ev_id = str(ctx.get("event_id", f"EV_{as_of.replace('-', '')}_01_0000"))
    pub_at = str(ctx.get("published_at", f"{as_of} 09:30:00"))
    ev = ctx.get("new_event") or {}
    graph: Optional[L2Graph] = ctx.get("l2_graph")
    stock_code = graph.stock_code if graph else str(ev.get("stock_code", "300308.SZ"))
    stock_name = graph.stock_name if graph else str(ev.get("stock_name", "中际旭创"))
    polarity = int(ctx["event_polarity"]) if ctx.get("event_polarity") is not None else classify_event_polarity(
        f"{ev.get('title', '')} {ev.get('content', '')}"
    )
    paths = ctx.get("contagion_paths") or []

    if require_all_forecasts:
        has_t1 = isinstance(out.get("t1_forecast") or out.get("pred_t1"), dict)
        has_t5 = isinstance(out.get("t5_forecast") or out.get("pred_t5"), dict)
        has_t20 = isinstance(out.get("t20_forecast"), dict)
        if not (has_t1 and has_t5 and has_t20):
            missing_fcs = [
                k for k, ok in (("t1_forecast", has_t1), ("t5_forecast", has_t5), ("t20_forecast", has_t20)) if not ok
            ]
            raise ValueError(f"模型输出缺少必填多周期预测字段: {', '.join(missing_fcs)}")

    raw_ops = out.get("patch_ops")
    norm_ops = []
    has_priced_in_op = False
    if isinstance(raw_ops, list):
        for idx, op in enumerate(raw_ops[:3], start=1):
            if not isinstance(op, dict):
                continue
            op_c = dict(op)
            op_type = str(op_c.get("op", "CONFIRM")).upper()
            if op_type not in ("CONFIRM", "INVALIDATE", "PRICED_IN", "ADD_NODE"):
                op_type = "CONFIRM"
            if op_type == "PRICED_IN":
                has_priced_in_op = True
            op_c["op"] = op_type
            if not op_c.get("target_node_id") and op_c.get("node_id"):
                op_c["target_node_id"] = op_c["node_id"]
            op_c["evidence_id"] = ev_id
            op_c["published_at"] = pub_at[:10]
            op_c["reason"] = str(op_c.get("reason") or "基于最新金融事件更新论点状态")

            if op_type == "ADD_NODE":
                nn = op_c.get("new_node")
                if not isinstance(nn, dict):
                    nn = {}
                else:
                    nn = dict(nn)
                nn.setdefault("id", f"TH_NEW_{idx:02d}")
                raw_t = str(nn.get("type", "BULLISH_LOGIC")).upper()
                nn["type"] = "BEARISH_LOGIC" if "BEAR" in raw_t or "空" in raw_t else "BULLISH_LOGIC"
                nn["title"] = str(nn.get("title") or op_c["reason"][:28] or "新增催化论点")
                nn["category"] = str(nn.get("category") or "EVENT")
                nn["status"] = "ACTIVE"
                nn["weight"] = max(0.0, min(1.0, float(nn.get("weight", 0.75))))
                nn["confidence"] = max(0.0, min(1.0, float(nn.get("confidence", 0.80))))
                nn["created_at"] = as_of
                nn["updated_at"] = as_of
                nn["priced_in_ratio"] = max(0.0, min(1.0, float(nn.get("priced_in_ratio", 0.15))))
                nn["evidence_pointers"] = [ev_id]
                if not nn.get("invalidation_condition") or not str(nn["invalidation_condition"]).strip():
                    nn["invalidation_condition"] = "后续经营数据或订单指引未达预期"
                op_c["new_node"] = nn
                if isinstance(op_c.get("new_edge"), dict):
                    ne = dict(op_c["new_edge"])
                    ne["created_at"] = as_of
                    if ne.get("relation") not in ("CONFIRM", "INVALIDATES", "UPSTREAM_DRIVES", "COMPETES_WITH"):
                        ne["relation"] = "CONFIRM"
                    ne["transmission_sign"] = "-1" if str(ne.get("transmission_sign")) == "-1" else "+1"
                    op_c["new_edge"] = ne
                else:
                    op_c["new_edge"] = None
            else:
                op_c["new_node"] = None
                op_c["new_edge"] = None
                if op_c.get("new_weight") is not None:
                    try:
                        op_c["new_weight"] = max(0.0, min(1.0, float(op_c["new_weight"])))
                    except Exception:
                        op_c["new_weight"] = 0.75
            norm_ops.append(op_c)
    out["patch_ops"] = norm_ops

    def _norm_fc(fc_key: str, fallback_key: str = "") -> Dict[str, Any]:
        raw_fc = out.get(fc_key) or (out.get(fallback_key) if fallback_key else None) or {}
        if not isinstance(raw_fc, dict):
            raw_fc = {}
        d = str(raw_fc.get("direction", "NEUTRAL")).upper()
        if "BULL" in d or "多" in d or "POS" in d:
            d = "BULLISH"
        elif "BEAR" in d or "空" in d or "NEG" in d:
            d = "BEARISH"
        else:
            d = "NEUTRAL"
        try:
            c = max(0.0, min(1.0, float(raw_fc.get("confidence", 0.75))))
        except Exception:
            c = 0.75
        r = str(raw_fc.get("reasoning") or raw_fc.get("rationale") or "基于 L2 论点图谱与 L3 量价校准推演")
        return {"direction": d, "confidence": c, "reasoning": r}

    out["t1_forecast"] = _norm_fc("t1_forecast", "pred_t1")
    out["t5_forecast"] = _norm_fc("t5_forecast", "pred_t5")
    out["t20_forecast"] = _norm_fc("t20_forecast", "pred_t5" if not require_all_forecasts else "")
    if not isinstance(out.get("watch_indicators"), list):
        out["watch_indicators"] = ["核心产品出货节奏", "下游客户资本开支指引"]
    else:
        out["watch_indicators"] = [str(x) for x in out["watch_indicators"][:3]]

    default_ev_fields = _build_event_analysis_fields(
        ev=ev,
        stock_code=stock_code,
        stock_name=stock_name,
        polarity=polarity,
        paths=paths,
        pred_dir=out["t5_forecast"]["direction"],
        is_priced_in=has_priced_in_op,
    )
    if not out.get("event_summary"):
        out["event_summary"] = str(out.get("reasoning_summary") or default_ev_fields["event_summary"])
    if not out.get("entities"):
        out["entities"] = [e.model_dump() for e in default_ev_fields["entities"]]
    if not out.get("event_type"):
        out["event_type"] = default_ev_fields["event_type"]
    if not out.get("impact_direction"):
        out["impact_direction"] = default_ev_fields["impact_direction"]
    if not out.get("risk_level"):
        out["risk_level"] = default_ev_fields["risk_level"]
    if not out.get("event_confidence"):
        out["event_confidence"] = float(out["t5_forecast"].get("confidence") or default_ev_fields["event_confidence"])

    return out


def _call_llm_json(
    sys_prompt: str,
    usr_prompt: str,
    model_cls: Type[BaseModel],
    ctx: dict,
    client_factory: Optional[Callable[[str, str, float], Any]] = None,
    dotenv_path: Optional[Path] = None,
    retry_sleep_sec: float = 1.0,
    method_tag: Optional[str] = None,
    use_cache: bool = False,
    return_trace: bool = False,
) -> Any:
    """
    Call Qwen OpenAI-compatible Chat Completions API and validate against model_cls:
    - Attempt 1 uses GRAPH_MAX_TOKENS (2600) and timeout LLM_TIMEOUT (60.0s).
    - On truncation ("输出被截断") or JSON parse / validation failure ("JSON 解析失败"),
      or 5xx / timeout (with 1s sleep), retries at most ONCE (retry_count = 1, max 2 requests total)
      using GRAPH_MAX_TOKENS_RETRY (4096) and appending RETRY_COMPACT_SUFFIX to system prompt.
    - Never retries on 401 / 403 / 404 or missing config.
    - Strictly NO automatic fallback to heuristic rules when the API fails.
    """
    pi = ctx.get("priced_in_info", {})
    read_mode = pi.get("storage_read_mode", "IN_MEMORY")
    data_origin = pi.get("underlying_data_origin", "CURATED_REAL_ARCHIVE")
    cfg = load_qwen_config(dotenv_path=dotenv_path)
    req_hash = hashlib.md5(
        f"{cfg['model']}||{method_tag or ''}||{sys_prompt}||{usr_prompt}".encode("utf-8")
    ).hexdigest()[:16]

    if use_cache and method_tag and client_factory is None:
        EVAL_LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        eval_cache_file = EVAL_LLM_CACHE_DIR / f"eval_{req_hash}.json"
        if eval_cache_file.exists():
            try:
                c_data = json.loads(eval_cache_file.read_text(encoding="utf-8"))
                parsed_dict = c_data["parsed"]
                if model_cls is InferenceResponse:
                    parsed_dict = _normalize_inference_dict(parsed_dict, ctx, require_all_forecasts=True)
                parsed_model = model_cls.model_validate(parsed_dict)
                meta = ExecutionMeta.model_validate(c_data["execution_meta"])
                meta.inference_mode = "RESPONSE_CACHE_HIT"
                meta.call_origin = "RESPONSE_CACHE_HIT"
                meta.request_hash = req_hash
                trace = {"system_prompt": sys_prompt, "user_prompt": usr_prompt, "raw_response_text": c_data.get("raw_text", "")}
                if return_trace or method_tag is not None:
                    return parsed_model, meta, trace
                return parsed_model, meta
            except Exception:
                pass

    retry_count = 0
    json_repaired = False
    last_err: Optional[QwenAPIError] = None
    total_latency_ms = 0

    for attempt in range(2):
        cur_max_tokens = GRAPH_MAX_TOKENS if attempt == 0 else GRAPH_MAX_TOKENS_RETRY
        cur_sys_prompt = sys_prompt if attempt == 0 else (sys_prompt + RETRY_COMPACT_SUFFIX)
        if attempt == 1:
            retry_count = 1

        try:
            res = call_qwen_json(
                prompt=cur_sys_prompt,
                input_text=usr_prompt,
                max_tokens=cur_max_tokens,
                timeout=LLM_TIMEOUT,
                client_factory=client_factory,
                dotenv_path=dotenv_path,
            )
            total_latency_ms += int(res.get("latency_ms", 0))
            parsed_dict = res["parsed"]
            if model_cls is InferenceResponse:
                parsed_dict = _normalize_inference_dict(parsed_dict, ctx, require_all_forecasts=True)
            parsed_model = model_cls.model_validate(parsed_dict)

            p_tok = res.get("prompt_tokens") or _estimate_tokens(cur_sys_prompt + "\n" + usr_prompt)
            c_tok = res.get("completion_tokens") or _estimate_tokens(parsed_model.model_dump_json())
            tok_type = (
                "EXACT_API_USAGE"
                if (res.get("prompt_tokens", 0) > 0 and res.get("completion_tokens", 0) > 0)
                else "MISSING_OR_ESTIMATED"
            )
            finish_reason = res.get("finish_reason")
            logger.info(
                "Qwen graph inference succeeded: model=%s retry_count=%d finish_reason=%s json_repaired=%s latency_ms=%d",
                res["model"],
                retry_count,
                finish_reason,
                json_repaired,
                total_latency_ms,
            )
            meta = ExecutionMeta(
                storage_read_mode=read_mode,
                underlying_data_origin=data_origin,
                inference_mode="LLM_API",
                call_origin="LIVE_API_CALL",
                model_name=res["model"],
                base_url=res["base_url"],
                token_count_type=tok_type,
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                estimated_tokens=p_tok + c_tok,
                request_hash=req_hash,
                fallback_reason=None,
                retry_count=retry_count,
                finish_reason=finish_reason,
                json_repaired=json_repaired,
                latency_ms=total_latency_ms,
            )
            if use_cache and method_tag and client_factory is None:
                try:
                    EVAL_LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    (EVAL_LLM_CACHE_DIR / f"eval_{req_hash}.json").write_text(
                        json.dumps(
                            {
                                "parsed": parsed_model.model_dump(),
                                "execution_meta": meta.model_dump(),
                                "raw_text": res.get("raw_text", ""),
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
            trace = {"system_prompt": cur_sys_prompt, "user_prompt": usr_prompt, "raw_response_text": res.get("raw_text", "")}
            if return_trace or method_tag is not None:
                return parsed_model, meta, trace
            return parsed_model, meta

        except (ValidationError, ValueError) as val_exc:
            raw_out = locals().get("res", {}).get("raw_text", "") if "res" in locals() else ""
            f_reason = locals().get("res", {}).get("finish_reason") if "res" in locals() else None
            last_err = QwenAPIError(
                error_type="图谱 JSON Schema 校验失败",
                message=f"Qwen 返回的 JSON 不符合 {model_cls.__name__} 契约：{val_exc}",
                hint="模型输出缺少必填字段（如 t1_forecast/t5_forecast/t20_forecast）或类型不匹配。",
                raw_output=raw_out[:600],
                retryable=True,
                finish_reason=f_reason,
            )
        except QwenAPIError as api_err:
            last_err = api_err

        if attempt == 0 and last_err is not None:
            if last_err.status_code in (401, 403, 404) or not last_err.retryable:
                raise last_err
            is_server_or_timeout = (
                last_err.status_code in (500, 502, 503, 504)
                or "服务端网关异常" in last_err.error_type
                or last_err.error_type == "请求超时"
            )
            if is_server_or_timeout and retry_sleep_sec > 0:
                time.sleep(retry_sleep_sec)
            continue

        if attempt == 1 and last_err is not None and last_err.raw_output and model_cls is InferenceResponse:
            repaired_dict = _repair_truncated_json(last_err.raw_output)
            if repaired_dict is not None:
                try:
                    norm_rep = _normalize_inference_dict(repaired_dict, ctx, require_all_forecasts=True)
                    parsed_model = model_cls.model_validate(norm_rep)
                    json_repaired = True
                    p_tok = _estimate_tokens(cur_sys_prompt + "\n" + usr_prompt)
                    c_tok = _estimate_tokens(parsed_model.model_dump_json())
                    meta = ExecutionMeta(
                        storage_read_mode=read_mode,
                        underlying_data_origin=data_origin,
                        inference_mode="LLM_API",
                        call_origin="LIVE_API_CALL",
                        model_name=cfg["model"],
                        base_url=cfg["base_url"],
                        token_count_type="MISSING_OR_ESTIMATED",
                        prompt_tokens=p_tok,
                        completion_tokens=c_tok,
                        estimated_tokens=p_tok + c_tok,
                        request_hash=req_hash,
                        fallback_reason=None,
                        retry_count=retry_count,
                        finish_reason=last_err.finish_reason or "length",
                        json_repaired=True,
                        latency_ms=total_latency_ms,
                    )
                    trace = {"system_prompt": cur_sys_prompt, "user_prompt": usr_prompt, "raw_response_text": last_err.raw_output}
                    if return_trace or method_tag is not None:
                        return parsed_model, meta, trace
                    return parsed_model, meta
                except Exception:
                    pass

    assert last_err is not None
    raise QwenAPIError(
        error_type=last_err.error_type,
        message=f"{last_err.message}（已重试 {retry_count} 次，总请求 {retry_count + 1} 次仍失败）",
        hint=last_err.hint,
        status_code=last_err.status_code,
        raw_output=last_err.raw_output,
        retryable=False,
        finish_reason=last_err.finish_reason,
    )


def cold_start_init(
    stock_code: str,
    stock_name: str,
    as_of_date: str,
    persist: bool = True,
    use_builtin_demo: bool = False,
    client_factory: Optional[Callable[[str, str, float], Any]] = None,
    dotenv_path: Optional[Path] = None,
) -> L2Graph:
    """冷启动建图：支持真实 Qwen API 建图或内置演示冷启动（当 use_builtin_demo=True 时）。"""
    code, cutoff = stock_code.upper(), as_of_date[:10]
    m_data = fetch_market_data(code, cutoff)
    pi_info = verify_priced_in(code, cutoff, sentiment_sign=1)
    has_real_news = (m_data.get("underlying_data_origin") == "REAL_MARKET_API") and len(m_data.get("news", [])) > 0
    ev_type = "EMPIRICAL_NEWS_FILING" if has_real_news else "COLD_START_PRIOR"
    seed_ev = record_l4_event(
        code,
        {
            "published_at": f"{cutoff} 09:00:00",
            "source": "L3冷启动基线",
            "title": f"{stock_name}冷启动先验锚定",
            "content": pi_info["priced_in_desc"],
            "evidence_type": ev_type,
        },
        cutoff,
        evidence_type=ev_type,
        persist=persist,
    )
    ctx = {
        "stock_code": code,
        "stock_name": stock_name,
        "as_of_date": cutoff,
        "priced_in_info": pi_info,
        "event_id": seed_ev["event_id"],
        "evidence_type": ev_type,
    }
    if use_builtin_demo:
        graph = _heuristic_fallback(L2Graph, ctx)
    else:
        sys_p, usr_p = build_cold_start_prompt(code, stock_name, cutoff, m_data, pi_info, seed_event_id=seed_ev["event_id"])
        graph, _ = _call_llm_json(
            sys_p, usr_p, L2Graph, ctx, client_factory=client_factory, dotenv_path=dotenv_path
        )

    if ev_type == "COLD_START_PRIOR":
        for n in graph.thesis_nodes:
            n.confidence = min(n.confidence, 0.50)
            if not n.title.startswith("[待实证核验]"):
                n.title = f"[待实证核验] {n.title}"

    net_score = graph.compute_net_score(use_edges=True)
    if persist:
        L2_DIR.mkdir(parents=True, exist_ok=True)
        (L2_DIR / f"{code}.json").write_text(graph.model_dump_json(indent=2), encoding="utf-8")
        if L1_INDEX_PATH.exists() and code not in (l1_txt := L1_INDEX_PATH.read_text(encoding="utf-8")):
            bull_c = sum(1 for n in graph.thesis_nodes if n.status == "ACTIVE" and n.type == "BULLISH_LOGIC")
            bear_c = sum(1 for n in graph.thesis_nodes if n.status == "ACTIVE" and n.type == "BEARISH_LOGIC")
            st_label = "偏多" if net_score > 0.2 else ("偏空" if net_score < -0.2 else "震荡筑底")
            L1_INDEX_PATH.write_text(
                l1_txt.rstrip()
                + f"\n  - `{code}` **{stock_name}** [当前净状态: {st_label}({net_score:+.2f}) | 活跃利好:{bull_c} | 活跃利空:{bear_c}]：冷启动建图标的 → L2 图谱：`memory/L2_graphs/{code}.json`\n",
                encoding="utf-8",
            )
    return graph


def _execute_graph_pipeline_core(
    stock_code: str,
    new_event: dict,
    as_of_date: str,
    stock_name: str = "",
    persist: bool = False,
    use_edges: bool = True,
    max_hops: int = 2,
    enable_invalidation: bool = True,
    enable_priced_in: bool = True,
    alpha: float = 0.8,
    lambda_decay: float = 0.6,
    method_tag: Optional[str] = None,
    use_builtin_demo: bool = False,
    use_cache: bool = True,
    priced_in_override: Optional[dict] = None,
    initial_graph: Optional[L2Graph] = None,
    client_factory: Optional[Callable[[str, str, float], Any]] = None,
    dotenv_path: Optional[Path] = None,
    retry_sleep_sec: float = 1.0,
) -> dict:
    code, cutoff = stock_code.upper(), as_of_date[:10]
    cfg = load_qwen_config(dotenv_path=dotenv_path)
    model_name = cfg["model"]

    if initial_graph is not None:
        graph = initial_graph.model_copy(deep=True)
    else:
        loaded_graph = load_l2_graph(code, as_of_date=cutoff)
        if loaded_graph is not None:
            graph = loaded_graph
        else:
            graph = cold_start_init(
                code,
                stock_name or code,
                cutoff,
                persist=persist,
                use_builtin_demo=use_builtin_demo,
                client_factory=client_factory,
                dotenv_path=dotenv_path,
            )

    before_graph = graph.model_copy(deep=True)
    before_graph.is_historical_view = graph.is_historical_view
    before_score_edges = before_graph.compute_net_score(alpha=alpha, lambda_decay=lambda_decay, use_edges=True)
    before_score_no_edges = before_graph.compute_net_score(alpha=alpha, lambda_decay=lambda_decay, use_edges=False)
    before_score = before_score_edges if use_edges else before_score_no_edges

    ev_text = f"{new_event.get('title', '')} {new_event.get('content', '')} {new_event.get('snippet', '')}"
    polarity = classify_event_polarity(ev_text)
    contagion_paths = (
        find_contagion_paths(ev_text, code, lambda_decay=lambda_decay, max_hops=max_hops, event_polarity=polarity)
        if use_edges and max_hops > 0
        else []
    )
    direct_mention = (graph.stock_name in ev_text) or (code in ev_text)
    default_ev_type = "SUPPLY_CHAIN_TRANSMISSION" if (contagion_paths and not direct_mention) else "EMPIRICAL_NEWS_FILING"
    ev_type = new_event.get("evidence_type") or default_ev_type

    ev_rec = record_l4_event(code, new_event, cutoff, evidence_type=ev_type, persist=False)
    ev_id, pub_at = ev_rec["event_id"], ev_rec["published_at"]

    sign = -1 if polarity < 0 else 1
    if priced_in_override is not None:
        pi_info = dict(priced_in_override)
    elif isinstance(new_event.get("priced_in_override"), dict):
        pi_info = dict(new_event["priced_in_override"])
    else:
        pi_info = verify_priced_in(code, cutoff, sentiment_sign=sign)

    sys_p, usr_p = build_belief_revision_prompt(
        graph,
        pi_info,
        new_event,
        cutoff,
        event_id=ev_id,
        contagion_paths=contagion_paths,
        event_polarity=polarity,
        enable_invalidation=enable_invalidation,
        enable_priced_in=enable_priced_in,
    )
    ctx = {
        "l2_graph": graph,
        "priced_in_info": pi_info,
        "new_event": new_event,
        "as_of_date": cutoff,
        "event_id": ev_id,
        "published_at": pub_at,
        "contagion_paths": contagion_paths,
        "event_polarity": polarity,
    }

    from_cache = False
    cache_key_str = f"{method_tag or 'default'}_{ ev_text[:80]}" if method_tag else ev_text[:80]
    cache_file = _graph_cache_file(code, cutoff, cache_key_str, model_name)
    raw_response_text = ""

    if use_builtin_demo:
        inf_resp = _heuristic_fallback(InferenceResponse, ctx)
        raw_response_text = inf_resp.model_dump_json()
        p_tok = _estimate_tokens(sys_p + "\n" + usr_p)
        c_tok = _estimate_tokens(raw_response_text)
        exec_meta = ExecutionMeta(
            storage_read_mode=pi_info.get("storage_read_mode", "DISK_CACHE"),
            underlying_data_origin=pi_info.get("underlying_data_origin", "SYNTHETIC_SIMULATION"),
            inference_mode="RESPONSE_CACHE_HIT",
            call_origin="RESPONSE_CACHE_HIT",
            model_name="内置演示数据 (未调用 Qwen API)",
            base_url="-",
            token_count_type="MISSING_OR_ESTIMATED",
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            estimated_tokens=p_tok + c_tok,
            fallback_reason="用户点击“使用演示结果”按钮（未发起网络请求）",
            retry_count=0,
            finish_reason="builtin_demo",
            json_repaired=False,
            latency_ms=0,
        )
    else:
        if use_cache and cache_file.exists():
            try:
                cached_json = json.loads(cache_file.read_text(encoding="utf-8"))
                norm_cached = _normalize_inference_dict(cached_json["inference"], ctx, require_all_forecasts=False)
                inf_resp = InferenceResponse.model_validate(norm_cached)
                exec_meta = ExecutionMeta.model_validate(cached_json["execution_meta"])
                exec_meta.inference_mode = "RESPONSE_CACHE_HIT"
                exec_meta.call_origin = "RESPONSE_CACHE_HIT"
                raw_response_text = cached_json.get("raw_response_text") or inf_resp.model_dump_json()
                from_cache = True
            except Exception:
                from_cache = False

        if not from_cache:
            inf_resp, exec_meta, trace_obj = _call_llm_json(
                sys_p,
                usr_prompt=usr_p,
                model_cls=InferenceResponse,
                ctx=ctx,
                client_factory=client_factory,
                dotenv_path=dotenv_path,
                retry_sleep_sec=retry_sleep_sec,
                method_tag=method_tag,
                use_cache=use_cache,
                return_trace=True,
            )
            raw_response_text = trace_obj.get("raw_response_text", "")
            from_cache = exec_meta.call_origin == "RESPONSE_CACHE_HIT"
            try:
                GRAPH_DEMO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(
                    json.dumps(
                        {
                            "inference": inf_resp.model_dump(),
                            "execution_meta": exec_meta.model_dump(),
                            "raw_response_text": raw_response_text,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass

    valid_node_ids = {n.id for n in graph.thesis_nodes}
    valid_ops: list[PatchOp] = []
    for op in inf_resp.patch_ops:
        if not enable_invalidation and op.op == "INVALIDATE":
            continue
        if not enable_priced_in and op.op == "PRICED_IN":
            continue
        op.evidence_id = ev_id
        op.published_at = pub_at[:10]
        if op.op in ("CONFIRM", "INVALIDATE", "PRICED_IN"):
            if op.target_node_id not in valid_node_ids:
                if graph.thesis_nodes:
                    op.target_node_id = graph.thesis_nodes[0].id
                else:
                    continue
        if op.op == "ADD_NODE" and op.new_node:
            op.new_node.created_at = cutoff
            op.new_node.updated_at = cutoff
            op.new_node.evidence_pointers = [ev_id]
            if not op.new_node.invalidation_condition or not op.new_node.invalidation_condition.strip():
                op.new_node.invalidation_condition = "后续经营数据或订单指引未达预期"
            if op.new_edge and op.new_edge.target not in valid_node_ids and op.new_edge.source not in valid_node_ids:
                op.new_edge = None
        valid_ops.append(op)
    inf_resp.patch_ops = valid_ops

    after_graph = patch_l2_graph(
        code,
        inf_resp.patch_ops,
        cutoff,
        use_edges=use_edges,
        persist=persist,
        extra_l4_events=[ev_rec],
        initial_graph=graph,
    )
    after_score_no_edges = after_graph.compute_net_score(alpha=alpha, lambda_decay=lambda_decay, use_edges=False)
    after_score_with_edges = after_graph.compute_net_score(alpha=alpha, lambda_decay=lambda_decay, use_edges=True)
    final_after_score = after_graph.compute_net_score(alpha=alpha, lambda_decay=lambda_decay, use_edges=use_edges)

    consistency_warnings = check_inference_consistency(inf_resp)

    exec_meta_dict = exec_meta.model_dump()
    exec_meta_dict["persistence_mode"] = "DISK_COMMITTED" if persist else "IN_MEMORY_PREVIEW"
    exec_meta_dict["total_tokens"] = (exec_meta.prompt_tokens or 0) + (exec_meta.completion_tokens or 0)
    exec_meta_dict["llm_model"] = exec_meta.model_name
    exec_meta_dict["from_cache"] = from_cache
    exec_meta_dict["is_demo_fallback"] = use_builtin_demo

    status_label = (
        "当前为演示数据，未调用 Qwen API"
        if use_builtin_demo
        else ("本地图谱缓存命中（未重复发起 Qwen API 请求）" if from_cache else f"真实 Qwen API ({exec_meta.model_name}) 图谱推演成功")
    )

    return {
        "stock_code": code,
        "stock_name": after_graph.stock_name,
        "as_of_date": cutoff,
        "event_id": ev_id,
        "event_polarity": polarity,
        "evidence_type": ev_type,
        "before_score": before_score,
        "after_score": final_after_score,
        "score_before": before_score,
        "score_after": final_after_score,
        "graph_before": before_graph,
        "graph_after": after_graph,
        "inference": inf_resp,
        "llm_trace": {
            "system_prompt": sys_p,
            "user_prompt": usr_p,
            "raw_response_text": raw_response_text,
        },
        "consistency_warnings": consistency_warnings,
        "after_score_with_edges": after_score_with_edges,
        "after_score_no_edges": after_score_no_edges,
        "priced_in_info": pi_info,
        "contagion_paths": contagion_paths,
        "patch_ops": [op.model_dump() for op in inf_resp.patch_ops],
        "contagion_impact": inf_resp.contagion_impact,
        "forecast": {
            "t1": inf_resp.t1_forecast.model_dump(),
            "t5": inf_resp.t5_forecast.model_dump(),
            "t20": inf_resp.t20_forecast.model_dump(),
        },
        "watch_indicators": inf_resp.watch_indicators,
        "execution_meta": exec_meta_dict,
        "before_nodes": [n.model_dump() for n in before_graph.thesis_nodes],
        "after_nodes": [n.model_dump() for n in after_graph.thesis_nodes],
        "from_cache": from_cache,
        "is_demo_fallback": use_builtin_demo,
        "status_label": status_label,
    }


def run_agent_pipeline(
    stock_code: str,
    new_event: dict,
    as_of_date: str,
    stock_name: str = "",
    persist: bool = False,
    use_edges: bool = True,
    max_hops: int = 2,
    enable_invalidation: bool = True,
    enable_priced_in: bool = True,
    alpha: float = 0.8,
    lambda_decay: float = 0.6,
    method_tag: Optional[str] = None,
    use_cache: bool = True,
    priced_in_override: Optional[dict] = None,
    initial_graph: Optional[L2Graph] = None,
    client_factory: Optional[Callable[[str, str, float], Any]] = None,
    dotenv_path: Optional[Path] = None,
    retry_sleep_sec: float = 1.0,
) -> dict:
    """真实调用 Qwen API 执行四层动态金融知识图谱推演（失败直接抛 QwenAPIError，绝不静默降级）。"""
    return _execute_graph_pipeline_core(
        stock_code=stock_code,
        new_event=new_event,
        as_of_date=as_of_date,
        stock_name=stock_name,
        persist=persist,
        use_edges=use_edges,
        max_hops=max_hops,
        enable_invalidation=enable_invalidation,
        enable_priced_in=enable_priced_in,
        alpha=alpha,
        lambda_decay=lambda_decay,
        method_tag=method_tag,
        use_builtin_demo=False,
        use_cache=use_cache,
        priced_in_override=priced_in_override,
        initial_graph=initial_graph,
        client_factory=client_factory,
        dotenv_path=dotenv_path,
        retry_sleep_sec=retry_sleep_sec,
    )


def run_builtin_graph_demo_pipeline(
    stock_code: str,
    new_event: dict,
    as_of_date: str,
    stock_name: str = "",
    persist: bool = False,
    use_edges: bool = True,
    max_hops: int = 2,
    priced_in_override: Optional[dict] = None,
    initial_graph: Optional[L2Graph] = None,
) -> dict:
    """离线零网络请求执行内置图谱演示（仅在用户明确点击“使用演示结果”按钮时触发）。"""
    return _execute_graph_pipeline_core(
        stock_code=stock_code,
        new_event=new_event,
        as_of_date=as_of_date,
        stock_name=stock_name,
        persist=persist,
        use_edges=use_edges,
        max_hops=max_hops,
        use_builtin_demo=True,
        use_cache=False,
        priced_in_override=priced_in_override,
        initial_graph=initial_graph,
    )


def cold_start_stock(
    stock_code: str,
    stock_name: str,
    as_of_date: str = "2026-10-14",
    persist: bool = False,
    use_builtin_demo: bool = True,
) -> L2Graph:
    """兼容别名：调用 cold_start_init。"""
    return cold_start_init(
        stock_code,
        stock_name,
        as_of_date=as_of_date,
        persist=persist,
        use_builtin_demo=use_builtin_demo,
    )


def run_agent_inference(
    stock_code: str,
    stock_name_or_event: str | dict,
    event_or_as_of: dict | str = "2026-10-14",
    as_of_date: str = "2026-10-14",
    persist: bool = False,
    use_edges: bool = True,
    use_builtin_demo: bool = False,
    use_cache: bool = True,
) -> dict:
    """兼容别名：支持真实 Qwen API 图谱推演与内置离线图谱演示。"""
    if isinstance(stock_name_or_event, dict):
        ev = stock_name_or_event
        dt = event_or_as_of if isinstance(event_or_as_of, str) else as_of_date
        s_name = stock_code
    else:
        s_name = stock_name_or_event
        ev = event_or_as_of if isinstance(event_or_as_of, dict) else {}
        dt = as_of_date

    if use_builtin_demo:
        return run_builtin_graph_demo_pipeline(
            stock_code, ev, as_of_date=dt, stock_name=s_name, persist=persist, use_edges=use_edges
        )
    return run_agent_pipeline(
        stock_code,
        ev,
        as_of_date=dt,
        stock_name=s_name,
        persist=persist,
        use_edges=use_edges,
        use_cache=use_cache,
    )
