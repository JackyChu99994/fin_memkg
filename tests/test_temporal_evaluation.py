from copy import deepcopy
import hashlib
import pytest

from scripts.build_reserved_temporal_review import temporal_tasks
from temporal_evaluation import score_episodes


def fixture():
    text1 = "2024年1月1日，公司召开董事会会议，审议通过《关于回购股份方案的议案》。2024年1月2日公司首次回购40股，后续继续实施。"
    text2 = "2024年1月1日，公司召开董事会会议，审议通过《关于回购股份方案的议案》。公司已完成本次股份回购。累计回购100股。"
    docs = {sid: {"id": sid, "stock_code": "600001", "company": "Example", "title": "Issuer disclosure",
                  "disclosure_date": day, "source_url": "https://example.test/" + sid,
                  "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
            for sid, day, text in [("FIRST", "2024-01-03", text1), ("FINAL", "2024-01-04", text2)]}
    from scripts.extend_reserved_source_review import proof
    historical = {"reference_proofs": [proof(docs["FIRST"], "2024年1月2日公司首次回购40股")],
                  "reference_draft": {"first_purchase_date": "2024-01-02"}, "target_scheme": "600001_BOARD_2024-01-01"}
    spec = {"code": "600001", "final_source": "FINAL", "first_shares": 40, "final_shares": 100,
            "completion_clause": "公司已完成本次股份回购"}
    questions, _, episode = temporal_tasks(spec, historical, docs)
    predictions = [{"question_id": q["id"], "status": "answered", "target_scheme": q["target_scheme"],
                    "answer": deepcopy(q["reference_draft"]), "evidence_ids": q["source_ids"], "missing_reason": ""}
                   for q in questions]
    return docs, questions, [episode], predictions


def test_earlier_snapshot_cannot_include_final_source():
    docs, questions, episodes, predictions = fixture()
    assert questions[0]["source_ids"] == ["FIRST"]
    assert questions[1]["source_ids"] == ["FIRST", "FINAL"]
    result = score_episodes(episodes, questions, predictions, docs)
    assert result["episodes"] == 1 and result["question_cards"] == 3
    assert result["correct_episode_counts"]["complete_episode_exact"] == 1
    assert not result["general_memory_gain_established"]


def test_stale_state_and_lost_history_are_distinct_failures():
    docs, questions, episodes, predictions = fixture()
    predictions[1]["answer"]["repurchase_stage"] = "STARTED"
    report = score_episodes(episodes, questions, predictions, docs)
    assert report["correct_episode_counts"]["stage_update_correct"] == 0
    assert report["correct_episode_counts"]["history_retained_correctly"] == 1
    predictions[1]["answer"]["repurchase_stage"] = "COMPLETED"
    predictions[1]["answer"]["first_purchase_shares"] = 100
    report = score_episodes(episodes, questions, predictions, docs)
    assert report["correct_episode_counts"]["stage_update_correct"] == 1
    assert report["correct_episode_counts"]["history_retained_correctly"] == 0


def test_missing_prediction_counts_as_failure_and_duplicate_is_rejected():
    docs, questions, episodes, predictions = fixture()
    report = score_episodes(episodes, questions, predictions[:2], docs)
    assert report["correct_episode_counts"]["complete_episode_exact"] == 0
    assert report["per_episode"][0]["missing_predictions"] == [questions[2]["id"]]
    with pytest.raises(ValueError, match="Duplicate"):
        score_episodes(episodes, questions, predictions + predictions[:1], docs)


def test_endpoint_scheme_mismatch_is_rejected():
    docs, questions, episodes, predictions = fixture()
    questions[1]["target_scheme"] = "600001_BOARD_2023-01-01"
    with pytest.raises(ValueError, match="identity"):
        score_episodes(episodes, questions, predictions, docs)
