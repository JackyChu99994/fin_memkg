from copy import deepcopy
import hashlib

from repurchase_identity import source_span
from scripts.audit_reserved_references import audit


def example(family="stage", code="300454"):
    text = "公司回购股份方案已实施完毕。累计回购100股。"
    d = {"id": "A", "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
         "title": "回购结果公告", "disclosure_date": "2024-04-11"}
    proof = source_span(d, "累计回购100股")
    q = {"id": "EXAMPLE", "stock_code": code, "benchmark_family": family,
         "source_ids": ["A"], "reference_draft": {"repurchase_stage": "STARTED"},
         "reference_proofs": [{**proof, "fields": ["repurchase_stage"]}],
         "identity_proof": proof, "target_scheme": "EXAMPLE_BOARD_2024-01-01",
         "as_of": "2024-04-12T00:00:00+08:00"}
    return q, d


def test_source_erratum_preserves_input_and_does_not_create_gold():
    q, d = example()
    before = deepcopy(q)
    result, ledger, _ = audit([q], {"A": d})
    assert q == before
    assert result[0]["reference_draft"] == {"repurchase_stage": "COMPLETED"}
    assert ledger[0]["old_answer"] == before["reference_draft"]
    assert not result[0]["formal_evaluation_ready"]
    assert not result[0]["human_reviewed"]
    assert result[0]["source_qualification"] == "pending"


def test_negative_packet_includes_every_eligible_source_without_certifying_absence():
    q, d = example("insufficient", "600001")
    other = {**d, "id": "B", "text": "2023年1月1日，旧方案首次回购100股。"}
    other["text_sha256"] = hashlib.sha256(other["text"].encode()).hexdigest()
    q["source_ids"].append("B")
    q["reference_draft"] = {}
    result, _, packets = audit([q], {"A": d, "B": other})
    assert {s["source_id"] for s in packets[0]["eligible_sources"]} == {"A", "B"}
    assert packets[0]["eligible_sources"][1]["cue_windows"]
    assert not packets[0]["absence_certified"]
    assert "target original scheme only" in result[0]["reference_missing_reason"]
