"""Factual memory preserves evidence and separates lifecycle dimensions."""
import pytest

from factual_memory import build_factual_state, verified_spans, supports_started
from test_stage5_evaluation import ScriptedClient


def documents():
    return [{"id": "plan", "text": "股份将全部用于注销", "published_at": "2024-04-21T00:00:00+08:00"},
            {"id": "done", "text": "本次回购方案已实施完毕", "published_at": "2024-05-01T00:00:00+08:00"}]


def replies():
    return [{"observations": [{"dimension": "cancellation_stage", "state": "INTENDED", "evidence_quote": "股份将全部用于注销"}]},
            {"observations": [{"dimension": "repurchase_stage", "state": "COMPLETED", "evidence_quote": "本次回购方案已实施完毕"}]}]


def test_later_purchase_completion_preserves_other_dimension():
    result = build_factual_state(documents(), ScriptedClient(replies()), "one plan")
    assert {row["dimension"]: row["state"] for row in result["current"]} == {"repurchase_stage": "COMPLETED", "cancellation_stage": "INTENDED"}
    assert len(result["history"]) == 2
    assert result["current"][0]["evidence_ids"] == ["plan"]


def test_invented_quote_is_rejected_without_fallback():
    reply = {"observations": [{"dimension": "cancellation_stage", "state": "COMPLETED", "evidence_quote": "已完成股份注销"}]}
    with pytest.raises(ValueError, match="quote"):
        build_factual_state(documents()[:1], ScriptedClient([reply]), "one plan")


def test_authorization_does_not_prove_started_but_actual_purchase_does():
    assert not supports_started("董事会审议通过了回购方案并授权实施")
    assert supports_started("公司首次实施回购股份140,700股")
    assert supports_started("2024年4月25日为公司首次回购股份事实发生之日")
    assert supports_started("2024年2月1日，公司首次实施了回购股份")
    assert supports_started("截至2024年6月30日，公司通过回购专用证券账户回购公司股份527,500股")
    assert not supports_started("公司正在办理回购专用账户等准备工作，尚未实施股份回购")


def test_separated_spans_must_all_match_in_source_order():
    assert len(verified_spans("首次回购股份……数量为959,900股", "首次回购股份。公司披露数量为959,900股")) == 2
    with pytest.raises(ValueError, match="quote"):
        verified_spans("数量为959,900股……首次回购股份", "首次回购股份。公司披露数量为959,900股")
    with pytest.raises(ValueError, match="quote"):
        verified_spans("首次回购股份……数量为9,000,000股", "首次回购股份。公司披露数量为959,900股")


def test_account_opening_is_audited_and_not_admitted_as_execution():
    docs = [{"id": "account", "text": "公司已开立回购专用证券账户", "published_at": "2024-04-21T00:00:00+08:00"}]
    client = ScriptedClient([{"observations": [{"dimension": "repurchase_stage", "state": "STARTED", "evidence_quote": docs[0]["text"]}]}])
    result = build_factual_state(docs, client, "one plan")
    assert result["view"] == []
    assert result["rejected_observations"][0]["reason"] == "account_opening_is_not_actual_share_purchase"


def test_append_and_state_share_observations_but_differ_in_latest_view():
    docs = documents() + [{"id": "cancel", "text": "股份注销已经完成", "published_at": "2024-05-15T00:00:00+08:00"}]
    responses = replies() + [{"observations": [{"dimension": "cancellation_stage", "state": "COMPLETED", "evidence_quote": "股份注销已经完成"}]}]
    state = build_factual_state(docs, ScriptedClient(responses), "one plan")
    append = build_factual_state(docs, ScriptedClient(responses), "one plan", updates=False)
    assert state["history"] == append["history"]
    assert len(state["view"]) == 2 and len(append["view"]) == 3
    with pytest.raises(ValueError, match="Chronological"):
        build_factual_state(list(reversed(docs)), ScriptedClient(list(reversed(responses))), "one plan")
