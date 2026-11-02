import hashlib
import pytest

from scripts.finalize_reserved_absence_review import checked_inventory, checked_quote


def test_explicit_punctuation_repair_keeps_a_source_bound_span_and_old_quote():
    text = "公司在回购期限内根据市场情况择机做出回购决策并予以实施。"
    sid = "CNINFO_1218578369"
    d = {"id": sid, "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
    original = text[:-1] + "."
    span, repair = checked_quote({"source_id": sid, "quote": original}, {sid: d})
    assert span["quote"] == text
    assert repair["original_model_quote"] == original and repair["raw_response_unchanged"]


def test_unreviewed_similar_quote_cannot_be_silently_repaired():
    d = {"id": "A", "text": "未来可能回购。", "text_sha256": hashlib.sha256("未来可能回购。".encode()).hexdigest()}
    with pytest.raises(ValueError, match="Unreviewed"):
        checked_quote({"source_id": "A", "quote": "未来将会回购。"}, {"A": d})


def test_scope_inventory_rejects_contradictory_ids_and_unresolved_roles():
    with pytest.raises(ValueError, match="Contradictory"):
        checked_inventory({"sources": {"A": {"source_id": "B", "role": "target_scheme"}}}, ["A"])
    with pytest.raises(ValueError, match="Unclear"):
        checked_inventory({"sources": [{"source_id": "A", "role": "unclear"}]}, ["A"])
