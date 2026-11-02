from copy import deepcopy
import hashlib
import json
import pytest

from matched_disclosure import METHODS, admit_observations, current_observations, extraction_payload, prepare_prompt


def fixture():
    values = [("CNINFO_1", "2024-01-02", "2024年1月1日召开董事会审议通过回购方案。2024年1月2日首次回购100股。"),
              ("CNINFO_2", "2024-01-04", "2024年1月1日召开董事会审议通过回购方案。公司本次回购方案已实施完毕。"),
              ("CNINFO_3", "2024-01-06", "2024年1月1日召开董事会审议通过回购方案。未来独有秘密信息。")]
    docs = {sid: {"id": sid, "stock_code": "600001", "title": "回购股份公告", "disclosure_date": day,
                  "source_url": "https://example.test/"+sid, "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
            for sid, day, text in values}
    raw = {"original_board_date": "2024-01-01", "identity_quote": "2024年1月1日召开董事会审议通过回购方案",
           "field": "first_purchase_shares", "value": 100, "quote": "首次回购100股"}
    rows, rejected = admit_observations(docs["CNINFO_1"], {"observations": [raw]})
    assert not rejected
    q = {"id": "Q", "stock_code": "600001", "company": "Example", "source_ids": ["CNINFO_1", "CNINFO_2"],
         "as_of": "2024-01-05T00:00:00+08:00", "question": "According to CNINFO_1, what was the first purchase share count?",
         "requested_fields": ["first_purchase_shares"], "reference_draft": {"first_purchase_shares": 100},
         "target_scheme": "600001_BOARD_2024-01-01"}
    return docs, q, raw, rows


def test_reference_poison_cannot_change_any_prepared_method_prompt():
    docs, q, _, rows = fixture()
    poisoned = {**deepcopy(q), "reference_draft": {"first_purchase_shares": 999999}, "target_scheme": "600001_BOARD_1999-01-01", "reference_proofs": [{"quote": "SECRET_LABEL"}]}
    for method in METHODS:
        a = prepare_prompt(q, docs, rows, {s: "ok" for s in docs}, method)
        b = prepare_prompt(poisoned, docs, rows, {s: "ok" for s in docs}, method)
        assert a["status"] == "prepared" and a["user"] == b["user"]
        assert "SECRET_LABEL" not in a["user"]


def test_all_methods_share_named_source_access_and_exclude_future_documents():
    docs, q, _, rows = fixture()
    for method in METHODS:
        result = prepare_prompt(q, docs, rows, {s: "ok" for s in docs}, method)
        assert "CNINFO_1" in result["supplied_source_ids"] and "CNINFO_3" not in result["supplied_source_ids"]
        assert "未来独有秘密信息" not in result["user"]
        assert result["evidence_characters"] <= result["budget_characters"]


def test_incomplete_extraction_blocks_memory_without_relabeling_it_as_rag():
    docs, q, _, rows = fixture()
    result = prepare_prompt(q, docs, rows, {"CNINFO_1": "ok"}, "current_flat")
    assert result["status"] == "memory_build_incomplete" and result["user"] is None
    assert result["extraction_failures"] == ["CNINFO_2"]


def test_same_day_conflicts_and_different_schemes_are_retained():
    _, _, _, rows = fixture()
    first = rows[0]
    conflict = {**first, "observation_id": "conflict", "value": "200"}
    other = {**first, "observation_id": "other", "scheme_candidate": "600001_BOARD_2023-01-01"}
    earlier = {**first, "observation_id": "earlier", "available_at": "2024-01-02T00:00:00+08:00"}
    result = current_observations([first, conflict, other, earlier])
    assert {r["observation_id"] for r in result} == {first["observation_id"], "conflict", "other"}


def test_span_matching_does_not_allow_invented_evidence_or_future_identity():
    docs, _, raw, _ = fixture()
    bad = {**raw, "quote": "公司首次回购999股"}
    assert admit_observations(docs["CNINFO_1"], {"observations": [bad]})[0] == []
    bad = {**raw, "original_board_date": "2025-01-01"}
    assert admit_observations(docs["CNINFO_1"], {"observations": [bad]})[0] == []


def test_full_text_overflow_is_explicit_and_numeric_observations_serialize():
    docs, q, _, rows = fixture()
    assert prepare_prompt(q, docs, rows, {}, "full_text", budget=1)["status"] == "full_text_overflow"
    json.dumps(rows)
    payload = extraction_payload(docs["CNINFO_1"])
    assert set(payload) == {"allowed_fields", "document"} and "reference_draft" not in payload


def test_plan_quantity_and_deadline_do_not_establish_execution():
    docs, _, raw, _ = fixture()
    d = docs["CNINFO_1"]
    d["text"] += "预计回购100股。本次回购期限12个月。"
    d["text_sha256"] = hashlib.sha256(d["text"].encode()).hexdigest()
    rows = [{**raw, "field": "shares", "value": 100, "quote": "预计回购100股"},
            {**raw, "field": "repurchase_stage", "value": "NO_EXECUTION_DISCLOSED", "quote": "本次回购期限12个月"}]
    assert admit_observations(d, {"observations": rows})[0] == []


def test_unique_source_parser_fallback_does_not_accept_ellipsis_as_verbatim():
    docs, _, raw, _ = fixture()
    changed = {**raw, "identity_quote": "2024年1月1日……董事会"}
    # This fixture lacks the parser's quoted proposal syntax: no fallback identity.
    assert admit_observations(docs["CNINFO_1"], {"observations": [changed]})[0] == []
