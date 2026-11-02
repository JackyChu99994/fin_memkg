from decimal import Decimal
import json
import pytest
from repurchase_evaluation import normalize_number, score_response, serialize_prompt


def fixture():
    documents = {
        "S1": {"id": "S1", "stock_code": "600001", "title": "Repurchase notice", "disclosure_date": "2024-01-01", "source_url": "https://example.test/1.pdf", "text": "Archived fact."},
        "S2": {"id": "S2", "stock_code": "600001", "title": "Later notice", "disclosure_date": "2024-02-01", "source_url": "https://example.test/2.pdf", "text": "Future fact."},
    }
    question = {"id": "Q1", "stock_code": "600001", "company": "Example", "question": "How many shares?", "as_of": "2024-01-02T00:00:00+08:00",
                "target_scheme": "600001_BOARD_2023-12-01", "source_ids": ["S1"], "reference_draft": {"shares": 1234500},
                "reference_proofs": [{"source_id": "S1", "quote": "SECRET_PROOF"}], "reference_tier": "draft"}
    prediction = {"question_id": "Q1", "status": "answered", "target_scheme": "600001_BOARD_2023-12-01", "answer": {"shares": "123.45万股"}, "evidence_ids": ["S1"]}
    return documents, question, prediction


@pytest.mark.parametrize("value,unit,expected", [
    ("123.45万股", "shares", Decimal("1234500")),
    ("人民币1.809960404亿元", "yuan", Decimal("180996040.40")),
    ("28.40%", "percent", Decimal("28.4")),
    ("1,234,500股", "shares", Decimal("1234500")),
])
def test_exact_unit_equivalence(value, unit, expected):
    assert normalize_number(value, unit) == expected


@pytest.mark.parametrize("value,unit", [(True, "shares"), ("1.5股", "shares"), ("10万元", "shares"), ("12,34元", "yuan"), ("NaN", "yuan"), (float("inf"), "yuan")])
def test_invalid_units_or_nonfinite_values_are_rejected(value, unit):
    with pytest.raises(ValueError):
        normalize_number(value, unit)


def test_equivalent_unit_answer_passes_without_claiming_entailment():
    docs, question, prediction = fixture()
    result = score_response(question, prediction, docs)
    assert result["exact_answer_correct"]
    assert result["citation_semantic_entailment"] == "not_automatically_judged"


def test_wrong_scheme_fails_even_if_values_match():
    docs, question, prediction = fixture()
    prediction["target_scheme"] = "600001_BOARD_2023-11-01"
    result = score_response(question, prediction, docs)
    assert result["fields_correct"] == 1 and not result["exact_answer_correct"]


def test_future_citation_invalidates_otherwise_correct_answer():
    docs, question, prediction = fixture()
    prediction["evidence_ids"] = ["S2"]
    result = score_response(question, prediction, docs)
    assert not result["exact_answer_correct"] and "future_citation:S2" in result["validation_issues"]


def test_zero_is_not_false_for_an_approval_condition():
    docs, question, prediction = fixture()
    question["reference_draft"] = {"shareholder_approval_still_required": False}
    prediction["answer"] = {"shareholder_approval_still_required": 0}
    assert not score_response(question, prediction, docs)["schema_valid"]


def test_percentage_ratio_is_not_percentage_points():
    docs, question, prediction = fixture()
    question["reference_draft"] = {"planned_minimum_completion_percent": "28.40"}
    prediction["answer"] = {"planned_minimum_completion_percent": "0.284"}
    assert not score_response(question, prediction, docs)["exact_answer_correct"]


def test_original_wrong_unit_is_preserved_in_before_after_task():
    docs, question, prediction = fixture()
    question["reference_draft"] = {"before": "1,182,929万股", "after": "1,182,929股"}
    prediction["answer"] = {"before": "1,182,929股", "after": "1,182,929股"}
    result = score_response(question, prediction, docs)
    assert not result["field_matches"]["before"] and result["field_matches"]["after"]


def test_source_column_label_does_not_change_the_quoted_unit_fact():
    docs, question, prediction = fixture()
    question["reference_draft"] = {"before": "1,182,929万股", "after": "1,182,929股"}
    prediction["answer"] = {"before": "累计已回购股数 1,182,929 万股", "after": "累计已回购股数 1,182,929 股"}
    assert score_response(question, prediction, docs)["exact_answer_correct"]


def test_missing_or_extra_facts_do_not_pass_exact_scoring():
    docs, question, prediction = fixture()
    prediction["answer"]["completion_date"] = "2024-01-01"
    assert not score_response(question, prediction, docs)["exact_answer_correct"]


def test_answerable_task_abstention_is_reported_as_unanswered():
    docs, question, prediction = fixture()
    prediction.update(status="insufficient", answer={}, evidence_ids=[], missing_reason="Not found")
    result = score_response(question, prediction, docs)
    assert result["schema_valid"] and not result["answered"] and not result["exact_answer_correct"]


def test_expected_insufficient_task_can_accept_reasoned_abstention():
    docs, question, prediction = fixture()
    question.update(reference_draft={}, reference_answerability="insufficient")
    prediction.update(status="insufficient", answer={}, evidence_ids=[], missing_reason="No purchase source before cutoff")
    assert score_response(question, prediction, docs)["exact_answer_correct"]


def test_public_prompt_has_no_reference_values_proofs_or_future_text():
    docs, question, _ = fixture()
    system, user = serialize_prompt(question, docs)
    body = json.loads(user)
    assert "shares" in body["requested_fields"]
    assert "1234500" not in user and "SECRET_PROOF" not in user and "Future fact" not in user
    assert "reference_draft" not in user and "reference_tier" not in user and "target_scheme" not in body
    assert "untrusted evidence" in system
    assert body["target_scheme_prefix"] == "600001_BOARD_"


def test_compared_source_ids_are_public_but_their_answer_dates_are_not():
    docs, question, _ = fixture()
    question["reference_draft"] = {"source_approval_dates": {"S1": "1998-07-06"}}
    _, user = serialize_prompt(question, docs)
    assert json.loads(user)["requested_source_ids"] == ["S1"]
    assert "1998-07-06" not in user


def test_answerability_does_not_change_public_field_shape_or_leak_label():
    docs, question, _ = fixture()
    _, original = serialize_prompt(question, docs)
    question.update(reference_draft={}, reference_answerability="insufficient", requested_fields=["shares"])
    _, insufficient = serialize_prompt(question, docs)
    assert json.loads(original) == json.loads(insufficient)


def test_insufficient_reference_requires_an_independent_public_field_schema():
    docs, question, _ = fixture()
    question.update(reference_draft={}, reference_answerability="insufficient")
    with pytest.raises(ValueError):
        serialize_prompt(question, docs)


@pytest.mark.parametrize("status", [{"state": "answered"}, ["answered"]])
def test_malformed_status_is_counted_invalid_instead_of_crashing(status):
    docs, question, prediction = fixture()
    prediction["status"] = status
    result = score_response(question, prediction, docs)
    assert not result["exact_answer_correct"] and "invalid_status" in result["validation_issues"]
