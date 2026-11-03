"""Reserved-test references cannot silently inherit development draft status."""
import pytest

from experiments.prepare_expanded_episodes import prepare


def data(split="development", reviewed=False):
    document = {"id": "source", "candidate_id": "company", "stock_code": "000001", "split": split,
                "role": "initial_candidate", "disclosure_date": "2024-04-20", "company": "Company",
                "title": "Repurchase report", "text": "A plan", "text_sha256": "hash", "source_url": "https://example.com/filing"}
    reference = {"id": "source", "text_sha256": "hash", "split": split,
                 "review_status": "reviewed" if reviewed else "ai_draft_pending_user_review",
                 "reviewer": "actual_reviewer" if reviewed else "", "validation_errors": [],
                 "draft": {"scheme_relation": "SAME_SCHEME", "initial_approval_year": 2024,
                           "repurchase_stage": "NO_EXECUTION_DISCLOSED", "cancellation_stage": "INTENDED", "evidence": []}}
    return [document], [reference]


def test_reserved_partition_cannot_use_allow_draft():
    corpus, refs = data("test_reserved")
    with pytest.raises(ValueError, match="reviewed references"):
        prepare(corpus, refs, "test_reserved", allow_draft=True)
    with pytest.raises(ValueError, match="Human review"):
        prepare(corpus, refs, "test_reserved")


def test_draft_development_is_explicit_and_date_only_is_delayed():
    corpus, refs = data()
    episodes, exclusions = prepare(corpus, refs, "development", allow_draft=True)
    assert not exclusions and episodes[0]["review_status"] == "development_ai_draft"
    assert episodes[0]["as_of"] == "2024-04-21T00:00:00+08:00"
    assert "gold" not in episodes[0]["documents"][0]
    assert episodes[0]["event_key"] in episodes[0]["query"]


def test_changed_source_hash_is_rejected_before_preparing_episodes():
    corpus, refs = data(reviewed=True)
    refs[0]["text_sha256"] = "different"
    with pytest.raises(ValueError, match="hash"):
        prepare(corpus, refs, "development")


def test_scheme_and_date_exclusions_remain_auditable():
    corpus, refs = data(reviewed=True)
    refs[0]["draft"]["initial_approval_year"] = 2023
    episodes, exclusions = prepare(corpus, refs, "development")
    assert episodes == [] and exclusions[0]["reason"] == "original_approval_not_confirmed_in_2024"
