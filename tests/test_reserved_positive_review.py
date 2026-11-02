import hashlib
import pytest

from scripts.review_reserved_positive_tasks import identity_erratum


def fixture():
    text = "证券代码：600001。分别于2024年1月1日、2024年1月2日召开董事会和股东大会，审议通过回购方案。"
    d = {"id": "A", "stock_code": "600001", "text": text,
         "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "disclosure_date": "2024-01-03"}
    q = {"id": "Q", "stock_code": "600001", "source_ids": ["A"], "as_of": "2024-01-04T00:00:00+08:00",
         "target_scheme": "600001_BOARD_2024-01-02", "identity_proof": {"source_id": "A", "quote": "old"},
         "question": "Which scheme?", "reference_proofs": [], "reference_draft": {"repurchase_stage": "COMPLETED"}}
    fragment = "分别于2024年1月1日、2024年1月2日召开董事会和股东大会，审议通过回购方案"
    return q, d, fragment


def test_identity_erratum_keeps_old_value_and_does_not_change_execution_answer():
    q, d, fragment = fixture()
    ledger = identity_erratum(q, d, "2024-01-01", fragment, "The dates respectively identify board and shareholders")
    assert ledger["old_scheme"] == "600001_BOARD_2024-01-02"
    assert ledger["new_scheme"] == q["target_scheme"] == "600001_BOARD_2024-01-01"
    assert q["reference_draft"] == {"repurchase_stage": "COMPLETED"}
    assert ledger["reference_answer_unchanged"] and not ledger["method_outputs_modified"]


def test_unsupported_identity_date_and_future_source_are_rejected():
    q, d, fragment = fixture()
    with pytest.raises(ValueError, match="Explicit"):
        identity_erratum(q, d, "2023-01-01", fragment, "unsupported")
    d["disclosure_date"] = "2024-01-04"
    with pytest.raises(ValueError, match="eligible"):
        identity_erratum(q, d, "2024-01-01", fragment, "future")


def test_other_issuer_cannot_correct_a_scheme_identity():
    q, d, fragment = fixture()
    d["stock_code"] = "600002"
    with pytest.raises(ValueError, match="issuer"):
        identity_erratum(q, d, "2024-01-01", fragment, "wrong issuer")
