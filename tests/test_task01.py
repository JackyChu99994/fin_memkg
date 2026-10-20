import unittest
from unittest.mock import patch

import pandas as pd

from scripts.validate_task01 import rebound_signals, rsi, run


class Task01Indicators(unittest.TestCase):
    def test_rsi_monotonic_and_flat_edges(self):
        self.assertEqual(rsi(pd.Series(range(40))).iloc[-1], 100)
        self.assertEqual(rsi(pd.Series(range(40, 0, -1))).iloc[-1], 0)
        self.assertEqual(rsi(pd.Series([10.0] * 40)).iloc[-1], 50)
        self.assertTrue(rsi(pd.Series(range(10))).isna().all())

    def test_rsi_wilder_known_reference(self):
        close = pd.Series([44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10,
                           45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28])
        self.assertAlmostEqual(rsi(close).iloc[-1], 70.464135, places=5)

    def test_one_rebound_per_oversold_cycle(self):
        values = pd.Series([29, 40, 51, 49, 52, 28, 45, 27, 50, 51, 55])
        self.assertEqual(rebound_signals(values)[lambda x: x].index.tolist(), [2, 9])

    def test_initial_strength_is_not_oversold_rebound(self):
        self.assertFalse(rebound_signals(pd.Series([49, 51, 60, 50, 51])).any())

    def test_missing_eligible_stock_is_explicit_in_acceptance(self):
        universe = pd.DataFrame({"code": ["300001", "300002"]})
        bars = pd.DataFrame({"code": ["300001"], "date": ["2026-03-31"],
                             "close": [10.0], "volume": [100.0]})
        with patch("scripts.validate_task01.ms.load_universe", return_value=universe), \
                patch("scripts.validate_task01.ms.load_bars", return_value=bars):
            result = run()
        self.assertFalse(result["coverage_complete"])
        self.assertEqual(result["missing_codes"], ["300002"])


if __name__ == "__main__":
    unittest.main()
