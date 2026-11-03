"""Tests for measurement errors that would invalidate the stage-five experiments."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.common import counts, event_sets, extraction_summary, prf, retrieve, reviewed_labels, strict_events
from experiments.eval_extraction import evaluate, extraction_prompt
from experiments.eval_memory import build_state, eligible_documents, evaluate_episode


def event(relation="利好事件"):
    return {"source": "宁德时代", "target": "特斯拉", "source_type": "公司", "target_type": "公司",
            "relation": relation, "status": "发酵中", "reason": "Supported by the document", "confidence": 0.8}


class ScriptedClient:
    def __init__(self, replies):
        self.replies, self.calls = iter(replies), []

    def chat(self, system, prompt):
        self.calls.append({"usage": {"input_tokens": 10, "output_tokens": 5}, "prompt": prompt})
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return json.dumps(reply, ensure_ascii=False)


class MeasurementTests(unittest.TestCase):
    def test_missing_events_is_a_parse_failure_not_an_empty_prediction(self):
        with self.assertRaises(ValueError):
            strict_events('{"answer": "none"}')
        with self.assertRaises(ValueError):
            strict_events('{"events": ["bad"]}')

    def test_snapshot_pointer_precedes_stale_legacy_files(self):
        import market_bridge
        import pandas as pd
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generation = root / "snapshots" / "new"
            generation.mkdir(parents=True)
            for path, close in ((root, 1.0), (generation, 2.0)):
                pd.DataFrame({"code": ["300750"], "date": ["2026-10-01"], "close": [close]}).to_parquet(path / "bars.parquet")
            (root / "CURRENT.json").write_text('{"generation":"snapshots/new"}', encoding="utf-8")
            self.assertEqual(market_bridge.load_series("300750", data_dir=root).iloc[0]["close"], 2.0)

    def test_snapshot_pointer_cannot_escape_market_directory(self):
        import market_bridge
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CURRENT.json").write_text('{"generation":"../escape"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                market_bridge.load_series("300750", data_dir=root)

    def test_wrong_relation_counts_both_false_positive_and_false_negative(self):
        actual = event_sets([event("利空事件")])["relations"]
        expected = event_sets([event()])["relations"]
        self.assertEqual(counts(actual, expected), {"tp": 0, "fp": 1, "fn": 1})

    def test_relation_direction_is_not_interchangeable(self):
        reverse = {**event(), "source": "特斯拉", "target": "宁德时代"}
        self.assertEqual(counts(event_sets([reverse])["relations"], event_sets([event()])["relations"])["tp"], 0)

    def test_empty_denominators_are_undefined_not_perfect_scores(self):
        self.assertIsNone(prf(0, 0, 0)["f1"])

    def test_label_review_and_text_binding_are_required(self):
        doc = {"id": "d1", "text": "Evidence"}
        label = {"id": "d1", "text_sha256": hashlib.sha256(b"Evidence").hexdigest(), "events": [], "review_status": "unreviewed"}
        with self.assertRaises(ValueError):
            reviewed_labels([doc], [label])
        label.update(review_status="reviewed", reviewer="human-A")
        self.assertIn("d1", reviewed_labels([doc], [label]))
        with self.assertRaises(ValueError):
            reviewed_labels([{**doc, "text": "Changed evidence"}], [label])

    def test_api_failure_counts_as_miss_without_rule_fallback(self):
        doc = {"id": "d1", "text": "宁德时代与特斯拉签订合同", "published_at": "2026-10-01"}
        records = evaluate([doc], {"d1": {"events": [event()]}}, "plain", ScriptedClient([TimeoutError()]))
        summary = extraction_summary(records)
        self.assertEqual(summary["failures"], 1)
        self.assertEqual(summary["micro"]["relations"]["fn"], 1)
        self.assertEqual(summary["exact_document_accuracy"], 0)

    def test_extra_invalid_relation_is_visible_in_raw_precision(self):
        doc = {"id": "d1", "text": "News", "published_at": "2026-10-01"}
        records = evaluate([doc], {"d1": {"events": []}}, "plain", ScriptedClient([{"events": [{**event(), "relation": "invented"}]}]))
        self.assertEqual(records[0]["raw_relation_counts"]["fp"], 1)
        self.assertEqual(len(records[0]["rejected"]), 1)

    def test_gold_fields_never_enter_prompt(self):
        doc = {"id": "d1", "text": "News", "published_at": "2026-10-01", "gold": "SECRET_LABEL"}
        self.assertNotIn("SECRET_LABEL", extraction_prompt(doc, "plain"))

    def test_sparse_retrieval_is_deterministic_and_handles_empty_history(self):
        docs = [{"id": "b", "text": "Lithium price"}, {"id": "a", "text": "Battery contract"}]
        self.assertEqual(retrieve("Battery contract", docs, 1)[0]["id"], "a")
        self.assertEqual(retrieve("News", [], 3), [])

    def test_future_documents_excluded_before_retrieval(self):
        episode = {"as_of": "2026-10-01T12:00:00+08:00", "documents": [
            {"id": "future", "text": "Answer", "published_at": "2026-10-01T13:00:00+08:00"},
            {"id": "past", "text": "Evidence", "published_at": "2026-10-01T11:00:00+08:00"}]}
        self.assertEqual([doc["id"] for doc in eligible_documents(episode)], ["past"])

    def test_state_memory_is_isolated_and_explicitly_records_reversal(self):
        docs = [{"id": "d1", "text": "Contract signed", "published_at": "2026-10-01T09:00:00+08:00"},
                {"id": "d2", "text": "Contract cancelled", "published_at": "2026-10-02T09:00:00+08:00"}]
        import l4_archive as l4
        default = l4.NEWS_JSONL
        before = default.read_bytes() if default.exists() else None
        client = ScriptedClient([{"events": [event()]}, {"events": [event("利空事件")]}])
        with tempfile.TemporaryDirectory() as directory:
            edges = build_state(docs, client, directory)
            self.assertEqual(len(edges), 2)
            self.assertEqual(sum(edge["status"] == "已被证伪" for edge in edges), 1)
            self.assertTrue((Path(directory) / "news.jsonl").exists())
        self.assertEqual(default.read_bytes() if default.exists() else None, before)

    def test_memory_build_tokens_are_included_and_citations_resolve(self):
        episode = {"id": "e1", "as_of": "2026-10-01T12:00:00+08:00", "query": "Current thesis?",
            "documents": [{"id": "d1", "text": "Contract", "published_at": "2026-10-01T09:00:00+08:00"}],
            "gold": {"direction": "BULLISH", "evidence_ids": ["d1"]}}
        client = ScriptedClient([{"events": [event()]}, {"direction": "BULLISH", "evidence_ids": ["d1"], "reason": "Contract"}])
        row = evaluate_episode(episode, "state_memory", client)
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["usage"]["input_tokens"], 20)
        self.assertIn('"evidence_ids": ["d1"]', client.calls[-1]["prompt"])


if __name__ == "__main__":
    unittest.main()
