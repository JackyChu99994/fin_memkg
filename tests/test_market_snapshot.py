"""Isolated regression tests; never read or modify the real market dataset."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal

import market_snapshot as ms


def bars(code="300001", dates=("2024-01-02", "2024-01-03"), close=10.0):
    return pd.DataFrame([
        {"code": code, "date": day, "open": close, "high": close+1,
         "low": close-1, "close": close, "volume": 100, "amount": 1000,
         "turnover_pct": 1.0} for day in dates])


def universe(codes=("300001",)):
    return pd.DataFrame([
        {"code": code, "name": code, "list_date": "2020-01-01", "board": "创业板",
         "float_shares": 10000, "total_shares": 20000, "industry": "制造业"}
        for code in codes])


def index_frame(dates=("2024-01-02", "2024-01-03")):
    return pd.DataFrame({"date": list(dates), "close": [100.0]*len(dates), "symbol": "sz399006"})


def inline(function, *args, timeout=5.0, **kwargs):
    return function(*args, **kwargs)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.assertTrue(self.root.resolve().is_relative_to(Path(__file__).resolve().parent))
        self.tmp.cleanup()

    def seed(self):
        (self.root / "parts").mkdir(exist_ok=True)
        bars().to_parquet(self.root / "bars.parquet", index=False)
        bars().to_parquet(self.root / "parts" / "300001.parquet", index=False)
        universe().to_parquet(self.root / "universe.parquet", index=False)
        index_frame().to_parquet(self.root / "index.parquet", index=False)
        ms._atomic_json(self.root / "meta.json", {
            "board": "创业板", "start": "2024-01-01", "end": "2024-01-03",
            "requested_codes": 1, "downloaded_codes": 1, "failed_codes": 0})

    def build(self, **kwargs):
        return ms.build_snapshot(start="2024-01-01", end="2024-01-03",
                                 out_dir=self.root, **kwargs)

    def test_historical_universe_codes_and_interval(self):
        self.seed()
        stocks = universe(("300001", "300002"))
        stocks.loc[1, "list_date"] = "2024-01-04"
        stocks.to_parquet(self.root / "universe.parquet", index=False)
        pd.concat([bars(), bars("300002")]).to_parquet(self.root / "bars.parquet", index=False)
        result = ms.load_bars("2024-01-03", ["sz300001", "300002.SZ"],
                              data_dir=self.root, start_date="2024-01-03")
        self.assertEqual(result["code"].tolist(), ["300001"])
        self.assertEqual(result["date"].tolist(), ["2024-01-03"])
        self.assertEqual(ms.load_universe("2024-01-03", data_dir=self.root)["code"].tolist(), ["300001"])
        self.assertTrue(ms.load_bars("2024-01-03", [], self.root).empty)
        self.assertTrue(ms.load_universe("2024-01-03", [], self.root).empty)

    def test_rows_before_listing_are_excluded(self):
        self.seed()
        stocks = universe()
        stocks["list_date"] = "2024-01-03"
        stocks.to_parquet(self.root / "universe.parquet", index=False)
        self.assertEqual(ms.load_bars("2024-01-03", data_dir=self.root)["date"].tolist(), ["2024-01-03"])

    def test_invalid_dates_and_windows_fail_fast(self):
        for day in ("2024-1-02", "2024-02-30", "2024-01-03T12:00:00"):
            with self.assertRaises(ValueError):
                ms.load_bars(day, data_dir=self.root)
        with self.assertRaises(ValueError):
            ms.load_panel("2024-01-03", lookback=0, data_dir=self.root)
        with self.assertRaises(ValueError):
            ms.load_index("2024-01-03", lookback=-1, data_dir=self.root)
        with self.assertRaises(ValueError):
            ms.load_bars("2024-01-03", data_dir=self.root, start_date="2024-01-04")

    def test_panel_and_index_are_time_filtered(self):
        self.seed()
        panel = ms.load_panel("2024-01-02", lookback=1, data_dir=self.root)
        self.assertEqual(panel.index.tolist(), ["2024-01-02"])
        self.assertEqual(ms.load_index("2024-01-02", 1, self.root)["date"].tolist(), ["2024-01-02"])

    def test_legacy_resume_adopts_coverage_without_network_or_foreign_parts(self):
        self.seed()
        bars("300999").to_parquet(self.root / "parts" / "300999.parquet", index=False)
        with patch.object(ms, "bounded_call", side_effect=AssertionError("unexpected network")):
            meta = self.build()
        self.assertTrue(meta["published"])
        self.assertEqual(meta["resumed_codes"], 1)
        self.assertEqual(meta["pending_this_run"], 0)
        self.assertEqual(ms.load_bars("2024-01-03", data_dir=self.root)["code"].unique().tolist(), ["300001"])
        self.assertTrue(ms._json(self.root / "parts" / "300001.json")["legacy_adopted"])

    def test_range_extension_redownloads_union_without_mixed_qfq(self):
        self.seed()
        fresh = bars(dates=("2023-12-29", "2024-01-02", "2024-01-03"), close=20)
        with patch.object(ms, "bounded_call", side_effect=inline), \
                patch.object(ms, "_fetch_one", return_value=fresh) as fetch, \
                patch.object(ms, "fetch_index", return_value=index_frame(("2023-12-29", "2024-01-02", "2024-01-03"))):
            ms.build_snapshot("2023-12-29", "2024-01-03", out_dir=self.root)
        fetch.assert_called_once_with("300001", "2023-12-29", "2024-01-03", retries=1)
        result = ms.load_bars("2024-01-03", data_dir=self.root)
        self.assertEqual(result["close"].tolist(), [20, 20, 20])
        self.assertEqual(result["date"].min(), "2023-12-29")

    def test_partial_selection_does_not_poison_later_full_universe(self):
        stocks = universe(("300001", "300002"))
        with patch.object(ms, "bounded_call", side_effect=inline), \
                patch.object(ms, "fetch_universe", return_value=stocks) as fetch_universe, \
                patch.object(ms, "_fetch_one", side_effect=lambda code, *a, **k: bars(code)), \
                patch.object(ms, "fetch_index", return_value=index_frame()):
            limited = self.build(limit=1)
            self.assertFalse(limited["universe_complete"])
            full = self.build()
        self.assertEqual(fetch_universe.call_count, 2)
        self.assertEqual(full["requested_codes"], 2)
        self.assertEqual(ms.load_universe(data_dir=self.root)["code"].tolist(), ["300001", "300002"])

    def test_future_listings_excluded_during_build(self):
        stocks = universe(("300001", "300002"))
        stocks.loc[1, "list_date"] = "2024-01-04"
        with patch.object(ms, "bounded_call", side_effect=inline), \
                patch.object(ms, "fetch_universe", return_value=stocks), \
                patch.object(ms, "_fetch_one", side_effect=lambda code, *a, **k: bars(code)) as fetch, \
                patch.object(ms, "fetch_index", return_value=index_frame()):
            meta = self.build()
        self.assertEqual(meta["requested_codes"], 1)
        fetch.assert_called_once()

    def test_failed_symbol_retains_active_snapshot_and_records_failure(self):
        self.seed()
        before = ms.load_bars("2024-01-03", data_dir=self.root)
        with patch.object(ms, "bounded_call", side_effect=inline), \
                patch.object(ms, "fetch_universe", return_value=universe()), \
                patch.object(ms, "_fetch_one", side_effect=TimeoutError("source unavailable")):
            with self.assertRaises(RuntimeError):
                self.build(resume=False)
        assert_frame_equal(ms.load_bars("2024-01-03", data_dir=self.root), before)
        attempt = ms._json(self.root / "last_attempt.json")
        self.assertFalse(attempt["published"])
        self.assertEqual(attempt["failed_codes"], 1)
        self.assertIn("source unavailable", attempt["failures"][0]["error"])

    def test_failed_index_retains_entire_active_generation(self):
        self.seed()
        self.build()
        manifest = (self.root / "CURRENT.json").read_text()
        with patch.object(ms, "bounded_call", side_effect=inline), \
                patch.object(ms, "fetch_universe", return_value=universe()), \
                patch.object(ms, "_fetch_one", return_value=bars(close=25)), \
                patch.object(ms, "fetch_index", side_effect=TimeoutError("index unavailable")):
            with self.assertRaises(RuntimeError):
                self.build(resume=False)
        self.assertEqual((self.root / "CURRENT.json").read_text(), manifest)
        self.assertEqual(ms.load_bars("2024-01-03", data_dir=self.root)["close"].tolist(), [10, 10])

    def test_publication_write_failure_cannot_expose_mixed_generation(self):
        self.seed()
        self.build()
        manifest = (self.root / "CURRENT.json").read_text()
        original = pd.DataFrame.to_parquet

        def fail_index(frame, path, *args, **kwargs):
            if Path(path).name == "index.parquet":
                raise OSError("simulated disk full")
            return original(frame, path, *args, **kwargs)

        with patch.object(pd.DataFrame, "to_parquet", fail_index):
            with self.assertRaises(OSError):
                ms.publish_snapshot(bars(close=30), universe(), index_frame(), {}, self.root)
        self.assertEqual((self.root / "CURRENT.json").read_text(), manifest)
        self.assertEqual(ms.load_bars("2024-01-03", data_dir=self.root)["close"].tolist(), [10, 10])

    def test_unsupported_boards_fail_before_network(self):
        for board in ("主板", "科创板", ""):
            with self.assertRaises(ValueError):
                ms.fetch_universe(board)
            with self.assertRaises(ValueError):
                self.build(board=board)

    def test_optional_query_is_offline_and_reports_insufficient_coverage(self):
        self.seed()
        with patch.object(ms, "bounded_call", side_effect=AssertionError("network forbidden")):
            result = ms.get_bars(["300001"], "2024-01-04", "2024-01-01", self.root)
        self.assertFalse(result.attrs["coverage"][0]["complete"])
        self.assertEqual(len(result), 2)

    def test_optional_query_fetches_only_missing_and_reuses_query_cache(self):
        self.seed()
        with patch.object(ms, "bounded_call", return_value=bars(
                dates=("2024-01-02", "2024-01-03", "2024-01-04"), close=20)) as fetch:
            first = ms.get_bars(["300001"], "2024-01-04", "2024-01-01", self.root, allow_fetch=True)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(first["close"].tolist(), [20, 20, 20])
        self.assertTrue(first.attrs["coverage"][0]["complete"])
        with patch.object(ms, "bounded_call", side_effect=AssertionError("cache should satisfy request")):
            second = ms.get_bars(["300001"], "2024-01-04", "2024-01-01", self.root, allow_fetch=True)
        assert_frame_equal(first, second)
        self.assertEqual(second.attrs["coverage"][0]["source"], "query_cache")

    def test_query_rejects_not_yet_listed_stock(self):
        self.seed()
        with self.assertRaisesRegex(ValueError, "unknown or not-yet-listed"):
            ms.get_bars(["300002"], "2024-01-03", "2024-01-01", self.root)

    def test_query_can_fetch_when_only_universe_exists(self):
        universe().to_parquet(self.root / "universe.parquet", index=False)
        with patch.object(ms, "bounded_call", return_value=bars()) as fetch:
            result = ms.get_bars(["300001"], "2024-01-03", "2024-01-01",
                                 self.root, allow_fetch=True)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(len(result), 2)
        self.assertTrue(result.attrs["coverage"][0]["complete"])

    def test_invalid_numeric_source_is_never_published(self):
        corrupt = bars()
        corrupt["close"] = "not-a-number"
        with patch.object(ms, "bounded_call", side_effect=inline), \
                patch.object(ms, "fetch_universe", return_value=universe()), \
                patch.object(ms, "_fetch_one", return_value=corrupt):
            with self.assertRaises(RuntimeError):
                self.build()
        self.assertFalse((self.root / "CURRENT.json").exists())
        self.assertEqual(ms._json(self.root / "last_attempt.json")["failed_codes"], 1)

    def test_subprocess_timeout_is_real_and_terminates_work(self):
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            ms.bounded_call(time.sleep, 10, timeout=0.1)
        self.assertLess(time.monotonic()-started, 4)
        self.assertEqual(ms.bounded_call(abs, -3, timeout=10), 3)


if __name__ == "__main__":
    unittest.main()
