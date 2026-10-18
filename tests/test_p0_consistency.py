import inspect
import json
import math
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_loop import (
    GRAPH_MAX_TOKENS,
    GRAPH_MAX_TOKENS_RETRY,
    QwenAPIError,
    run_agent_pipeline,
    run_builtin_graph_demo_pipeline,
)
from eval_benchmark import (
    METHOD_B0,
    RUNS_DIR,
    _bootstrap_ci95,
    _compute_macro_f1_pct,
    _make_blind_input,
    classify_car_3class,
    evaluate_single_case_method,
    load_real_fin_events_12,
    recompute_run_summary_from_records,
)
from schema import HorizonPred, InferenceResponse, check_inference_consistency
from tools import classify_event_polarity, find_contagion_paths


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str, finish_reason: str = "stop"):
        self.message = _FakeMessage(content)
        self.finish_reason = finish_reason


class _FakeUsage:
    def __init__(self, prompt_tokens: int = 120, completion_tokens: int = 180):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = prompt_tokens + completion_tokens


class _FakeCompletionResponse:
    def __init__(self, content: str, finish_reason: str = "stop"):
        self.choices = [_FakeChoice(content, finish_reason=finish_reason)]
        self.usage = _FakeUsage()


class _FakeChatCompletions:
    def __init__(self, handler):
        self._handler = handler
        self.call_count = 0
        self.calls_kwargs = []

    def create(self, **kwargs):
        self.call_count += 1
        self.calls_kwargs.append(kwargs)
        return self._handler(self.call_count, **kwargs)


class _FakeOpenAIClient:
    def __init__(self, handler):
        self.completions_api = _FakeChatCompletions(handler)
        self.chat = type("ChatNamespace", (), {"completions": self.completions_api})()


def _build_valid_compact_inference_json() -> str:
    return json.dumps(
        {
            "event_summary": "英伟达Blackwell B200机柜交付推迟一个季度，短期压制1.6T光模块提货节奏。",
            "entities": [
                {"name": "中际旭创", "type": "公司"},
                {"name": "Blackwell B200", "type": "产品"},
            ],
            "event_type": "供应链与排产利空",
            "impact_direction": "negative",
            "risk_level": "high",
            "event_confidence": 0.88,
            "patch_ops": [
                {
                    "op": "INVALIDATE",
                    "target_node_id": "TH_01",
                    "reason": "Blackwell机柜推迟交付直接冲击1.6T光模块Q4放量节奏",
                    "evidence_id": "EV_20261014_01_mock",
                    "published_at": "2026-10-14",
                }
            ],
            "contagion_impact": "北美算力机柜交付顺延传导至高速光模块排产",
            "t1_forecast": {"direction": "BEARISH", "confidence": 0.85, "reasoning": "突发推迟利空压制短线情绪"},
            "t5_forecast": {"direction": "BEARISH", "confidence": 0.80, "reasoning": "核心多头论点被证伪"},
            "t20_forecast": {"direction": "NEUTRAL", "confidence": 0.65, "reasoning": "等待次季排产修复"},
            "watch_indicators": ["北美云厂商CapEx指引", "1.6T光模块提货节奏"],
        },
        ensure_ascii=False,
    )


class TestP0Consistency(unittest.TestCase):
    """P0-1 / P0-2 / P0-3 专项回归测试（纯离线执行，不发起任何真实网络请求）。"""

    def setUp(self):
        self.event_a = {
            "published_at": "2026-10-14 09:30:00",
            "source": "海外供应链核心快讯",
            "title": "英伟达Blackwell B200机柜因连接器与散热背板公差缺陷推迟大批量交付一个季度",
            "content": "受机柜散热方案改版影响，北美云厂商配套1.6T光模块集中提货节点顺延至明年Q2。",
            "evidence_type": "EMPIRICAL_NEWS_FILING",
        }

    def test_1_classify_event_polarity_and_negation(self):
        for neg_sample in (
            "英伟达Blackwell B200机柜因连接器与散热背板公差缺陷推迟大批量交付",
            "核心客户突发砍单并下调四季度排产指引",
            "上游晶圆厂产线停产检修两周导致断供与短缺",
            "公司因信披违规遭立案调查并处以罚款，产品召回且降价跌破成本线",
            "半年度业绩预减且大股东宣布减持，叠加出口管制与关税限制导致亏损",
        ):
            self.assertEqual(classify_event_polarity(neg_sample), -1)

        for pos_sample in (
            "三季报净利预增165%超预期，管理层上修全年指引",
            "800G产线扩产满产，1.6T光模块实现良率突破并规模量产",
            "成功中标海外算力大单，核心产品提价涨价，公司启动大额回购且新药获批",
        ):
            self.assertEqual(classify_event_polarity(pos_sample), 1)

        self.assertNotEqual(classify_event_polarity("项目进展正常，未推迟交付"), -1)
        self.assertNotEqual(classify_event_polarity("下游需求稳健，没有砍单迹象"), -1)
        self.assertNotEqual(classify_event_polarity("产线运转正常，无缺陷且不降价"), -1)

    def test_2_scenario_a_blackwell_delay_never_bullish_and_lowers_score(self):
        out = run_builtin_graph_demo_pipeline(
            stock_code="300308.SZ",
            new_event=self.event_a,
            as_of_date="2026-10-14",
            stock_name="中际旭创",
            persist=False,
        )
        inf: InferenceResponse = out["inference"]
        self.assertNotEqual(inf.t5_forecast.direction, "BULLISH")
        self.assertEqual(inf.t1_forecast.direction, "BEARISH")
        self.assertEqual(inf.t5_forecast.direction, "BEARISH")
        self.assertEqual(inf.impact_direction, "negative")

        has_bearish_or_invalidate = any(
            op.op == "INVALIDATE"
            or (op.op == "ADD_NODE" and op.new_node is not None and op.new_node.type == "BEARISH_LOGIC")
            for op in inf.patch_ops
        )
        self.assertTrue(has_bearish_or_invalidate)
        self.assertLess(out["score_after"], out["score_before"])
        self.assertEqual(len(out["consistency_warnings"]), 0)

    def test_3_scenario_b_priced_in_trap_triggers_priced_in_and_bearish_t5(self):
        event_b = {
            "published_at": "2026-10-14 09:30:00",
            "source": "深交所业绩预告",
            "title": "中际旭创披露前三季度净利预增165%，符合卖方一致预期上限",
            "content": "公司800G出货保持高景气，但前期股价已连续大涨28%，处于60日96%极高分位，获利盘兑现压力显著。",
            "evidence_type": "EMPIRICAL_NEWS_FILING",
        }
        out = run_builtin_graph_demo_pipeline(
            stock_code="300308.SZ",
            new_event=event_b,
            as_of_date="2026-10-14",
            stock_name="中际旭创",
            persist=False,
        )
        inf: InferenceResponse = out["inference"]
        self.assertTrue(any(op.op == "PRICED_IN" for op in inf.patch_ops))
        self.assertFalse(
            any(
                op.op == "ADD_NODE" and op.new_node is not None and op.new_node.type == "BULLISH_LOGIC"
                for op in inf.patch_ops
            )
        )
        self.assertEqual(inf.t5_forecast.direction, "BEARISH")

    def test_4_scenario_c_two_hop_contagion_negative_path_factor_and_bearish_t5(self):
        event_c = {
            "published_at": "2026-10-14 09:30:00",
            "source": "海外光电产业链快讯",
            "title": "上游磷化铟(InP)晶圆外延片大厂产线停产检修两周，Lumentum 200G EML光芯片现货跳涨15%",
            "content": "磷化铟衬底短缺传导至中游EML光芯片制造商Lumentum，导致下游800G/1.6T光模块厂面临物料配额收紧。",
            "evidence_type": "EMPIRICAL_NEWS_FILING",
        }
        out = run_builtin_graph_demo_pipeline(
            stock_code="300308.SZ",
            new_event=event_c,
            as_of_date="2026-10-14",
            stock_name="中际旭创",
            persist=False,
        )
        paths = out["contagion_paths"]
        self.assertTrue(len(paths) >= 1)
        top_p = paths[0]
        self.assertEqual(top_p["actual_hops"], 2)
        self.assertLess(top_p["path_factor"], 0.0)
        self.assertTrue(top_p["polarity_applied"])
        self.assertEqual(top_p["event_polarity"], -1)
        self.assertEqual(out["inference"].t5_forecast.direction, "BEARISH")
        self.assertEqual(out["inference"].impact_direction, "negative")

    def test_5_same_path_opposite_event_polarity_flips_path_factor(self):
        neg_paths = find_contagion_paths("北美云厂商与英伟达Blackwell推迟交付", "300308.SZ", event_polarity=-1)
        pos_paths = find_contagion_paths("北美云厂商与英伟达Blackwell出货超预期", "300308.SZ", event_polarity=+1)
        zero_paths = find_contagion_paths("北美云厂商与英伟达Blackwell动态跟踪", "300308.SZ", event_polarity=0)
        self.assertEqual(neg_paths[0]["path"], pos_paths[0]["path"])
        self.assertLess(neg_paths[0]["path_factor"], 0.0)
        self.assertGreater(pos_paths[0]["path_factor"], 0.0)
        self.assertTrue(neg_paths[0]["polarity_applied"])
        self.assertTrue(pos_paths[0]["polarity_applied"])
        self.assertFalse(zero_paths[0]["polarity_applied"])

        src = inspect.getsource(find_contagion_paths)
        for forbidden_kw in ("跌破7.3万", "超额交付", "拍卖价下调", "跌破2250"):
            self.assertNotIn(forbidden_kw, src)

    def test_6_market_gate_high_priced_in_with_positive_polarity_never_bullish(self):
        pos_event = {
            "published_at": "2026-10-14 09:30:00",
            "source": "公司公告",
            "title": "中际旭创800G与1.6T光模块大单中标，单季扩产超预期",
            "content": "公司海外核心客户加单超预期，产线满产。",
            "evidence_type": "EMPIRICAL_NEWS_FILING",
        }
        out = run_builtin_graph_demo_pipeline(
            stock_code="300308.SZ",
            new_event=pos_event,
            as_of_date="2026-10-14",
            stock_name="中际旭创",
            persist=False,
            priced_in_override={
                "stock_code": "300308.SZ",
                "as_of_date": "2026-10-14",
                "storage_read_mode": "IN_MEMORY",
                "underlying_data_origin": "SYNTHETIC_SIMULATION",
                "return_20d_pct": 32.0,
                "close_rank_pct_60d": 0.96,
                "range_pos_60d": 0.94,
                "turnover_anomaly": "HIGH",
                "priced_in_ratio": 0.90,
                "priced_in_desc": "预期兑现度90%，高位透支",
            },
        )
        inf: InferenceResponse = out["inference"]
        self.assertNotEqual(inf.t1_forecast.direction, "BULLISH")
        self.assertNotEqual(inf.t5_forecast.direction, "BULLISH")

    def test_7_consistency_check_warns_on_unexplained_negative_plus_bullish(self):
        contradictory_inf = InferenceResponse(
            event_summary="核心客户推迟提货导致短期出货受阻",
            event_type="供应链利空",
            impact_direction="negative",
            risk_level="high",
            event_confidence=0.88,
            patch_ops=[],
            contagion_impact="上游机柜正常交付带动下游景气上行。",
            t1_forecast=HorizonPred(direction="BULLISH", confidence=0.80, reasoning="看多"),
            t5_forecast=HorizonPred(direction="BULLISH", confidence=0.80, reasoning="看多"),
            t20_forecast=HorizonPred(direction="BULLISH", confidence=0.75, reasoning="看多"),
            watch_indicators=[],
        )
        self.assertTrue(len(check_inference_consistency(contradictory_inf)) >= 1)

    def test_8_p0_2_first_truncated_json_second_valid_succeeds_with_retry_count_1(self):
        truncated_json = '{"patch_ops": [{"op": "INVALIDATE", "target_node_id": "TH_01", "reason": "Blackwell推迟", "new_w'
        valid_json = _build_valid_compact_inference_json()

        def _handler(call_idx, **kwargs):
            if call_idx == 1:
                return _FakeCompletionResponse(truncated_json, finish_reason="stop")
            return _FakeCompletionResponse(valid_json, finish_reason="stop")

        fake_client = _FakeOpenAIClient(_handler)
        with patch.dict(os.environ, {"QWEN_API_KEY": "test_key", "QWEN_MODEL": "qwen-plus"}, clear=True):
            res = run_agent_pipeline(
                stock_code="300308.SZ",
                new_event=self.event_a,
                as_of_date="2026-10-14",
                stock_name="中际旭创",
                persist=False,
                use_cache=False,
                client_factory=lambda k, b, t: fake_client,
                retry_sleep_sec=0.0,
            )
            self.assertEqual(fake_client.completions_api.call_count, 2)
            self.assertEqual(res["execution_meta"]["retry_count"], 1)
            self.assertEqual(res["forecast"]["t5"]["direction"], "BEARISH")

    def test_9_p0_2_first_finish_reason_length_second_valid_increases_max_tokens(self):
        valid_json = _build_valid_compact_inference_json()

        def _handler(call_idx, **kwargs):
            if call_idx == 1:
                return _FakeCompletionResponse(valid_json[:220], finish_reason="length")
            return _FakeCompletionResponse(valid_json, finish_reason="stop")

        fake_client = _FakeOpenAIClient(_handler)
        with patch.dict(os.environ, {"QWEN_API_KEY": "test_key", "QWEN_MODEL": "qwen-plus"}, clear=True):
            res = run_agent_pipeline(
                stock_code="300308.SZ",
                new_event=self.event_a,
                as_of_date="2026-10-14",
                stock_name="中际旭创",
                persist=False,
                use_cache=False,
                client_factory=lambda k, b, t: fake_client,
                retry_sleep_sec=0.0,
            )
            self.assertEqual(fake_client.completions_api.call_count, 2)
            first_max = fake_client.completions_api.calls_kwargs[0]["max_tokens"]
            second_max = fake_client.completions_api.calls_kwargs[1]["max_tokens"]
            self.assertEqual(first_max, GRAPH_MAX_TOKENS)
            self.assertEqual(second_max, GRAPH_MAX_TOKENS_RETRY)
            self.assertGreater(second_max, first_max)
            self.assertEqual(res["execution_meta"]["retry_count"], 1)
            self.assertEqual(res["execution_meta"]["finish_reason"], "stop")

    def test_10_p0_2_http_401_never_retries(self):
        def _handler(call_idx, **kwargs):
            raise Exception("Error code: 401 - Invalid API-key provided")

        fake_client = _FakeOpenAIClient(_handler)
        with patch.dict(os.environ, {"QWEN_API_KEY": "bad_key", "QWEN_MODEL": "qwen-plus"}, clear=True):
            with self.assertRaises(QwenAPIError) as ctx:
                run_agent_pipeline(
                    stock_code="300308.SZ",
                    new_event=self.event_a,
                    as_of_date="2026-10-14",
                    stock_name="中际旭创",
                    persist=False,
                    use_cache=False,
                    client_factory=lambda k, b, t: fake_client,
                    retry_sleep_sec=0.0,
                )
            self.assertEqual(fake_client.completions_api.call_count, 1)
            self.assertEqual(ctx.exception.status_code, 401)

    def test_11_p0_2_both_attempts_truncated_raises_qwen_api_error_without_heuristic_fallback(self):
        truncated_json = '{"patch_ops": [{"op": "INVALIDATE", "target_node_id": "TH_01", "reason": "截断测试", "new_w'

        def _handler(call_idx, **kwargs):
            return _FakeCompletionResponse(truncated_json, finish_reason="length")

        fake_client = _FakeOpenAIClient(_handler)
        with patch.dict(os.environ, {"QWEN_API_KEY": "test_key", "QWEN_MODEL": "qwen-plus"}, clear=True):
            with self.assertRaises(QwenAPIError) as ctx:
                run_agent_pipeline(
                    stock_code="300308.SZ",
                    new_event=self.event_a,
                    as_of_date="2026-10-14",
                    stock_name="中际旭创",
                    persist=False,
                    use_cache=False,
                    client_factory=lambda k, b, t: fake_client,
                    retry_sleep_sec=0.0,
                )
            self.assertEqual(fake_client.completions_api.call_count, 2)
            self.assertEqual(ctx.exception.error_type, "输出被截断")
            self.assertIn("已重试 1 次", ctx.exception.message)

    def test_12_p0_2_valid_compact_json_succeeds_first_try_with_retry_count_0(self):
        valid_json = _build_valid_compact_inference_json()

        def _handler(call_idx, **kwargs):
            return _FakeCompletionResponse(valid_json, finish_reason="stop")

        fake_client = _FakeOpenAIClient(_handler)
        with patch.dict(os.environ, {"QWEN_API_KEY": "test_key", "QWEN_MODEL": "qwen-plus"}, clear=True):
            res = run_agent_pipeline(
                stock_code="300308.SZ",
                new_event=self.event_a,
                as_of_date="2026-10-14",
                stock_name="中际旭创",
                persist=False,
                use_cache=False,
                client_factory=lambda k, b, t: fake_client,
                retry_sleep_sec=0.0,
            )
            self.assertEqual(fake_client.completions_api.call_count, 1)
            self.assertEqual(res["execution_meta"]["retry_count"], 0)
            self.assertEqual(res["execution_meta"]["finish_reason"], "stop")
            self.assertFalse(res["execution_meta"]["json_repaired"])

    def test_13_p0_3_b0_momentum_and_car_3class_and_bootstrap(self):
        self.assertEqual(classify_car_3class(2.5), "BULLISH")
        self.assertEqual(classify_car_3class(-2.5), "BEARISH")
        self.assertEqual(classify_car_3class(0.8), "NEUTRAL")

        real_cases = load_real_fin_events_12()
        b0_out_0 = evaluate_single_case_method(METHOD_B0, _make_blind_input(real_cases[0]))
        self.assertEqual(b0_out_0["status"], "SUCCESS")
        self.assertEqual(b0_out_0["inference_mode"], "DETERMINISTIC_BASELINE")
        self.assertEqual(b0_out_0["prompt_tokens"], 0)
        self.assertEqual(b0_out_0["pred_dir"], "BEARISH")

        ci = _bootstrap_ci95([100.0, 0.0, 100.0, 100.0, 0.0, 100.0])
        self.assertEqual(len(ci), 2)
        self.assertLessEqual(ci[0], ci[1])
        self.assertGreater(_compute_macro_f1_pct(["BULLISH", "BEARISH"], ["BULLISH", "BEARISH"]), 99.0)

    def test_14_per_hop_sign_product_equals_total_path_sign(self):
        """断言逐跳有效符号乘积严格等于路径总符号 transmission_sign（含场景 C 两跳传导）。"""
        for query, pol in (
            ("上游磷化铟(InP)晶圆停产检修，Lumentum EML光芯片短缺涨价", -1),
            ("北美云厂商与英伟达Blackwell B200推迟交付", -1),
            ("北美云厂商与英伟达Blackwell B200扩产超预期", +1),
            ("北美云厂商与英伟达Blackwell B200动态跟踪", 0),
        ):
            paths = find_contagion_paths(query, "300308.SZ", event_polarity=pol)
            self.assertTrue(len(paths) >= 1)
            for p in paths:
                hop_eff_prod = math.prod(p["hop_effective_signs"])
                total_sign = int(p["transmission_sign"])
                self.assertEqual(
                    hop_eff_prod,
                    total_sign,
                    f"逐跳有效符号乘积 {p['hop_effective_signs']}={hop_eff_prod} != 总符号 {total_sign}",
                )
                pol_mult = pol if pol != 0 else 1
                self.assertEqual(math.prod(p["hop_edge_signs"]) * pol_mult, total_sign)

    def test_15_recompute_run_summary_metrics_and_na_scenarios(self):
        """验证已有 smoke run 的重算口径：sample_count、scenario_counts、total=0 返回 N/A、traded vs all CAR。"""
        smoke_dir = RUNS_DIR / "run_real12_20261018T140931Z"
        if smoke_dir.exists():
            payload = recompute_run_summary_from_records(smoke_dir)
            self.assertEqual(payload["manifest"]["sample_count"], 2)
            sc_counts = payload["scenario_counts"]
            self.assertEqual(sc_counts["TEMPORAL_REVERSAL"], 1)
            self.assertEqual(sc_counts["PRICED_IN_TRAP"], 1)
            self.assertEqual(sc_counts["SECTOR_CONTAGION"], 0)
            for m, sc_row in payload["by_scenario"].items():
                self.assertEqual(sc_row["SECTOR_CONTAGION"], "N/A")
            for m, st in payload["summary"].items():
                self.assertIn("avg_car_traded_pct", st)
                self.assertIn("avg_car_all_pct", st)
            self.assertEqual(payload["summary"]["B2: Lexical Top-K Retrieval + LLM (Char-Bigram Top-3)"]["f1_pct"], 100.0)
            self.assertEqual(payload["summary"]["Ours: Fin-MemKG (Full: Revision + PricedIn + 2-Hop KG)"]["f1_pct"], 100.0)
            self.assertEqual(payload["summary"]["B1: Long-History Context + LLM (Full-Text)"]["f1_pct"], 50.0)
            self.assertEqual(payload["summary"]["B2+Prior: Lexical Top-K + Supply-Chain Text Prior + LLM (Top-3)"]["f1_pct"], 50.0)


if __name__ == "__main__":
    unittest.main()
