"""Draft reference validation must retain source mismatches for adjudication."""
from experiments.draft_expanded_references import validate


def draft():
    return {"scheme_relation": "SAME_SCHEME", "initial_approval_year": 2024,
            "purpose": "SHARE_CANCELLATION", "repurchase_stage": "COMPLETED",
            "cancellation_stage": "INTENDED", "plan_abandoned": False,
            "evidence": [{"field": "repurchase_stage", "document_id": "doc", "quote": "本次回购方案已实施完毕"}]}


def test_source_span_validation_does_not_grant_human_review():
    assert validate(draft(), {"doc": {"text": "本次回购方案已实施完毕。"}}) == []


def test_wrong_number_or_missing_source_is_flagged():
    value = draft()
    value["evidence"][0]["quote"] = "累计回购一百万股"
    assert "unmatched_quote_0" in validate(value, {"doc": {"text": "累计回购二百万股"}})
    value["evidence"][0]["document_id"] = "invented"
    assert "invalid_evidence_source_0" in validate(value, {"doc": {"text": "累计回购二百万股"}})


def test_invalid_state_and_empty_evidence_need_review():
    value = draft()
    value["repurchase_stage"] = "PROFITABLE"
    value["evidence"] = []
    errors = validate(value, {})
    assert "invalid_repurchase_stage" in errors and "empty_evidence_requires_review" in errors
