from pathlib import Path

import pandas as pd
import pytest

from market_fields import add_float_market_cap
from market_sectors import assemble_mapping, load_sectors, official_mapping, parse_catalog, parse_members


CATALOG = [
    {"level": 1, "industry_code": "801080.SI", "industry_name": "电子", "parent_name": None},
    {"level": 2, "industry_code": "801081.SI", "industry_name": "半导体", "parent_name": "电子"},
    {"level": 3, "industry_code": "850811.SI", "industry_name": "集成电路制造", "parent_name": "半导体"},
    {"level": 3, "industry_code": "850812.SI", "industry_name": "集成电路设计", "parent_name": "半导体"},
]


def membership(code="300001", industry_code="850811.SI", industry_name="集成电路制造"):
    return {"code": code, "industry_code": industry_code, "industry_name": industry_name,
            "observed_at": "2026-10-21T00:30:00+08:00", "source_member_since": "2021-07-30",
            "source_url": "https://example.test", "source_data_date": "2026-10-20"}


def test_parse_catalog_preserves_explicit_hierarchy():
    html = "".join(
        f'<div id="level{row["level"]}Items"><div class="lg-industries-item" id="{row["industry_code"]}">'
        f'<div class="lg-industries-item-number">{row["industry_name"]}(12)</div>'
        f'<span class="parent-industry-name">[{row["parent_name"] or ""}]</span></div></div>'
        for row in CATALOG[:3])
    rows = parse_catalog(html)
    assert rows[2]["parent_name"] == "半导体"
    assert rows[2]["industry_name"] == "集成电路制造"
    assert rows[2]["level"] == 3


def test_parse_members_ignores_json_ld_and_filters_bad_stock_codes():
    html = """<script>{"description": "2026-10-20，行业数据"}</script><table>
    <tr class="index-basic-composition-item" data-stock-code="300001.SZ">
    <td>1</td><td>300001.SZ</td><td>公司</td><td>2021-07-30</td></tr>
    <tr class="index-basic-composition-item" data-stock-code="bad">
    <td>2</td><td>bad</td><td>错误</td><td>2021-07-30</td></tr></table>"""
    rows, source_date = parse_members(html)
    assert rows == [{"code": "300001", "source_member_since": "2021-07-30"}]
    assert source_date == "2026-10-20"


def test_empty_source_is_not_a_successful_mapping():
    with pytest.raises(ValueError):
        parse_members("<html>Access denied</html>")


def test_mapping_marks_conflicts_and_unknowns_without_guessing():
    uni = pd.DataFrame({"code": ["300001", "300002", "300003"]})
    mapping, report = assemble_mapping(uni, CATALOG, [
        membership(), membership("300002"),
        membership("300002", "850812.SI", "集成电路设计")], 3)
    assert mapping["status"].tolist() == ["mapped", "conflict", "missing"]
    assert report["coverage_pct"] == 33.33
    assert report["missing_codes"] == ["300003"]
    assert len(report["conflicts"]["300002"]) == 2
    assert mapping.iloc[0]["level1_name"] == "电子"
    assert mapping.iloc[0]["level2_name"] == "半导体"


def _write_mapping(tmp_path: Path):
    target = tmp_path / "industries"
    target.mkdir()
    mapping, _ = assemble_mapping(pd.DataFrame({"code": ["300001"]}), CATALOG, [membership()], 3)
    mapping["available_at"] = mapping["observed_at"]
    mapping.to_parquet(target / "mapping_level3.parquet", index=False)


def test_historical_membership_date_does_not_allow_future_snapshot(tmp_path):
    _write_mapping(tmp_path)
    with pytest.raises(ValueError, match="当前快照"):
        load_sectors("2026-03-31", data_dir=tmp_path)
    result = load_sectors("2026-03-31", data_dir=tmp_path, allow_current_snapshot=True)
    assert bool(result.iloc[0]["historical_snapshot_override"])


def test_sector_cutoff_uses_shanghai_calendar_day(tmp_path):
    _write_mapping(tmp_path)
    with pytest.raises(ValueError):
        load_sectors("2026-10-20", data_dir=tmp_path)
    assert len(load_sectors("2026-10-21", data_dir=tmp_path)) == 1
    assert load_sectors("2026-10-21", codes=[], data_dir=tmp_path).empty


def test_historical_market_cap_requires_raw_price_and_known_shares():
    bars = pd.DataFrame([
        {"code": "300001", "date": "2024-01-02", "close": 10., "price_adjustment": "raw"},
        {"code": "300001", "date": "2024-01-03", "close": 10., "price_adjustment": "raw"},
        {"code": "300001", "date": "2024-01-04", "close": 10., "price_adjustment": "qfq"},
        {"code": "300001", "date": "2024-01-05", "close": 10., "price_adjustment": "raw"},
    ])
    shares = pd.DataFrame([{"code": "300001", "effective_date": "2024-01-01",
                            "available_date": "2024-01-03", "float_shares": 100}])
    result = add_float_market_cap(bars, shares, "2024-01-04")
    assert len(result) == 3
    assert pd.isna(result.iloc[0]["float_market_cap"])
    assert result.iloc[1]["float_market_cap"] == 1000
    assert result.iloc[2]["float_market_cap_status"] == "unsupported_adjusted_price"


def test_market_cap_future_effective_shares_do_not_apply_early():
    bars = pd.DataFrame([{"code": "300001", "date": "2024-01-03",
                          "close": 10., "price_adjustment": "raw"}])
    shares = pd.DataFrame([{"code": "300001", "effective_date": "2024-01-04",
                            "available_date": "2024-01-02", "float_shares": 100}])
    assert pd.isna(add_float_market_cap(bars, shares, "2024-01-03").iloc[0]["float_market_cap"])


def test_market_cap_current_undated_shares_are_rejected():
    bars = pd.DataFrame([{"code": "300001", "date": "2024-01-03", "close": 10.,
                          "price_adjustment": "raw"}])
    with pytest.raises(ValueError, match="缺少字段"):
        add_float_market_cap(bars, pd.DataFrame([{"code": "300001", "float_shares": 100}]), "2024-01-03")


def test_market_cap_duplicate_frame_index_cannot_cross_overwrite_stocks():
    bars = pd.DataFrame([
        {"code": "300001", "date": "2024-01-03", "close": 10., "price_adjustment": "raw"},
        {"code": "300002", "date": "2024-01-03", "close": 20., "price_adjustment": "raw"},
    ], index=[0, 0])
    shares = pd.DataFrame([
        {"code": code, "effective_date": "2024-01-01", "available_date": "2024-01-01",
         "float_shares": size} for code, size in [("300001", 100), ("300002", 200)]])
    assert add_float_market_cap(bars, shares, "2024-01-03")["float_market_cap"].tolist() == [1000, 4000]


def test_market_cap_rejects_conflicting_share_history_and_infinity():
    bars = pd.DataFrame([{"code": "300001", "date": "2024-01-03", "close": float("inf"),
                          "price_adjustment": "raw"}])
    shares = pd.DataFrame([{"code": "300001", "effective_date": "2024-01-01",
                            "available_date": "2024-01-01", "float_shares": value}
                           for value in (100, 200)])
    with pytest.raises(ValueError, match="冲突"):
        add_float_market_cap(bars, shares, "2024-01-03")
    result = add_float_market_cap(bars, shares.iloc[:1], "2024-01-03")
    assert pd.isna(result.iloc[0]["float_market_cap"])


def test_official_six_digit_codes_use_official_names():
    history = pd.DataFrame([
        {"股票代码": "300001", "计入日期": "2021-07-30", "行业代码": "270102", "更新日期": "2025-12-15"},
        {"股票代码": "300001", "计入日期": "2027-01-01", "行业代码": "270103", "更新日期": "2026-10-20"},
    ])
    dictionary = pd.DataFrame([{"行业代码": "270102", "一级行业名称": "电子",
                                "二级行业名称": "半导体", "三级行业名称": "分立器件"}])
    result, report = official_mapping(pd.DataFrame({"code": ["300001", "300002"]}),
                                     history, dictionary, "2026-10-21T01:00:00+08:00")
    assert result.iloc[0]["industry_name"] == "分立器件"
    assert result.iloc[0]["level1_code"] == "270000"
    assert report["mapped_count"] == 1
    assert report["missing_codes"] == ["300002"]


def test_official_same_timestamp_conflict_is_not_silently_resolved():
    history = pd.DataFrame([
        {"股票代码": "300001", "计入日期": "2021-07-30", "行业代码": value, "更新日期": "2025-12-15"}
        for value in ("270102", "270103")])
    dictionary = pd.DataFrame([
        {"行业代码": value, "一级行业名称": "电子", "二级行业名称": "半导体", "三级行业名称": value}
        for value in ("270102", "270103")])
    result, report = official_mapping(pd.DataFrame({"code": ["300001"]}), history, dictionary,
                                     "2026-10-21T01:00:00+08:00")
    assert result.iloc[0]["status"] == "conflict"
    assert pd.isna(result.iloc[0]["industry_name"])
    assert report["mapped_count"] == 0
