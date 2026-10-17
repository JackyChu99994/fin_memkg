import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_loop import (
    QwenAPIError,
    analyze_demo_event,
    call_qwen_json,
    get_builtin_demo_result,
    load_qwen_config,
    load_sample_demo_event,
    run_agent_pipeline,
    run_builtin_graph_demo_pipeline,
)
from tools import (
    find_contagion_paths,
    load_l2_graph,
    patch_l2_graph,
    verify_priced_in,
)


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeUsage:
    def __init__(self, total_tokens: int = 128):
        self.prompt_tokens = 80
        self.completion_tokens = 48
        self.total_tokens = total_tokens


class _FakeCompletionResponse:
    def __init__(self, content: str, total_tokens: int = 128):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage(total_tokens)


class _FakeChatCompletions:
    def __init__(self, handler):
        self._handler = handler
        self.call_count = 0
        self.last_kwargs = None

    def create(self, **kwargs):
        self.call_count += 1
        self.last_kwargs = kwargs
        return self._handler(**kwargs)


class _FakeOpenAIClient:
    def __init__(self, handler):
        self.completions_api = _FakeChatCompletions(handler)
        self.chat = type("ChatNamespace", (), {"completions": self.completions_api})()


class TestQwenFirstEditionDemo(unittest.TestCase):
    """Verify all 10 requirements for the Qwen OpenAI-compatible First-Edition Demo."""

    def setUp(self):
        self.sample_event = load_sample_demo_event()

    def test_1_sample_event_loads_properly(self):
        self.assertEqual(self.sample_event["stock_code"], "300308.SZ")
        self.assertTrue(len(self.sample_event["title"]) > 5)
        self.assertTrue(len(self.sample_event["content"]) > 10)

    def test_2_strictly_reads_only_qwen_configs_and_ignores_openai_vars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dotenv = Path(tmpdir) / ".env"
            empty_dotenv.write_text("", encoding="utf-8")

            clean_env = {
                "OPENAI_API_KEY": "sk-should-be-ignored",
                "OPENAI_BASE_URL": "https://code.rayinai.com/v1",
                "OPENAI_MODEL": "gpt-5.5",
                "LLM_API_KEY": "sk-also-ignored",
                "DEEPSEEK_API_KEY": "sk-deepseek-ignored",
            }
            with patch.dict(os.environ, clean_env, clear=True):
                cfg = load_qwen_config(dotenv_path=empty_dotenv)
                self.assertFalse(cfg["ready"])
                self.assertFalse(cfg["has_api_key"])
                self.assertIn("QWEN_API_KEY", cfg["missing_fields"])
                self.assertEqual(
                    cfg["base_url"],
                    "https://dashscope.aliyuncs.com/compatible-mode/v1",
                )
                self.assertEqual(cfg["model"], "qwen-plus")

    def test_3_env_priority_over_dotenv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dotenv_file = Path(tmpdir) / ".env"
            dotenv_file.write_text(
                "QWEN_API_KEY=dotenv_key\nQWEN_MODEL=qwen-turbo\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"QWEN_API_KEY": "env_override_key", "QWEN_MODEL": "qwen-max"},
                clear=True,
            ):
                cfg = load_qwen_config(dotenv_path=dotenv_file)
                self.assertTrue(cfg["ready"])
                self.assertEqual(cfg["api_key"], "env_override_key")
                self.assertEqual(cfg["model"], "qwen-max")

    def test_4_missing_config_raises_clear_error_without_network_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dotenv = Path(tmpdir) / ".env"
            empty_dotenv.write_text("", encoding="utf-8")
            called = {"count": 0}

            def _should_not_be_called(api_key, base_url, timeout):
                called["count"] += 1
                raise AssertionError("Network client must not be initialized when config is missing")

            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(QwenAPIError) as ctx:
                    call_qwen_json(
                        prompt="sys",
                        input_text="user",
                        client_factory=_should_not_be_called,
                        dotenv_path=empty_dotenv,
                    )
                self.assertEqual(called["count"], 0)
                self.assertEqual(ctx.exception.error_type, "配置缺失")
                self.assertIn("QWEN_API_KEY", ctx.exception.message)

    def test_5_mock_successful_qwen_json_analysis_and_schema(self):
        valid_json = json.dumps(
            {
                "event_summary": "2025Q2北美800G光模块出货量环比增长35%，硅光渗透率提升带动毛利率改善。",
                "entities": [
                    {"name": "中际旭创", "type": "公司"},
                    {"name": "800G光模块", "type": "产品"},
                ],
                "event_type": "供应链与业绩催化",
                "impact_direction": "positive",
                "risk_level": "low",
                "confidence": 0.91,
                "evidence": ["800G环比高增35%", "毛利率提升1.6pct"],
            },
            ensure_ascii=False,
        )
        fake_client = _FakeOpenAIClient(lambda **kwargs: _FakeCompletionResponse(valid_json))

        with patch.dict(
            os.environ,
            {
                "QWEN_API_KEY": "test_key_do_not_print",
                "QWEN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "QWEN_MODEL": "qwen-plus",
            },
            clear=True,
        ):
            res = analyze_demo_event(
                self.sample_event,
                use_cache=False,
                client_factory=lambda k, b, t: fake_client,
            )
            self.assertTrue(res["ok"])
            self.assertTrue(res["call_success"])
            self.assertFalse(res["is_demo_fallback"])
            self.assertEqual(fake_client.completions_api.call_count, 1)
            self.assertEqual(fake_client.completions_api.last_kwargs["temperature"], 0)
            analysis = res["analysis"]
            self.assertEqual(analysis["impact_direction"], "positive")
            self.assertAlmostEqual(analysis["confidence"], 0.91)
            self.assertEqual(res["model"], "qwen-plus")

    def test_6_invalid_json_fails_immediately_with_zero_retry(self):
        fake_client = _FakeOpenAIClient(
            lambda **kwargs: _FakeCompletionResponse("这不是JSON输出，而是一段普通文本。")
        )
        with patch.dict(
            os.environ,
            {"QWEN_API_KEY": "test_key", "QWEN_MODEL": "qwen-plus"},
            clear=True,
        ):
            with self.assertRaises(QwenAPIError) as ctx:
                analyze_demo_event(
                    self.sample_event,
                    use_cache=False,
                    client_factory=lambda k, b, t: fake_client,
                )
            self.assertEqual(fake_client.completions_api.call_count, 1)
            self.assertEqual(ctx.exception.error_type, "JSON 解析失败")

    def test_7_http_401_404_502_and_timeout_errors_never_auto_fallback(self):
        error_cases = [
            (Exception("Error code: 401 - Invalid API-key provided"), "认证失败 (HTTP 401)"),
            (Exception("Error code: 404 - Model not found"), "接口或模型不存在 (HTTP 404)"),
            (Exception("Error code: 502 - Bad Gateway"), "服务端网关异常 (HTTP 502)"),
            (TimeoutError("Request timed out after 30s"), "请求超时"),
        ]
        for exc_obj, expected_type in error_cases:
            fake_client = _FakeOpenAIClient(lambda _exc=exc_obj, **kwargs: (_ for _ in ()).throw(_exc))
            with patch.dict(
                os.environ,
                {"QWEN_API_KEY": "test_key", "QWEN_MODEL": "qwen-plus"},
                clear=True,
            ):
                with self.assertRaises(QwenAPIError) as ctx:
                    analyze_demo_event(
                        self.sample_event,
                        use_cache=False,
                        client_factory=lambda k, b, t: fake_client,
                    )
                self.assertEqual(fake_client.completions_api.call_count, 1)
                self.assertEqual(ctx.exception.error_type, expected_type)

    def test_8_builtin_demo_result_is_explicitly_labeled(self):
        demo_res = get_builtin_demo_result(self.sample_event)
        self.assertTrue(demo_res["ok"])
        self.assertTrue(demo_res["is_demo_fallback"])
        self.assertIn("演示数据，未调用 Qwen API", demo_res["status_label"])


class TestKnowledgeGraphIntegrationWithQwen(unittest.TestCase):
    """Verify that the 4-layer Dynamic Knowledge Graph + L3 Priced-in + 2-Hop Contagion works with Qwen API."""

    def test_9_historical_rollback_and_overwrite_protection(self):
        g = load_l2_graph("300308.SZ", as_of_date="2026-09-01")
        self.assertIsNotNone(g)
        self.assertTrue(g.is_historical_view)
        with self.assertRaises(ValueError):
            patch_l2_graph(
                stock_code="300308.SZ",
                patch_ops=[],
                as_of_date="2026-09-01",
                persist=True,
                initial_graph=g,
            )

    def test_10_two_hop_three_node_contagion_and_priced_in(self):
        paths = find_contagion_paths(
            "上游磷化铟(InP)晶圆外延片大厂产线停产检修两周，Lumentum 200G EML光芯片现货跳涨15%",
            "300308.SZ",
            max_hops=2,
        )
        self.assertTrue(len(paths) >= 1)
        first = paths[0]
        self.assertEqual(first["target"], "300308.SZ")
        self.assertTrue(first["actual_hops"] >= 1)

        chk = verify_priced_in("300308.SZ", "2026-10-14", sentiment_sign=1)
        self.assertIn("priced_in_ratio", chk)
        self.assertIn("close_rank_pct_60d", chk)

    def test_11_builtin_graph_demo_and_live_qwen_graph_pipeline(self):
        event_input = {
            "published_at": "2026-10-14 09:30:00",
            "source": "海外供应链核心快讯",
            "title": "英伟达Blackwell B200机柜因连接器与散热背板公差缺陷推迟大批量交付一个季度",
            "content": "受机柜散热方案改版影响，北美云厂商配套1.6T光模块集中提货节点顺延至明年Q2。",
            "evidence_type": "EMPIRICAL_NEWS_FILING",
        }
        demo_bundle = run_builtin_graph_demo_pipeline(
            stock_code="300308.SZ",
            new_event=event_input,
            as_of_date="2026-10-14",
            stock_name="中际旭创",
            persist=False,
        )
        self.assertTrue(demo_bundle["is_demo_fallback"])
        self.assertIn("graph_before", demo_bundle)
        self.assertIn("graph_after", demo_bundle)
        self.assertIn("演示数据，未调用 Qwen API", demo_bundle["status_label"])

        mock_graph_llm_json = json.dumps(
            {
                "patch_ops": [
                    {
                        "op": "INVALIDATE",
                        "target_node_id": "TH_01",
                        "reason": "Blackwell机柜交付推迟直接冲击1.6T光模块放量节奏",
                        "evidence_id": "EV_20261014_01_mock",
                        "published_at": "2026-10-14",
                    }
                ],
                "contagion_impact": "北美算力链短期排产顺延",
                "t1_forecast": {"direction": "BEARISH", "confidence": 0.85, "reasoning": "突发推迟利空压制短线情绪"},
                "t5_forecast": {"direction": "BEARISH", "confidence": 0.80, "reasoning": "原核心多头论点被证伪"},
                "t20_forecast": {"direction": "NEUTRAL", "confidence": 0.65, "reasoning": "等待次季排产修复"},
                "watch_indicators": ["北美云厂商CapEx指引", "1.6T光模块提货节奏"],
            },
            ensure_ascii=False,
        )
        fake_client = _FakeOpenAIClient(lambda **kwargs: _FakeCompletionResponse(mock_graph_llm_json))
        with patch.dict(
            os.environ,
            {"QWEN_API_KEY": "test_key", "QWEN_MODEL": "qwen-plus"},
            clear=True,
        ):
            live_bundle = run_agent_pipeline(
                stock_code="300308.SZ",
                new_event=event_input,
                as_of_date="2026-10-14",
                stock_name="中际旭创",
                persist=False,
                use_cache=False,
                client_factory=lambda k, b, t: fake_client,
            )
            self.assertFalse(live_bundle["is_demo_fallback"])
            self.assertEqual(live_bundle["forecast"]["t1"]["direction"], "BEARISH")
            self.assertEqual(live_bundle["execution_meta"]["llm_model"], "qwen-plus")
            self.assertEqual(fake_client.completions_api.call_count, 1)


if __name__ == "__main__":
    unittest.main()
