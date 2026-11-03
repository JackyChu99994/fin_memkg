from copy import deepcopy
import hashlib
from benchmark_readiness import FAMILIES, METHODS, check_readiness


def fixture():
    text = "One share was disclosed."
    document = {"id": "S1", "stock_code": "600001", "title": "Notice", "text": text,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "disclosure_date": "2024-01-01", "source_url": "https://example.test/1"}
    base = {"stock_code": "600001", "company": "Example", "split": "test_reserved", "as_of": "2024-01-02T00:00:00+08:00",
            "question": "How many shares?", "source_ids": ["S1"], "reference_draft": {"shares": 1},
            "reference_proofs": [{"source_id": "S1", "start": 0, "end": len(text), "quote": text, "text_sha256": document["text_sha256"]}],
            "source_qualification": "source_checked", "reference_tier": "source_anchored_silver", "human_reviewed": False}
    questions = [{**deepcopy(base), "id": "Q" + str(i), "benchmark_family": family} for i, family in enumerate(sorted(FAMILIES))]
    for question in questions:
        if question["benchmark_family"] == "insufficient":
            question.update(question="What is the planned budget minimum?", requested_fields=["before_min"], reference_draft={},
                            reference_proofs=[], reference_answerability="insufficient", evidence_policy="natural_archive_gap",
                            reference_missing_reason="Only share quantity is disclosed in this fixed archive")
    protocol = {"model": "qwen-plus", "temperature": 0, "methods": sorted(METHODS), "retrieval_parameters": {"top_k": 3},
                "context_budget_policy": "record overflow", "scoring_version": "versioned", "reference_version": "silver-v1",
                "prompt_version": "p1", "source_version": "s1", "memory_build_policy": "shared blind construction", "failure_policy": "preserve failures"}
    return [document], {"600001": "test_reserved"}, questions, protocol


def test_qualified_silver_exploration_does_not_claim_human_gold():
    result = check_readiness(*fixture())
    assert result["exploratory_run_ready"] and not result["declared_independent_human_gold_ready"]


def test_no_questions_is_not_a_frozen_test_set():
    docs, assignments, _, protocol = fixture()
    assert not check_readiness(docs, assignments, [], protocol)["exploratory_run_ready"]


def test_development_company_cannot_enter_reserved_run():
    docs, assignments, questions, protocol = fixture()
    assignments["600001"] = "development"
    assert not check_readiness(docs, assignments, questions, protocol)["exploratory_run_ready"]


def test_future_source_and_bad_quote_prevent_readiness():
    docs, assignments, questions, protocol = fixture()
    docs[0]["disclosure_date"] = "2024-02-01"
    assert not check_readiness(docs, assignments, questions, protocol)["exploratory_run_ready"]


def test_source_qualification_is_not_inferred_from_a_pdf_hash():
    docs, assignments, questions, protocol = fixture()
    questions[0]["source_qualification"] = "pending"
    assert not check_readiness(docs, assignments, questions, protocol)["exploratory_run_ready"]


def test_missing_prompt_or_memory_policy_cannot_count_as_declared_protocol():
    docs, assignments, questions, protocol = fixture()
    del protocol["memory_build_policy"]
    assert not check_readiness(docs, assignments, questions, protocol)["method_protocol_declared"]
