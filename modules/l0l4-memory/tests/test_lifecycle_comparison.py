"""Lifecycle scoring must distinguish share cancellation from plan abandonment."""
from experiments.eval_memory import evaluate_episode
from test_stage5_evaluation import ScriptedClient


def case():
    return {"id": "lifecycle", "task": "repurchase_lifecycle", "as_of": "2024-05-15T00:00:00+08:00",
            "query": "Report the two stages", "documents": [
                {"id": "notice", "text": "Repurchase completed; shares cancelled", "published_at": "2024-05-15T00:00:00+08:00"},
                {"id": "future", "text": "Future unrelated proposal", "published_at": "2024-06-01T00:00:00+08:00"}],
            "gold": {"repurchase_stage": "COMPLETED", "cancellation_stage": "COMPLETED", "evidence_ids": ["notice"]}}


def test_both_stages_and_raw_evidence_are_required():
    client = ScriptedClient([{"repurchase_stage": "COMPLETED", "cancellation_stage": "COMPLETED", "evidence_ids": ["notice"]}])
    row = evaluate_episode(case(), "tfidf_rag", client)
    assert row["correct"] and row["grounded_correct"]
    assert row["eligible_document_ids"] == ["notice"]
    assert '"id": "future"' not in row["prompt"]


def test_purchase_completion_does_not_imply_share_cancellation():
    client = ScriptedClient([{"repurchase_stage": "COMPLETED", "cancellation_stage": "INTENDED", "evidence_ids": ["notice"]}])
    row = evaluate_episode(case(), "tfidf_rag", client)
    assert row["status"] == "ok" and not row["correct"]


def test_invalid_enum_and_invented_evidence_do_not_pass():
    client = ScriptedClient([{"repurchase_stage": "ABANDONED", "cancellation_stage": "COMPLETED", "evidence_ids": ["notice"]}])
    assert evaluate_episode(case(), "tfidf_rag", client)["status"] == "failed"
    client = ScriptedClient([{"repurchase_stage": "COMPLETED", "cancellation_stage": "COMPLETED", "evidence_ids": ["made_up"]}])
    row = evaluate_episode(case(), "tfidf_rag", client)
    assert row["correct"] and not row["grounded_correct"]
