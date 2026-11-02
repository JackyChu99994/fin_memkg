"""Evidence preservation and conservative state-update regression tests."""
import json
import sys
import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import l4_archive as l4
from agent import MemoryAgent
from evidence_retrieval import known_by
from pipeline import commit, run_news
from store import LocalStore
from experiments.eval_memory import build_state, evaluate_episode
from test_stage5_evaluation import ScriptedClient, event


def financial(reason, relation="利好事件", **kwargs):
    return {"source": "天齐锂业", "source_code": "002466", "target": "锂电产业链", "target_type": "行业",
        "source_type": "公司", "relation": relation, "reason": reason, "confidence": 0.8,
        "date": "2026-10-25", "status": "发酵中", **kwargs}


class MemoryRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root / "news.jsonl"
        self.store = LocalStore(self.root / "graph.json")
        self.patch = patch.object(l4, "append_event", partial(l4.append_event, path=self.archive))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def write(self, item, news=None):
        return commit(self.store, [item], date=item["date"], stock_code=item.get("source_code", "002466"), news=news or item["reason"])

    def test_revenue_does_not_invalidate_market_share_even_if_model_requests_it(self):
        added, _, _ = self.write(financial("2026年第三季度国内市场份额同比下降", "利空事件"))
        new = financial("2026年第三季度营业收入同比增长", invalidates=[added[0]["event_id"]])
        _, invalidated, _ = self.write(new)
        self.assertEqual(invalidated, [])
        self.assertEqual(self.store.stats()["invalidated"], 0)
        self.assertIn(added[0]["event_id"], new["blocked_invalidates"])

    def test_yoy_and_qoq_coexist(self):
        old, _, _ = self.write(financial("2026年第三季度净利润同比增长"))
        new = financial("2026年第三季度净利润环比下降", "利空事件", invalidates=[old[0]["event_id"]])
        self.assertEqual(self.write(new)[1], [])
        self.assertEqual(self.store.stats()["active_bull"], 1)
        self.assertEqual(self.store.stats()["active_bear"], 1)

    def test_quarter_and_year_to_date_do_not_invalidate_each_other(self):
        old, _, _ = self.write(financial("2026年第三季度净利润同比增长"))
        new = financial("2026年前三季度净利润同比下降", "利空事件", invalidates=[old[0]["event_id"]])
        self.assertEqual(self.write(new)[1], [])

    def test_same_scope_explicit_correction_can_invalidate(self):
        old, _, _ = self.write(financial("2026年第三季度净利润同比增长"))
        new = financial("2026年第三季度净利润同比下降", "利空事件", invalidates=[old[0]["event_id"]])
        invalidated = self.write(new, "更正：2026年第三季度净利润实际同比下降。")[1]
        self.assertEqual(len(invalidated), 1)

    def test_opposite_sign_alone_is_not_a_verified_correction(self):
        self.write(financial("2026年第三季度净利润同比增长"))
        self.assertEqual(self.write(financial("2026年第三季度净利润同比下降", "利空事件"))[1], [])

    def test_distinct_reporting_periods_are_not_merged(self):
        self.write(financial("2026年第三季度净利润同比增长"))
        added, _, reinforced = self.write(financial("2026年前三季度净利润同比增长"))
        self.assertEqual(len(added), 1)
        self.assertEqual(reinforced, [])
        self.assertEqual(len(self.store.edges()), 2)

    def test_proposal_is_not_merged_with_execution(self):
        self.write(financial("董事长提议回购股份", target="股票回购"))
        added, _, reinforced = self.write(financial("公司已执行股份回购", target="股票回购"))
        self.assertEqual(len(added), 1)
        self.assertEqual(reinforced, [])

    def test_unextracted_news_is_still_recallable(self):
        commit(self.store, [], date="2026-10-01", stock_code="300750", news="宁德时代发布股票回购计划。")
        recalled = l4.recall("股票回购", as_of="2026-10-01", stock_code="300750", path=self.archive)
        self.assertEqual(len(self.store.edges()), 0)
        self.assertEqual(len(recalled), 1)
        self.assertIn("回购", recalled[0]["text"])

    def test_archive_recall_excludes_future_sources(self):
        l4.append_event(text="Old report", stock_code="300750", stock_name="", publish_date="2026-10-01")
        l4.append_event(text="Future report", stock_code="300750", stock_name="", publish_date="2026-10-03")
        result = l4.recall("report", as_of="2026-10-02", path=self.archive)
        self.assertEqual([row["text"] for row in result], ["Old report"])

    def test_date_only_evidence_is_not_assumed_known_intraday(self):
        self.assertFalse(known_by("2026-10-01", "2026-10-01T09:00:00+08:00"))
        self.assertTrue(known_by("2026-10-01", "2026-10-01"))
        self.assertFalse(known_by("2026-10-01T02:00:00Z", "2026-10-01T09:00:00+08:00"))

    def test_reinforcement_preserves_original_and_new_references(self):
        first = financial("2026年第三季度净利润同比增长")
        self.write(first, "Report A: 2026年第三季度净利润同比增长")
        self.write(financial("2026年第三季度净利润同比增长"), "Report B: 2026年第三季度净利润同比增长")
        edge = self.store.edges()[0]
        self.assertEqual(len(edge["props"]["evidence_refs"]), 2)
        self.assertEqual(edge["props"]["n_evidence"], 2)

    def test_archive_augmented_answer_has_raw_evidence_after_empty_extraction(self):
        episode = {"id": "e1", "as_of": "2026-10-01T12:00:00+08:00", "query": "Repurchase?",
            "documents": [{"id": "d1", "text": "Repurchase plan", "published_at": "2026-10-01T09:00:00+08:00"}],
            "gold": {"direction": "BULLISH", "evidence_ids": ["d1"]}}
        for method in ("state_memory_archive", "append_memory_archive"):
            client = ScriptedClient([{"events": []}, {"direction": "BULLISH", "evidence_ids": ["d1"], "reason": "Plan"}])
            row = evaluate_episode(episode, method, client)
            self.assertTrue(row["grounded_correct"])
            context = json.loads(row["prompt"])["evidence"]
            self.assertEqual(context["graph"], [])
            self.assertEqual(context["archive_documents"][0]["id"], "d1")

    def test_append_control_does_not_apply_state_invalidation(self):
        docs = [{"id": "d1", "text": "Contract signed", "published_at": "2026-10-01T09:00:00+08:00"},
                {"id": "d2", "text": "Contract cancelled", "published_at": "2026-10-02T09:00:00+08:00"}]
        client = ScriptedClient([{"events": [event()]}, {"events": [event("利空事件")]}])
        edges = build_state(docs, client, self.root / "append", updates=False)
        self.assertEqual(len(edges), 2)
        self.assertTrue(all(edge["status"] == "发酵中" for edge in edges))

    def test_agent_caps_event_study_at_prediction_date(self):
        study = {"car_pct": 99, "n_days": 1, "source": "synthetic", "complete": False}
        with patch("agent.l3.event_study", return_value=study) as calculation:
            result = MemoryAgent(self.store, use_llm=False).run("宁德时代与特斯拉签订新合同。", date="2026-10-22", stock_code="300750")
        self.assertEqual(calculation.call_args.kwargs["as_of"], "2026-10-22")
        self.assertEqual(result.decision["action"], "观察")

    def test_historical_query_cannot_read_a_later_mutable_graph(self):
        self.write(financial("2026年第三季度净利润同比增长"))
        with self.assertRaisesRegex(ValueError, "later facts"):
            run_news("天齐锂业发布公告。", self.store, use_llm=False, date="2026-10-20", stock_code="002466")


if __name__ == "__main__":
    unittest.main()
