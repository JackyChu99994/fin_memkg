import hashlib
from scripts.draft_reserved_questions import FAMILIES, reconcile, schedule


def fixture():
    text = "公司于2024年1月1日召开董事会会议，审议通过《关于回购股份方案的议案》。公司实际回购100股。"
    doc = {"id": "S1", "stock_code": "600001", "company": "Example", "title": "回购公告", "text": text,
           "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "disclosure_date": "2024-01-02", "source_url": "https://example.test/1"}
    item = {"stock_code": "600001", "company": "Example", "assigned_families": ["stage"]}
    candidate = {"family": "stage", "availability": "draft", "question": "What execution stage is disclosed?",
        "as_of": "2024-01-03T00:00:00+08:00", "target_board_date": "2024-01-01",
        "identity": {"source_id": "S1", "quote": "2024年1月1日召开董事会会议，审议通过《关于回购股份方案的议案》"},
        "requested_fields": ["repurchase_stage"], "requested_source_ids": [], "answerability": "answerable",
        "reference_answer": {"repurchase_stage": "STARTED"},
        "evidence": [{"source_id": "S1", "quote": "公司实际回购100股", "fields": ["repurchase_stage"]}],
        "missing_reason": "", "qualification_notes": "Source draft pending review"}
    return item, candidate, [doc]


def test_sixty_company_schedule_is_balanced_and_deterministic():
    from collections import Counter
    queue = [{"stock_code": f"{i:06}", "company": "Example"} for i in range(60)]
    result = schedule(queue)
    assert result == schedule(list(reversed(queue)))
    assert Counter(f for r in result for f in r["assigned_families"]) == {f: 30 for f in FAMILIES}


def test_mechanical_pass_does_not_promote_reference_to_human_or_qualified():
    item, candidate, docs = fixture()
    rows, missing = reconcile(item, {"candidates": [candidate]}, docs)
    assert not missing and rows[0]["mechanical_checks"] == "passed_for_review_only"
    assert rows[0]["source_qualification"] == "pending" and not rows[0]["human_reviewed"]
    assert rows[0]["reference_tier"] == "ai_source_anchored_reserved_draft"


def test_paraphrased_quote_is_flagged_instead_of_repaired():
    item, candidate, docs = fixture()
    candidate["evidence"][0]["quote"] = "Already purchased one hundred shares"
    rows, _ = reconcile(item, {"candidates": [candidate]}, docs)
    assert rows[0]["mechanical_checks"] == "flagged" and "quote_not_in_source" in rows[0]["validation_errors"]


def test_future_evidence_cannot_supply_a_reference():
    item, candidate, docs = fixture()
    docs.append({**docs[0], "id": "S2", "disclosure_date": "2024-02-01"})
    candidate["evidence"][0]["source_id"] = "S2"
    rows, _ = reconcile(item, {"candidates": [candidate]}, docs)
    assert "unavailable_evidence_source" in rows[0]["validation_errors"]


def test_unavailable_family_remains_a_shortage():
    item, _, docs = fixture()
    rows, missing = reconcile(item, {"candidates": [{"family": "stage", "availability": "unavailable", "unavailable_reason": "No identity source"}]}, docs)
    assert rows == [] and len(missing) == 1 and missing[0]["reason"] == "No identity source"


def test_insufficient_reference_keeps_the_public_requested_fields():
    item, candidate, docs = fixture()
    item["assigned_families"] = ["insufficient"]
    candidate.update(family="insufficient", requested_fields=["completion_date"], answerability="insufficient", reference_answer={}, missing_reason="Completion not disclosed")
    candidate["evidence"][0]["fields"] = []
    rows, _ = reconcile(item, {"candidates": [candidate]}, docs)
    assert rows[0]["requested_fields"] == ["completion_date"] and rows[0]["reference_draft"] == {}
