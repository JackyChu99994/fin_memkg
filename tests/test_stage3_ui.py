"""Exercise page controls with small local fixtures; no market or model requests."""
from datetime import date
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import stage3_jobs as jobs


def page(data_dir):
    from pathlib import Path
    from stage3_ui import render_stage3
    render_stage3(Path(data_dir))


def grade(task):
    config = jobs.TASKS[task]
    return {"task_id": config["id"], "commit": jobs.COMMIT, "task_file_sha256": jobs.SHA256,
            "scores": {key: 1.0 for key in config["checks"]}, "automated_mean": 1.0,
            "llm_judge": "NOT_RUN", "overall_score": None}


@pytest.fixture
def dataset(tmp_path):
    universe = pd.DataFrame([
        {"code": "300001", "name": "甲公司", "list_date": "2020-01-01"},
        {"code": "300002", "name": "乙公司", "list_date": "2026-04-01"},
    ])
    universe.to_parquet(tmp_path / "universe.parquet")
    dates = ["2026-03-30", "2026-03-31", "2026-04-01"]
    pd.DataFrame([
        {"code": code, "date": day, "open": 10, "close": 11, "high": 12, "low": 9,
         "volume": 1000, "amount": 11000, "turnover_pct": 1}
        for code in universe["code"] for day in dates
    ]).to_parquet(tmp_path / "bars.parquet")
    pd.DataFrame({"date": dates, "close": [100, 101, 102]}).to_parquet(tmp_path / "index.parquet")
    (tmp_path / "meta.json").write_text(json.dumps({
        "date_min": dates[0], "date_max": dates[-1], "bar_rows": 6, "built_at": "2026-10-21",
    }), encoding="utf-8")
    industries = tmp_path / "industries"
    industries.mkdir()
    pd.DataFrame([
        {"code": code, "status": "mapped", "level1_name": level1, "level2_name": level2,
         "level3_name": level3, "available_at": "2026-10-21T01:00:00+08:00"}
        for code, level1, level2, level3 in [
            ("300001", "电子", "半导体", "分立器件"),
            ("300002", "电力设备", "电池", "锂电池"),
        ]
    ]).to_parquet(industries / "mapping_level3.parquet")
    for task in ("task01", "task36"):
        config = jobs.TASKS[task]
        output = tmp_path / "acceptance" / task
        output.mkdir(parents=True)
        summary = {"as_of": config["as_of"], "within_timeout": True,
                   "timeout_seconds": config["timeout"], "elapsed_seconds": 1.2,
                   "coverage_complete": True, "written_codes": ["300001"],
                   "evaluated_count": 1, "mode": "DAILY_OHLC_APPROX",
                   "candidate_count": 1, "confirmed_count": 0, "pending_count": 1,
                   "rejected_continuation_count": 0,
                   "candidates": [{"code": "300001", "date": "2024-08-22", "type": "急拉",
                                   "change_pct": 8.5, "closing_position_pct": 80,
                                   "continuation": "待验证", "confirmation_date": None}],
                   config["grade"]: grade(task)}
        (output / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        (output / config["output"]).write_text("300001\n", encoding="utf-8")
    return tmp_path


def test_missing_data_is_explained_without_starting_jobs(tmp_path):
    with patch("stage3_results_ui.run_acceptance") as run:
        app = AppTest.from_function(page, args=(str(tmp_path),), default_timeout=15).run()
        assert not app.exception
        assert not app.error
        assert any("尚无完整日线快照" in item.value for item in app.info)
        assert any("尚无验收记录" in item.value for item in app.info)
        app.run()
        run.assert_not_called()


def test_daily_cutoff_excludes_future_rows_and_new_listings(dataset):
    with patch("stage3_results_ui.run_acceptance") as run:
        app = AppTest.from_function(page, args=(str(dataset),), default_timeout=15).run()
        app.selectbox(key="stage3_daily_code").select("300002").run()
        app.date_input(key="stage3_daily_asof").set_value(date(2026, 3, 31)).run()
        assert not app.exception
        assert not app.error
        assert app.selectbox(key="stage3_daily_code").options == ["甲公司 · 300001"]
        table = next(table.value for table in app.dataframe if "交易日" in table.value)
        assert table["交易日"].max() == "2026-03-31"
        run.assert_not_called()


def test_historical_industry_requires_explicit_override(dataset):
    app = AppTest.from_function(page, args=(str(dataset),), default_timeout=15).run()
    app.date_input(key="stage3_sector_asof").set_value(date(2026, 3, 31)).run()
    assert not app.exception
    assert any("严格历史查询已停止" in item.value for item in app.warning)
    app.checkbox(key="stage3_sector_allow_current").check().run()
    assert not app.exception
    assert not app.error
    table = next(table.value for table in app.dataframe if "使用当前分类近似" in table.value)
    assert table["股票代码"].tolist() == ["300001"]
    assert table["使用当前分类近似"].all()
    app.text_input(key="stage3_sector_search").set_value("不存在").run()
    assert any("没有符合当前筛选" in item.value for item in app.info)


def test_industry_parent_change_resets_incompatible_child_filters(dataset):
    app = AppTest.from_function(page, args=(str(dataset),), default_timeout=15).run()
    app.selectbox(key="stage3_sector_level1").select("电子").run()
    app.selectbox(key="stage3_sector_level2").select("半导体").run()
    app.selectbox(key="stage3_sector_level3").select("分立器件").run()
    app.selectbox(key="stage3_sector_level1").select("电力设备").run()
    assert not app.exception
    assert not app.error
    table = next(table.value for table in app.dataframe if "使用当前分类近似" in table.value)
    assert table["股票代码"].tolist() == ["300002"]


def test_failed_strict_minute_click_keeps_existing_result_and_does_not_rerun(dataset):
    failed = {"task": "task36", "run_id": "task36-test", "state": "failed",
              "output_dir": str(dataset / "web_runs" / "task36-test"), "summary": None,
              "output_text": None, "log": "missing intervals", "error": "严格分钟数据不足",
              "started_at": "2026-10-21T12:00:00+08:00", "elapsed_seconds": 1}
    with patch("stage3_results_ui.run_acceptance", return_value=failed) as run, \
            patch("stage3_results_ui.list_runs", return_value=[]):
        app = AppTest.from_function(page, args=(str(dataset),), default_timeout=15).run()
        app.selectbox(key="stage3_task").select("task36").run()
        assert any("日线近似（DAILY_OHLC_APPROX）" in item.value for item in app.warning)
        assert next(m.value for m in app.metric if m.label == "待次日验证的事件") == "1"
        app.selectbox(key="stage3_mode").select("minute").run()
        run.assert_not_called()
        app.button(key="stage3_run").click().run()
        run.assert_called_once_with("task36", mode="minute", data_dir=dataset)
        assert not app.exception
        assert any("本次验收未完成" in item.value for item in app.error)
        app.selectbox(key="stage3_history_task36").select("existing").run()
        assert not app.exception
        assert not app.error
        assert any("日线近似（DAILY_OHLC_APPROX）" in item.value for item in app.warning)
        app.run()
        assert run.call_count == 1
