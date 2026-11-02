import hashlib
import pytest
from repurchase_identity import anchor_gate, approval_candidates, own_number, source_span, validate_span


def document(text):
    return {"id": "SOURCE_1", "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}


def test_span_offsets_preserve_original_whitespace_and_hash():
    doc = document("公司\n 2024 年 1 月 2 日 召开会议。")
    span = source_span(doc, r"2024年1月2日召开会议")
    assert "\n" not in span["quote"] and " " in span["quote"]
    assert validate_span(doc, span)
    assert not validate_span({**doc, "text": doc["text"] + "changed"}, span)


def test_missing_proof_is_not_silently_invented():
    with pytest.raises(ValueError):
        source_span(document("尚未执行"), "已经买入")


def test_own_number_uses_header_not_cited_predecessor():
    assert own_number("公告编号：临2024－002。更正原公告2024-001。") == "2024-002"


def test_termination_decision_is_not_initial_scheme_approval():
    doc = document("2024年1月2日召开董事会会议，审议通过《关于终止回购股份的议案》。")
    assert approval_candidates(doc)[0]["kind"] == "termination_decision"


def test_proposal_without_passed_meeting_is_not_approval():
    assert approval_candidates(document("2024年1月2日提议回购，未来拟召开会议审议。")) == []


@pytest.mark.parametrize("title,text,expected", [
    ("关于第二期员工持股计划非交易过户暨回购股份处理完成", "", "share_disposal_not_a_second_repurchase_scheme"),
    ("关于回购方案的核查意见", "", "auxiliary_opinion_use_issuer_disclosure_for_primary_fact"),
    ("关于终止回购的公告", "本次事项需提交公司股东大会审议。", "termination_board_decision_pending_shareholder_gate"),
    ("关于终止回购的公告", "本次事项无需提交公司股东大会审议。", "source_identity_review_required"),
    ("关于回购进展的更正公告", "", "field_scoped_update_not_automatic_stage_change"),
])
def test_gate_preserves_semantic_boundaries(title, text, expected):
    assert anchor_gate(title, text) == expected
