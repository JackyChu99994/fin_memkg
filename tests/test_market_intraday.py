import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from market_intraday import (
    BAR_ENDS, IntradayCoverageError, attach_continuation, daily_approximation,
    detect_minute_signals, load_intraday, normalize, save_cache,
)


def session(day="2024-08-21", closes=None, volumes=None):
    closes = closes or [100, 100, 106, 107, 108, 109, 110, 110]
    volumes = volumes or [10, 10, 60, 10, 10, 10, 10, 10]
    return pd.DataFrame([
        dict(code="300001", timestamp=f"{day} {bar}", open=float(close), high=float(close + 1),
             low=float(close - 1), close=float(close), volume=float(volume))
        for bar, close, volume in zip(BAR_ENDS, closes, volumes)
    ])


class IntradayTests(unittest.TestCase):
    def test_surge_uses_same_day_previous_interval_mean(self):
        yesterday = session("2024-08-20", volumes=[10000] * 8)
        today = session()
        found = detect_minute_signals(pd.concat([yesterday, today]), "2024-08-21")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["type"], "急拉")
        self.assertAlmostEqual(found[0]["volume_ratio"], 6)

    def test_v_recovery_requires_two_rising_bars_and_same_day(self):
        bars = session(closes=[100, 96, 98, 101, 102, 103, 104, 104],
                       volumes=[10, 60, 10, 10, 10, 10, 10, 10])
        found = detect_minute_signals(bars, "2024-08-21")
        self.assertEqual(found[0]["type"], "V型反转")
        self.assertEqual(detect_minute_signals(bars, "2024-08-21 10:30"), [])
        bars.loc[2, ["open", "high", "low", "close"]] = [95, 96, 94, 95]
        self.assertEqual(detect_minute_signals(bars, "2024-08-21"), [])

    def test_no_partial_day_or_future_price_used(self):
        self.assertEqual(detect_minute_signals(session(), "2024-08-21 14:30"), [])
        self.assertEqual(detect_minute_signals(session(), "2024-08-20"), [])

    def test_conflicting_duplicate_rejected(self):
        bars = session()
        duplicate = bars.iloc[[0]].copy()
        duplicate["volume"] = 999
        with self.assertRaisesRegex(ValueError, "conflicting duplicate"):
            normalize(pd.concat([bars, duplicate]))
        self.assertEqual(len(normalize(pd.concat([bars, bars]))), 8)

    def test_invalid_ohlc_units_time_nonfinite_rejected(self):
        for field, value in (("high", 0), ("volume", -1), ("close", float("inf")),
                             ("timestamp", "2024-08-21 12:00"), ("timestamp", "2024-08-21 10:00:05")):
            bars = session()
            bars.loc[0, field] = value
            with self.assertRaises(ValueError):
                normalize(bars)
        self.assertEqual(normalize(session(), volume_unit="lots").iloc[0]["volume"], 1000)

    def test_cache_complete_dates_and_offline_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            save_cache(session(), {"source": "imported", "adjust": "none"}, path)
            with patch("market_intraday.fetch_recent", side_effect=AssertionError("network forbidden")):
                found, report = load_intraday(["300001"], "2024-08-21", ["2024-08-21"], data_dir=path)
                self.assertEqual(len(found), 8)
                self.assertEqual(report["covered_codes"], 1)
                with self.assertRaises(IntradayCoverageError):
                    load_intraday(["300001"], "2024-08-22", ["2024-08-21", "2024-08-22"], data_dir=path)

    def test_missing_interval_not_called_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            save_cache(session().drop(index=4), {"source": "imported", "adjust": "none"}, path)
            with self.assertRaises(IntradayCoverageError):
                load_intraday(["300001"], "2024-08-21", ["2024-08-21"], data_dir=path)

    def test_no_network_after_budget_expires(self):
        with tempfile.TemporaryDirectory() as directory, patch("market_intraday.fetch_recent") as network:
            with self.assertRaises(IntradayCoverageError):
                load_intraday(["300001"], "2024-08-21", ["2024-08-21"],
                              data_dir=Path(directory), allow_network=True, max_wait_seconds=0)
            network.assert_not_called()

    def test_corrupt_imported_cache_falls_back_to_valid_sina(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            imported = path / "imported"
            imported.mkdir()
            (imported / "300001.parquet").write_text("corrupt parquet", encoding="utf-8")
            save_cache(session(), {"source": "sina", "adjust": "none"}, path)
            found, report = load_intraday(["300001"], "2024-08-21", ["2024-08-21"], data_dir=path)
            self.assertEqual(len(found), 8)
            self.assertEqual(report["sources"], {"300001": "sina"})
            self.assertEqual(report["cache_errors"][0]["source"], "imported")

    def test_all_corrupt_caches_raise_coverage_with_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            save_cache(session(), {"source": "imported", "adjust": "none"}, path)
            (path / "imported" / "300001.json").write_text("{broken", encoding="utf-8")
            with self.assertRaises(IntradayCoverageError) as failure:
                load_intraday(["300001"], "2024-08-21", ["2024-08-21"], data_dir=path)
            report = json.loads(str(failure.exception))
            self.assertIn("300001", report["missing"])
            self.assertIn("JSONDecodeError", report["cache_errors"][0]["error"])

    def test_never_cache_adjusted_synthetic_minute(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                save_cache(session(), {"source": "imported", "adjust": "qfq"}, Path(directory))

    def test_next_day_label_does_not_leak_or_skip_suspension(self):
        signal = dict(code="300001", date="2024-08-21", day_low=99)
        prices = pd.DataFrame([dict(code="300001", date="2024-08-22", close=105)])
        calendar = ["2024-08-21", "2024-08-22"]
        self.assertEqual(attach_continuation([signal], prices, "2024-08-21", calendar)[0]["continuation"], "待验证")
        self.assertEqual(attach_continuation([signal], prices, "2024-08-22 10:30", calendar)[0]["continuation"], "待验证")
        self.assertEqual(attach_continuation([signal], prices, "2024-08-22", calendar)[0]["continuation"], "是")
        prices.loc[0, "date"] = "2024-08-23"
        self.assertEqual(attach_continuation([signal], prices, "2024-08-23", calendar + ["2024-08-23"])[0]["continuation"], "待验证")

    def test_daily_proxy_explicit_and_prior_volume_excludes_today(self):
        data = pd.DataFrame([
            dict(code="300001", date=f"2024-08-{day:02}", open=100, high=101, low=99, close=100, volume=10)
            for day in range(16, 21)
        ] + [dict(code="300001", date="2024-08-21", open=100, high=111, low=99, close=110, volume=31)])
        found = daily_approximation(data, "2024-08-21", ["2024-08-21"])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["mode"], "DAILY_OHLC_APPROX")
        self.assertFalse(found[0]["intraday_verified"])
        self.assertAlmostEqual(found[0]["volume_ratio"], 3.1)
        self.assertEqual(daily_approximation(data, "2024-08-20", ["2024-08-21"]), [])
        self.assertEqual(daily_approximation(data, "2024-08-21 10:30", ["2024-08-21"]), [])


if __name__ == "__main__":
    unittest.main()
