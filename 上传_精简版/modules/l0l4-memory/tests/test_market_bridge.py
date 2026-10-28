# -*- coding: utf-8 -*-
"""数据层融合测试：用一份本地 parquet 快照，验证 L3 优先读快照、并正确回退。"""
import json
import sys
import unittest
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import l3_event_study as l3  # noqa: E402
import market_bridge  # noqa: E402

TMP = ROOT / ".tmp_tests"
TMP.mkdir(exist_ok=True)


def build_snapshot(days: int = 320) -> Path:
    d = TMP / f"market_{uuid.uuid4().hex[:8]}"
    d.mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range(end="2026-10-21", periods=days)
    rng = np.random.default_rng(7)
    mkt = rng.normal(0.0003, 0.010, days)
    stock = 100 * np.cumprod(1 + 1.1 * mkt + rng.normal(0, 0.012, days))
    index = 100 * np.cumprod(1 + mkt)

    pd.DataFrame({"code": "300750", "date": dates, "close": stock}).to_parquet(d / "bars.parquet")
    pd.DataFrame({"code": "000300", "date": dates, "close": index}).to_parquet(d / "index.parquet")
    pd.DataFrame({"code": ["300750", "002466"],
                  "industry_l3": ["电池", "锂矿"]}).to_parquet(d / "universe.parquet")
    (d / "meta.json").write_text(json.dumps({"version": "test", "boards": ["创业板"]},
                                            ensure_ascii=False), encoding="utf-8")
    return d


class TestMarketBridge(unittest.TestCase):
    def setUp(self):
        self.dir = build_snapshot()
        self.orig = market_bridge.DATA_DIR
        market_bridge.DATA_DIR = self.dir

    def tearDown(self):
        market_bridge.DATA_DIR = self.orig

    def test_status(self):
        s = market_bridge.status()
        self.assertTrue(s["available"])
        self.assertEqual(s["codes"], 1)
        self.assertEqual(s["rows"], 320)
        self.assertIn("本地快照", market_bridge.describe())

    def test_load_series(self):
        df = market_bridge.load_series("300750")
        self.assertIsNotNone(df)
        self.assertEqual(list(df.columns), ["date", "close"])
        self.assertEqual(len(df), 320)
        self.assertTrue(df["date"].is_monotonic_increasing)

    def test_index_series(self):
        df = market_bridge.load_series("000300")
        self.assertIsNotNone(df)

    def test_industry(self):
        self.assertEqual(market_bridge.industry_of("300750"), "电池")

    def test_missing_code(self):
        self.assertIsNone(market_bridge.load_series("999999"))

    def test_event_study_uses_snapshot(self):
        r = l3.event_study("300750", "2026-10-21")
        self.assertEqual(r["source"], "snapshot")
        self.assertGreater(r["n_est"], 60)
        self.assertLessEqual(r["n_days"], 7)

    def test_pit_truncates_window(self):
        bars = pd.read_parquet(self.dir / "bars.parquet")
        day = bars["date"].sort_values().iloc[-2].strftime("%Y-%m-%d")
        r = l3.event_study("300750", day, as_of=day)
        self.assertTrue(r["truncated"])
        self.assertFalse(r["complete"])
        self.assertLessEqual(r["n_days"], 2)

    def test_pit_blocks_future_data(self):
        bars = pd.read_parquet(self.dir / "bars.parquet")
        day = bars["date"].sort_values().iloc[-3].strftime("%Y-%m-%d")
        later = bars["date"].sort_values().iloc[-1].strftime("%Y-%m-%d")
        with self.assertRaises(ValueError):
            l3.event_study("300750", later, as_of=day)


class TestFallback(unittest.TestCase):
    def setUp(self):
        self.orig = market_bridge.DATA_DIR
        market_bridge.DATA_DIR = TMP / f"empty_{uuid.uuid4().hex[:8]}"

    def tearDown(self):
        market_bridge.DATA_DIR = self.orig

    def test_no_snapshot(self):
        s = market_bridge.status()
        self.assertFalse(s["available"])
        self.assertIsNone(market_bridge.load_series("300750"))
        self.assertIn("AkShare", market_bridge.describe())


if __name__ == "__main__":
    unittest.main(verbosity=2)
