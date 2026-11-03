"""Regression checks for fair evidence and repeated-comparison accounting."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.eval_memory import build_state, evaluate_episode, evidence_recall
from experiments.reviewed_comparison import derive_episodes, direction_from_relations, summarize
from test_stage5_evaluation import ScriptedClient, event


class ComparisonTests(unittest.TestCase):
    def test_mixed_reviewed_signs_do_not_become_an_arbitrary_net_direction(self):
        self.assertEqual(direction_from_relations(["利好事件"]), "BULLISH")
        self.assertEqual(direction_from_relations(["利空事件"]), "BEARISH")
        self.assertEqual(direction_from_relations(["利空事件", "利好事件"]), "NEUTRAL")
        with self.assertRaises(ValueError):
            direction_from_relations([])

    def test_derivation_requires_actual_reviewed_parent_labels(self):
        doc = {"id": "d1", "text": "Evidence"}
        label = {"id": "d1", "text_sha256": hashlib.sha256(b"Evidence").hexdigest(),
                 "events": [], "review_status": "ai_labeled", "reviewer": ""}
        with self.assertRaisesRegex(ValueError, "Human review required"):
            derive_episodes([doc], [label])

    def test_syndicated_evidence_can_satisfy_the_same_fact_without_id_bias(self):
        gold = {"evidence_ids": ["first"], "evidence_groups": [["first", "second"]]}
        self.assertEqual(evidence_recall(["second"], gold), 1.0)
        self.assertEqual(evidence_recall(["unrelated"], gold), 0.0)

    def test_original_support_survives_reinforcement(self):
        docs = [{"id": f"d{i}", "text": f"Contract report {i}", "published_at": f"2026-10-0{i}T09:00:00+08:00"} for i in (1, 2)]
        client = ScriptedClient([{"events": [event()]}, {"events": [event()]}])
        with tempfile.TemporaryDirectory() as directory:
            edges = build_state(docs, client, directory)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["evidence_ids"], ["d1", "d2"])

    def test_renewed_relation_does_not_inherit_cancelled_lifecycle_sources(self):
        stories = ["Original contract signed", "Original contract cancelled", "Original contract reinstated"]
        docs = [{"id": f"d{i}", "text": stories[i-1], "published_at": f"2026-10-0{i}T09:00:00+08:00"} for i in (1, 2, 3)]
        client = ScriptedClient([{"events": [event()]}, {"events": [event("利空事件")]}, {"events": [event()]}])
        with tempfile.TemporaryDirectory() as directory:
            edges = build_state(docs, client, directory)
        active = [edge for edge in edges if edge["status"] == "发酵中"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["evidence_ids"], ["d3"])

    def test_final_context_uses_raw_news_ids_and_no_filesystem_paths(self):
        episode = {"id": "e1", "as_of": "2026-10-01T12:00:00+08:00", "query": "Current thesis?",
            "documents": [{"id": "d1", "text": "Contract", "published_at": "2026-10-01T09:00:00+08:00"}],
            "gold": {"direction": "BULLISH", "evidence_ids": ["d1"]}}
        client = ScriptedClient([{"events": [event()]}, {"direction": "BULLISH", "evidence_ids": ["d1"], "reason": "Contract"}])
        row = evaluate_episode(episode, "state_memory", client)
        self.assertTrue(row["grounded_correct"])
        prompt = client.calls[-1]["prompt"]
        self.assertIn('"allowed_evidence_ids": ["d1"]', prompt)
        self.assertNotIn("archive_ref", prompt)
        self.assertNotIn("created_at", prompt)

    def test_repeats_are_not_treated_as_additional_independent_episodes(self):
        records = []
        for repeat in (1, 2, 3):
            for method in ("full_text", "tfidf_rag", "state_memory", "append_memory_archive", "state_memory_archive"):
                for index, direction in enumerate(("BULLISH", "BEARISH")):
                    records.append({"id": f"e{index}", "method": method, "repeat": repeat,
                        "status": "ok", "correct": index == 0, "reference_direction": direction,
                        "prediction": {"direction": "BULLISH"}, "calls": 1,
                        "usage": {"input_tokens": 10, "output_tokens": 5}, "elapsed_seconds": 1,
                        "invented_evidence_ids": [], "required_evidence_recall": 1.0, "grounded_correct": index == 0})
        summary = summarize(records)
        self.assertEqual(summary["unique_episodes"], 2)
        self.assertEqual(summary["methods"]["tfidf_rag"]["predictions"], 6)
        self.assertEqual(summary["methods"]["tfidf_rag"]["majority_total"], 2)
        self.assertEqual(summary["methods"]["tfidf_rag"]["majority_accuracy"], 0.5)
        self.assertEqual(summary["paired_majority"]["state_memory_vs_tfidf_rag"]["exact_mcnemar_p"], 1.0)
        self.assertEqual(summary["paired_majority"]["state_memory_archive_vs_append_memory_archive"]["ties"], 2)


if __name__ == "__main__":
    unittest.main()
