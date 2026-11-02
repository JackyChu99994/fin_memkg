"""Score selected temporal episodes without treating correlated cards as samples."""
from repurchase_evaluation import score_response


def score_episodes(episodes, questions, predictions, documents):
    by_question = {q["id"]: q for q in questions}
    if len(by_question) != len(questions):
        raise ValueError("Duplicate question IDs")
    by_prediction = {}
    for prediction in predictions:
        ident = prediction.get("question_id")
        if ident in by_prediction or ident not in by_question:
            raise ValueError("Duplicate or unknown prediction question ID")
        by_prediction[ident] = prediction
    results = []
    episode_ids = set()
    used_questions = set()
    for episode in episodes:
        if episode["id"] in episode_ids:
            raise ValueError("Duplicate episode ID")
        episode_ids.add(episode["id"])
        ids = [*episode["snapshot_question_ids"], episode["join_question_id"]]
        if len(ids) != 3 or len(set(ids)) != 3 or set(ids) & used_questions:
            raise ValueError("Episodes must have two distinct snapshots and one separate join")
        used_questions.update(ids)
        cards = [by_question[ident] for ident in ids]
        if not cards[0]["as_of"] < cards[1]["as_of"] or len({q["target_scheme"] for q in cards}) != 1:
            raise ValueError("Snapshot order or scheme identity mismatch")
        scores = [score_response(q, by_prediction.get(q["id"]), documents) for q in cards]

        def field_ok(score, key):
            return bool(score["schema_valid"] and score["answered"] and score["scheme_correct"] and score["field_matches"].get(key))

        stage = all(field_ok(s, episode["updated_field"]) for s in scores[:2])
        history = all(field_ok(s, key) for s in scores[:2] for key in episode["stable_fields"])
        snapshots = all(s["exact_answer_correct"] for s in scores[:2])
        join = scores[2]["exact_answer_correct"]
        all_named_sources = all(s["reference_designated_source_coverage"] == 1 for s in scores)
        results.append({"episode_id": episode["id"], "stage_update_correct": stage,
                        "history_retained_correctly": history, "both_snapshots_exact": snapshots,
                        "cross_source_difference_correct": join,
                        "all_designated_sources_cited": all_named_sources,
                        "complete_episode_exact": bool(snapshots and join),
                        "missing_predictions": [ident for ident in ids if ident not in by_prediction],
                        "question_scores": scores})
    metrics = ["stage_update_correct", "history_retained_correctly", "both_snapshots_exact",
               "cross_source_difference_correct", "all_designated_sources_cited", "complete_episode_exact"]
    return {"episodes": len(results), "question_cards": len(used_questions),
            "correct_episode_counts": {key: sum(r[key] for r in results) for key in metrics},
            "per_episode": results, "sampling_unit": "scheme_episode",
            "missing_predictions_count_as_failure": True, "model_calls": 0,
            "citation_semantic_entailment": "not_automatically_judged",
            "general_memory_gain_established": False,
            "limitation": "Selected started-to-completed diagnostics; correlated cards are not independent evaluation samples."}
