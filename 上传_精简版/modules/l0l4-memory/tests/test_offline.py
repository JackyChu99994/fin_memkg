# -*- coding: utf-8 -*-
"""离线回归测试：不依赖 Neo4j / DeepSeek，可在答辩电脑上直接跑。

    python -m unittest discover -s tests -v
"""
import json
import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import demo_data          # noqa: E402
import l3_event_study as l3  # noqa: E402
import l4_archive as l4   # noqa: E402
import viz                # noqa: E402
from agent import MemoryAgent  # noqa: E402
from l1_router import route, universe_block  # noqa: E402
from store import LocalStore  # noqa: E402

TMPDIR = ROOT / ".tmp_tests"
TMPDIR.mkdir(exist_ok=True)


def fresh_store() -> LocalStore:
    return LocalStore(TMPDIR / f"graph_{uuid.uuid4().hex[:8]}.json")


class TestL1(unittest.TestCase):
    def test_lithium_routing(self):
        d = route("碳酸锂期货主力合约涨停，锂矿供给持续收紧，盐湖提锂板块走强。")
        self.assertTrue(d.ok)
        self.assertEqual(d.clusters[0]["id"], "LITHIUM")
        self.assertLessEqual(len(d.stocks), 6)
        self.assertGreater(d.stats["saved_pct"], 0.3)

    def test_named_stock_priority(self):
        d = route("宁德时代与特斯拉签订新合同")
        self.assertEqual(d.stocks[0].name, "宁德时代")
        self.assertEqual(d.named[0].name, "宁德时代")

    def test_irrelevant_news_no_route(self):
        d = route("宁德时代成功注册一枚“宁的易购”商标。")
        # 商标新闻仍会被点名标的路由到，但抽取阶段应被 L0 过滤为空
        self.assertTrue(d.ok)

    def test_universe_block_larger(self):
        self.assertGreater(len(universe_block()), len(route("锂矿涨价").prompt_block))


class TestL4(unittest.TestCase):
    def test_append_and_resolve(self):
        rec = l4.append_event(text="测试新闻：宁德时代扩产。", stock_code="300750",
                              stock_name="宁德时代", publish_date="2026-10-01")
        self.assertTrue(rec["event_id"].startswith("EV-20261001-"))
        self.assertIn("#", rec["ref"])
        again = l4.append_event(text="测试新闻：宁德时代扩产。", stock_code="300750",
                                stock_name="宁德时代", publish_date="2026-10-01")
        self.assertEqual(rec["event_id"], again["event_id"])  # 内容寻址去重
        self.assertEqual(l4.resolve(rec["ref"])["text"], "测试新闻：宁德时代扩产。")


class TestStore(unittest.TestCase):
    def test_upsert_and_invalidate(self):
        st = fresh_store()
        st.upsert_event({"event_id": "E1", "source": "宁德时代", "source_type": "公司",
                         "target": "特斯拉", "target_type": "公司", "relation": "利好事件",
                         "status": "发酵中", "confidence": 0.8, "date": "2026-10-16",
                         "reason": "签约"}, "memory/L4_archive/news.jsonl#E1")
        self.assertEqual(st.stats()["active_bull"], 1)
        hits = st.invalidate(source="宁德时代", target="特斯拉", rel_type="利好事件",
                             by_event="E2", reason="被推翻")
        self.assertEqual(hits, ["E1"])
        self.assertEqual(st.stats()["invalidated"], 1)
        self.assertEqual(st.stats()["active_bull"], 0)

    def test_l0_whitelist(self):
        st = fresh_store()
        with self.assertRaises(ValueError):
            st.upsert_event({"event_id": "X", "source": "A", "target": "B",
                             "relation": "疑似利好", "status": "发酵中"},
                            "ref#X")


class TestScenarios(unittest.TestCase):
    def setUp(self):
        self.store = fresh_store()
        demo_data.seed(self.store, reset=True)
        self.agent = MemoryAgent(self.store, use_llm=False)

    def test_seed_graph(self):
        s = self.store.stats()
        self.assertGreaterEqual(s["edges"], 6)
        self.assertGreaterEqual(s["nodes"], 5)

    def test_scenario_a_reversal(self):
        sc = demo_data.SCENARIOS["A"]
        res = self.agent.run(sc["text"], date=sc["date"], stock_code="300750", with_study=False)
        self.assertEqual(len(res.run.added), 1)
        self.assertGreaterEqual(len(res.run.invalidated), 1)
        inv = [e for e in self.store.edges() if e["status"] == "已被证伪"]
        self.assertTrue(any(e["target_name"].startswith("上海时代宸远") for e in inv))

    def test_scenario_b_direction_flip(self):
        sc = demo_data.SCENARIOS["B"]
        res = self.agent.run(sc["text"], date=sc["date"], stock_code="300750", with_study=False)
        self.assertEqual(res.decision["direction"], "偏空")

    def test_scenario_c_two_hop(self):
        sc = demo_data.SCENARIOS["C"]
        res = self.agent.run(sc["text"], date=sc["date"], stock_code="300750", with_study=False)
        self.assertGreaterEqual(len(res.run.added), 2)
        rels = {a["relation"] for a in res.run.added}
        self.assertEqual(rels, {"利好事件", "利空事件"})
        sg = self.store.subgraph(code="300750", hops=1)
        self.assertTrue(any(n["name"] == "天齐锂业" for n in sg["nodes"]))
        # 两跳路径：天齐锂业 -[供应商]-> 宁德时代 必须存在
        self.assertTrue(any(e["source_name"] == "天齐锂业" and e["target_name"] == "宁德时代"
                            for e in sg["edges"]))

    def test_empty_news_does_nothing(self):
        res = self.agent.run("宁德时代成功注册一枚商标，国际分类为37类建筑修理。",
                             date="2026-10-22", stock_code="300750", with_study=False)
        self.assertEqual(len(res.run.added), 0)


class TestL3(unittest.TestCase):
    def test_synthetic_event_study(self):
        import market_bridge

        orig = l3.load_prices
        orig_dir = market_bridge.DATA_DIR
        market_bridge.DATA_DIR = TMPDIR / "no_snapshot"
        l3.load_prices = lambda code, date, **kw: (l3._synthetic(code, date), "synthetic")
        try:
            r = l3.event_study("300750", "2026-10-21")
        finally:
            l3.load_prices = orig
            market_bridge.DATA_DIR = orig_dir
        self.assertIn("car_pct", r)
        self.assertGreater(r["n_est"], 60)
        self.assertEqual(r["source"], "synthetic")
        self.assertEqual(len(r["table"]), r["n_days"])

    def test_verdict_text(self):
        s = {"car_pct": 3.2}
        self.assertIn("方向一致", l3.verdict(s, "偏多"))
        self.assertIn("方向一致", l3.verdict({"car_pct": -3.2}, "偏空"))


class TestViz(unittest.TestCase):
    def test_mermaid(self):
        st = fresh_store()
        demo_data.seed(st, reset=True)
        code = viz.mermaid_source(st.subgraph(code="300750", hops=1))
        self.assertIn("graph LR", code)
        self.assertIn("宁德时代", code)

    def test_html_without_pyvis(self):
        html = viz.build_network_html({"nodes": [], "edges": []})
        self.assertIn("<div", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
