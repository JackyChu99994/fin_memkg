import os
from pathlib import Path

import pandas as pd
import pytest

from stage3_data_ui import _csv, _daily, file_signature, filter_industries, select_daily_window


def test_daily_ui_window_filters_future_and_keeps_inclusive_start():
    bars = pd.DataFrame({"date": ["2026-03-31", "2026-04-01", "2026-03-30", "2026-03-27"],
                         "close": [10, 99, 9, 8]})
    result = select_daily_window(bars, "2026-03-31", start="2026-03-30")
    assert result["date"].tolist() == ["2026-03-30", "2026-03-31"]
    assert 99 not in result["close"].tolist()
    assert select_daily_window(bars, "2026-03-31", lookback=2).equals(result)


def test_daily_ui_window_rejects_reversed_dates_and_zero_window():
    bars = pd.DataFrame({"date": ["2026-03-31"]})
    with pytest.raises(ValueError):
        select_daily_window(bars, "2026-03-31", start="2026-04-01")
    with pytest.raises(ValueError):
        select_daily_window(bars, "2026-03-31", lookback=0)


def test_signature_changes_with_mtime_and_generation_even_at_same_size(tmp_path):
    first = tmp_path / "generation1" / "bars.parquet"
    second = tmp_path / "generation2" / "bars.parquet"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"data")
    second.write_bytes(b"data")
    signature = file_signature([first])
    os.utime(first, ns=(first.stat().st_atime_ns, first.stat().st_mtime_ns + 1_000_000))
    assert file_signature([first]) != signature
    assert file_signature([first]) != file_signature([second])
    assert file_signature([tmp_path / "missing"])[0][1:] == (None, None)


def test_daily_ui_cache_does_not_reload_on_date_range_change(monkeypatch):
    calls = []

    def local_loader(as_of, codes=None, data_dir=None):
        calls.append((as_of, codes, data_dir))
        return pd.DataFrame({"date": ["2026-03-30", "2026-03-31"], "close": [9, 10]})

    monkeypatch.setattr("stage3_data_ui.ms.load_bars", local_loader)
    _daily.clear()
    version = (("example", 1, 2),)
    frame = _daily("example-root", version, "300001", "2026-03-31")
    assert len(select_daily_window(frame, "2026-03-30")) == 1
    again = _daily("example-root", version, "300001", "2026-03-31")
    assert len(select_daily_window(again, "2026-03-31", lookback=1)) == 1
    assert len(calls) == 1
    _daily("example-root", (("example", 2, 2),), "300001", "2026-03-31")
    assert len(calls) == 2
    assert calls[0][2] == Path("example-root")
    _daily.clear()


def test_industry_filter_search_is_literal_and_retains_time_override_flag():
    frame = pd.DataFrame({
        "code": ["300001", "300002"], "name": ["测试[公司", "另一公司"],
        "level1_name": ["电子", "电子"], "level2_name": ["半导体", "元件"],
        "level3_name": ["分立器件", "印制电路板"], "historical_snapshot_override": [True, False],
    })
    result = filter_industries(frame, keyword="[", level1="电子", level2="半导体")
    assert result["code"].tolist() == ["300001"]
    assert bool(result.iloc[0]["historical_snapshot_override"])
    assert filter_industries(frame, keyword="300002", level3="印制电路板")["name"].tolist() == ["另一公司"]
    assert filter_industries(frame, keyword="不存在").empty


def test_csv_download_preserves_chinese_and_explicit_approximation_marker():
    frame = pd.DataFrame({"股票代码": ["300001"], "使用当前分类近似": [True]})
    content = _csv(frame)
    assert content.startswith(b"\xef\xbb\xbf")
    assert "使用当前分类近似" in content.decode("utf-8-sig")
    assert "True" in content.decode("utf-8-sig")
