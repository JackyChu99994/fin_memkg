"""The deployed module must use its selected model and never disguise failures."""
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import config
import pipeline
from store import LocalStore


def response(finish="stop"):
    return SimpleNamespace(id="test-response", model="qwen-model-response",
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3),
        choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content='{"events": []}'))])


def test_root_qwen_selection_and_explicit_provider_override():
    with patch.dict(os.environ, {"QWEN_API_KEY": "test-only", "DEEPSEEK_API_KEY": "test-only"}, clear=True):
        assert config.get_llm_config()["provider"] == "qwen"
        assert config.has_llm()
        with patch.dict(os.environ, {"MEMKG_LLM_PROVIDER": "deepseek"}):
            assert config.get_llm_config()["provider"] == "deepseek"


def test_blank_module_template_does_not_mask_root_configuration(tmp_path):
    local = tmp_path / "module.env"
    root = tmp_path / "root.env"
    local.write_text("QWEN_API_KEY=\n", encoding="utf-8")
    root.write_text("QWEN_API_KEY=test-only-root\n", encoding="utf-8")
    with patch.dict(os.environ, {}, clear=True):
        config._load_dotenv(local)
        config._load_dotenv(root)
        assert config.get_llm_config()["api_key"] == "test-only-root"


def test_unknown_provider_and_missing_selected_key_fail_explicitly():
    with patch.dict(os.environ, {"MEMKG_LLM_PROVIDER": "other"}, clear=True):
        with pytest.raises(ValueError):
            config.get_llm_config()
    with patch.dict(os.environ, {"MEMKG_LLM_PROVIDER": "qwen"}, clear=True), patch("openai.OpenAI") as factory:
        with pytest.raises(RuntimeError, match="API key"):
            pipeline.call_llm("source")
        factory.assert_not_called()


def test_selected_qwen_model_and_usage_reach_the_live_pipeline():
    client = Mock()
    client.chat.completions.create.return_value = response()
    with patch.dict(os.environ, {"MEMKG_LLM_PROVIDER": "qwen", "QWEN_API_KEY": "test-only", "QWEN_MODEL": "selected-qwen"}, clear=True), patch("openai.OpenAI", return_value=client) as factory:
        meta = {}
        assert pipeline.call_llm("source", metadata=meta) == '{"events": []}'
        assert client.chat.completions.create.call_args.kwargs["model"] == "selected-qwen"
        assert factory.call_args.kwargs["max_retries"] == 0
        assert meta["provider"] == "qwen" and meta["usage"]["input_tokens"] == 10


def test_api_error_does_not_switch_model_or_commit_rules(tmp_path):
    store = LocalStore(tmp_path / "graph.json")
    with patch.object(pipeline, "call_llm", side_effect=RuntimeError("model 404")), patch.object(pipeline, "heuristic_extract_with_theses") as rules, patch.object(pipeline, "commit") as commit:
        with pytest.raises(RuntimeError, match="no rule result"):
            pipeline.run_news("宁德时代与特斯拉签订新合同", store, date="2026-10-31", use_llm=True)
        rules.assert_not_called()
        commit.assert_not_called()


def test_model_failure_is_one_attempt_without_alias_fallback():
    client = Mock()
    client.chat.completions.create.side_effect = RuntimeError("model 404")
    with patch.dict(os.environ, {"MEMKG_LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "test-only"}, clear=True), patch("openai.OpenAI", return_value=client):
        with pytest.raises(RuntimeError):
            pipeline.call_llm("source")
    assert client.chat.completions.create.call_count == 1


def test_truncated_and_malformed_outputs_are_not_valid_empty_extractions():
    client = Mock()
    client.chat.completions.create.return_value = response("length")
    with pytest.raises(ValueError, match="Incomplete"):
        pipeline._chat(client, "model", "source")
    for raw in ('', '{"answer":"none"}', '{"events":"none"}', '{"events":["bad"]}'):
        with pytest.raises(ValueError):
            pipeline.parse_events(raw)
    assert pipeline.parse_events('{"events":[]}') == []


def test_explicit_rule_demo_still_runs_without_credentials(tmp_path):
    store = LocalStore(tmp_path / "graph.json")
    with patch.object(pipeline, "call_llm") as model, patch.object(pipeline, "commit", return_value=([], [], [])):
        result = pipeline.run_news("宁德时代扩产", store, date="2026-10-31", use_llm=False)
    assert result.mode == "heuristic"
    model.assert_not_called()
