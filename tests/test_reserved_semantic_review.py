import hashlib
import pytest

from repurchase_evaluation import build_public_task
from scripts.extend_reserved_source_review import correction_question, review_record


def documents():
    values = [
        ("ORIGINAL", "2024-01-01", "关于回购股份方案的公告", "公告编号：2024-001。2024年1月1日，公司召开董事会会议，审议通过《关于回购股份方案的议案》。"),
        ("CORRECTION", "2024-01-02", "更正公告", "现更正原2024-001公告。原文数据有误，现予更正。其他内容不变。"),
        ("FUTURE", "2024-01-03", "后续公告", "公司已回购100股。"),
    ]
    return {sid: {"id": sid, "disclosure_date": day, "title": title, "text": text,
                  "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                  "stock_code": "600001", "company": "Example", "source_url": "https://example.test/" + sid}
            for sid, day, title, text in values}


def specification():
    return {"code": "600001", "original": "ORIGINAL", "correction": "CORRECTION",
            "reference_notice": "2024-001", "answer": {"corrected_field": "other", "new_execution_stage_supported": False},
            "fragment": "原文数据有误，现予更正", "tail": "其他内容不变", "scope": "wording_correction",
            "query": "What does {correction} correct in {original}?"}


def test_correction_task_excludes_future_sources_and_keeps_review_blind():
    docs = documents()
    q, review = correction_question(specification(), docs)
    public = build_public_task(q, docs)
    assert q["source_ids"] == ["ORIGINAL", "CORRECTION"]
    assert "reference_draft" not in public and "source_semantics" not in public
    assert "scope_decisions" not in public and "reference_tier" not in public
    assert q["source_qualification"] == "source_checked"
    assert not q["human_reviewed"] and not q["formal_evaluation_ready"]
    assert not review["independent_review"]


def test_correction_must_explicitly_link_original_notice():
    docs = documents()
    docs["CORRECTION"]["text"] = "这是别的公告的更正，原文数据有误，现予更正。其他内容不变。"
    with pytest.raises(ValueError):
        correction_question(specification(), docs)


def test_review_cannot_use_later_source_as_evidence():
    docs = documents()
    q, _ = correction_question(specification(), docs)
    from scripts.extend_reserved_source_review import proof
    later = proof(docs["FUTURE"], "公司已回购100股")
    with pytest.raises(ValueError, match="ineligible"):
        review_record(q, docs, [], "Later source cannot qualify an earlier cutoff", [later])
