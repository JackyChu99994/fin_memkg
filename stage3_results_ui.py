"""Streamlit acceptance view; jobs run only on an explicit button click."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import streamlit as st

import market_snapshot as ms
from stage3_jobs import list_runs, read_existing, run_acceptance

TASKS = {
    "task01": {"label": "task_01 · 技术指标共振筛选", "as_of": "2026-03-31", "timeout": 300},
    "task36": {"label": "task_36 · 盘中异动筛选", "as_of": "2024-08-22", "timeout": 480},
}
MODES = {
    "auto": "自动选择：分钟数据不足时使用日线近似",
    "minute": "严格分钟：必须具有完整的历史 30 分钟数据",
    "daily": "日线近似：按题目许可，用日 K 线筛选",
}
MODE_NAMES = {"MINUTE_30": "真实 30 分钟行情", "DAILY_OHLC_APPROX": "日线近似"}
CHECK_NAMES = {
    "file_created": "已生成结果文件", "valid_codes": "股票代码格式", "count_limit": "结果数量限制",
    "data_fetched": "行情读取记录", "macd_computed": "MACD 计算记录", "rsi_computed": "RSI 计算记录",
    "ma_computed": "均线计算记录", "anomaly_type": "异动类型字段",
    "closing_position": "收盘位置字段", "continuation_field": "次日持续字段",
    "intraday_attempted": "分钟行情尝试记录",
}
STATE_NAMES = {"completed": "运行完成", "failed": "运行失败", "timeout": "运行超时"}


def _seconds(value) -> str:
    try:
        return f"{float(value):.2f} 秒"
    except (TypeError, ValueError):
        return "未记录"


def _history_label(record: dict, *, existing: bool = False) -> str:
    prefix = "已有验收" if existing else str(record.get("started_at") or record.get("run_id") or "历史运行")
    mode = (record.get("summary") or {}).get("mode")
    suffix = f" · {MODE_NAMES.get(mode, mode)}" if mode else ""
    return f"{prefix} · {STATE_NAMES.get(record.get('state'), '状态未记录')}{suffix}"


def _grading(summary: dict) -> None:
    grade = summary.get("grading") or summary.get("official_automated_grade") or {}
    scores = grade.get("scores") or {}
    st.markdown("**官方自动检查**")
    if scores:
        st.dataframe(pd.DataFrame([
            {"检查项": CHECK_NAMES.get(name, name), "得分": score}
            for name, score in scores.items()
        ]), hide_index=True, width="stretch")
        mean = grade.get("automated_mean")
        if isinstance(mean, (float, int)):
            st.caption(f"自动检查均分：{mean:.2f} / 1.00。检查内容包括文件、字段格式和计算过程记录。")
    else:
        st.info("这条运行记录尚无自动检查结果。")
    if grade.get("llm_judge") == "NOT_RUN" or grade.get("overall_score") is None:
        st.info("模型评审尚未完成，完整评测总分未生成。自动检查满分不等于完整评测满分，也不能替代计算核验。")


def _evidence(record: dict, data_dir: Path) -> list[dict]:
    directory = Path(record["output_dir"]).resolve()
    if not directory.is_relative_to(data_dir.resolve()):
        raise ValueError("结果目录不在当前数据目录内")
    path = directory / "evidence.json"
    if not path.is_file():
        return []
    content = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(content, list):
        raise ValueError("指标依据文件格式不正确")
    return [row for row in content if isinstance(row, dict) and "code" in row]


def _task01_result(record: dict, summary: dict, data_dir: Path, key: str) -> None:
    codes = [str(code) for code in summary.get("written_codes", [])]
    st.markdown("**筛选结果**")
    if codes:
        st.dataframe(pd.DataFrame({"股票代码": codes}), hide_index=True, width="stretch")
    else:
        st.info("本次计算没有筛出满足所采用条件的股票。空结果与运行失败分别记录。")
    st.caption("采用 RSI14；窗口内需满足 MACD 金叉与至少两次放量，并要求 RSI 反弹、均线上穿和放量在同日共振。")
    if summary.get("missing_codes"):
        st.warning(f"有 {len(summary['missing_codes'])} 只股票缺少行情，本次结果覆盖不完整。")
    if not st.checkbox("查看单只股票的指标依据", key=f"{key}_show_evidence"):
        return
    try:
        rows = _evidence(record, data_dir)
    except (OSError, ValueError, KeyError):
        st.warning("暂时无法读取这次运行的指标依据，可在日志中检查结果文件状态。")
        return
    if not rows:
        st.info("该记录未保存单股指标依据。重新运行验收可生成。")
        return
    by_code = {str(row["code"]): row for row in rows}
    options = [code for code in codes if code in by_code] + sorted(set(by_code) - set(codes))
    selected = st.selectbox("选择股票", options, key=f"{key}_evidence_code")
    row = by_code[selected]
    if not row.get("eligible_history"):
        st.info("历史行情长度不足，未纳入指标筛选。")
        return
    st.write("该股满足筛选条件。" if row.get("selected") else "该股未同时满足全部筛选条件。")
    st.dataframe(pd.DataFrame([
        {"信号": label, "发生日期": "、".join(map(str, row.get(field, []))) or "窗口内未出现"}
        for label, field in [
            ("MACD 金叉", "macd_cross_dates"), ("RSI 从超卖区反弹", "rsi_rebound_dates"),
            ("MA5 上穿 MA8", "ma_cross_dates"), ("同日共振", "joint_signal_dates"),
        ]
    ]), hide_index=True, width="stretch")
    st.caption(f"计算使用 {row.get('history_rows', '未记录')} 根日 K 线；放量天数 {row.get('volume_spike_days', 0)}。")
    if row.get("signals"):
        details = pd.DataFrame(row["signals"]).rename(columns={
            "date": "日期", "rsi14": "RSI14", "volume": "当日成交量",
            "previous_5_volume_mean": "前五日平均成交量", "ma5": "MA5", "ma8": "MA8",
        })
        st.dataframe(details, hide_index=True, width="stretch")


def _task36_result(summary: dict) -> None:
    mode = summary.get("mode")
    if mode == "DAILY_OHLC_APPROX":
        st.warning("本次实际采用日线近似（DAILY_OHLC_APPROX）。它不能验证真实 30 分钟涨跌路径、同日时段量比或两根 K 线收复失地。")
        st.caption("下表“幅度”为日振幅；这些是日线近似候选，不应当作已证实的分钟信号。")
    elif mode == "MINUTE_30":
        st.success("本次使用完整覆盖请求区间的真实 30 分钟 K 线。")
    else:
        st.warning("该记录未明确保存实际数据模式，需先核对结果。")
    metrics = st.columns(3)
    metrics[0].metric("通过次日确认的事件", summary.get("confirmed_count", 0))
    metrics[1].metric("待次日验证的事件", summary.get("pending_count", 0))
    metrics[2].metric("次日未持续的事件", summary.get("rejected_continuation_count", 0))
    st.caption("数量按事件统计，同一股票可能出现多次事件。待验证事件不计入已确认结果；不使用基准日之后的行情。")
    candidates = summary.get("candidates") or []
    if not candidates:
        st.info("本模式未筛出候选。若采用日线近似，这不能证明真实分钟信号不存在。")
        return
    status_names = {"是": "通过次日确认", "待验证": "待验证", "否": "次日未持续"}
    display = pd.DataFrame([{
        "股票代码": str(row.get("code", "")), "异动日期": row.get("date"),
        "类型": row.get("type"), "幅度（%）": row.get("change_pct"),
        "收盘位置（%）": row.get("closing_position_pct"),
        "次日验证": status_names.get(row.get("continuation"), "未记录"),
        "验证日期": row.get("confirmation_date") or "尚无可用次日",
    } for row in candidates])
    st.dataframe(display, hide_index=True, width="stretch")


def _record_view(record: dict, task: str, data_dir: Path, key: str) -> None:
    state = record.get("state")
    summary = record.get("summary") or {}
    timeout = summary.get("timeout_seconds", TASKS[task]["timeout"])
    if state == "timeout":
        st.error(f"本次运行超过 {timeout} 秒限制。此前的成功记录仍可在上方选择查看。")
    elif state == "failed":
        st.error(f"本次验收未完成。{record.get('error') or '详细原因见运行日志。'}")
        st.caption("此前的成功记录仍可在“查看记录”中选择。")
        if task == "task36":
            st.caption("严格分钟模式需要完整历史数据；缺少目标区间时会明确失败。可改用自动选择或日线近似。")
    elif state == "completed":
        st.success("本次运行完成。请结合实际数据模式、覆盖范围和各项检查判断结果。")
    else:
        st.warning("该记录的运行状态未明确。")
    if summary:
        elapsed = summary.get("elapsed_seconds", record.get("elapsed_seconds"))
        count = summary.get("evaluated_count", summary.get("daily_codes", "未记录"))
        metrics = st.columns(3)
        metrics[0].metric("运行耗时", _seconds(elapsed))
        metrics[1].metric("任务时限", f"{timeout} 秒")
        metrics[2].metric("已读取行情的股票", count)
        window = summary.get("window") or []
        if window:
            st.caption(f"计算区间：{window[0]} 至 {window[-1]}；基准日：{summary.get('as_of', TASKS[task]['as_of'])}。")
        if summary.get("within_timeout") is False:
            st.warning("这次计算未满足任务时限。")
        _grading(summary)
        if task == "task01":
            _task01_result(record, summary, data_dir, key)
        else:
            _task36_result(summary)
        with st.expander("数据边界与计算口径"):
            st.write("股票池来自当前存续股票清单，不能完全还原历史退市样本；日线前复权数据也不是历史时点归档的复权版本。")
            if task == "task01":
                st.write("题目文字与预期行为存在差异，本验收同时保留窗口条件和同日共振条件。参考答案重合度只作辅助信息。")
            else:
                st.write("真实分钟与日线近似使用不同条件。最后一个分析日尚无可用次日收盘时，后续验证保留为待验证。")
    elif state in {"failed", "timeout"}:
        st.caption(f"本次等待耗时：{_seconds(record.get('elapsed_seconds'))}。")
    else:
        st.info("这条记录没有可展示的验收摘要。")
    output_text = record.get("output_text")
    if output_text is not None:
        with st.expander("结果文件预览"):
            st.code(output_text or "（结果文件为空）", language="text")
    if summary or output_text is not None:
        buttons = st.columns(2)
        if output_text is not None:
            buttons[0].download_button("下载结果 TXT", output_text,
                                       file_name="result.txt" if task == "task01" else "intraday_signal.txt",
                                       mime="text/plain", key=f"{key}_download_result")
        if summary:
            buttons[1].download_button("下载验收摘要 JSON", json.dumps(summary, ensure_ascii=False, indent=2),
                                       file_name=f"{task}_summary.json", mime="application/json",
                                       key=f"{key}_download_summary")
    with st.expander("运行日志"):
        full_log = "\n\n".join(str(value) for value in (record.get("error"), record.get("log")) if value)
        if len(full_log) > 8000:
            st.caption("日志较长，页面仅显示末尾 8,000 个字符。可下载完整日志查看全部内容。")
        st.code(full_log[-8000:] or "该记录未保存额外日志。", language="text")
        if full_log:
            st.download_button("下载完整日志", full_log, file_name=f"{task}_run.log",
                               mime="text/plain", key=f"{key}_download_log")


def render_acceptance(data_dir: Path = ms.DATA_DIR) -> None:
    """Render existing and historical results without running work on page reruns."""
    data_dir = Path(data_dir)
    namespace = hashlib.sha256(str(data_dir.resolve()).encode()).hexdigest()[:10]
    root_key = f"stage3_acceptance_{namespace}"
    task = st.selectbox("选择验收任务", list(TASKS), format_func=lambda value: TASKS[value]["label"],
                        key="stage3_task")
    key = f"{root_key}_{task}"
    spec = TASKS[task]
    st.caption(f"官方固定基准日 {spec['as_of']} · 超时限制 {spec['timeout']} 秒。运行使用本地快照；只有点击按钮才开始计算。")
    mode = "auto"
    if task == "task36":
        mode = st.selectbox("数据模式", list(MODES), format_func=MODES.get, key="stage3_mode")
        probe_path = data_dir / "intraday" / "probe_report.json"
        try:
            probe = json.loads(probe_path.read_text(encoding="utf-8")) if probe_path.is_file() else {}
            attempts = probe.get("attempts", [])
            if (probe.get("target") == ["2024-08-16", "2024-08-22"] and attempts
                    and not any(item.get("target_range_spanned") for item in attempts)
                    and any(item.get("status") == "HISTORICAL_RANGE_UNAVAILABLE" for item in attempts)):
                st.caption("已保存的新浪／腾讯小样本探测未取得本题历史分钟区间。自动模式会检查本地缓存，数据仍不足时采用日线近似。")
        except (OSError, ValueError, TypeError, AttributeError):
            st.caption("源探测记录暂时无法读取；实际覆盖范围以本次验收检查为准。")
    just_run = None
    if st.button("运行本次验收", type="primary", key="stage3_run"):
        with st.spinner("正在读取本地行情、计算信号并执行官方自动检查……"):
            try:
                just_run = run_acceptance(task, mode=mode, data_dir=data_dir)
            except Exception as exc:
                st.error("无法启动本次验收。已有记录仍然保留。")
                with st.expander("启动错误详情", expanded=True):
                    st.code(f"{type(exc).__name__}: {exc}", language="text")
    try:
        existing = read_existing(task, data_dir=data_dir)
    except (OSError, ValueError, KeyError):
        existing = None
        st.warning("已有验收记录暂时无法读取。")
    try:
        runs = list_runs(task, data_dir=data_dir)
    except (OSError, ValueError, KeyError):
        runs = []
        st.warning("历史运行列表暂时无法读取。")
    records = {}
    labels = {}
    if existing:
        records["existing"] = existing
        labels["existing"] = _history_label(existing, existing=True)
    for run in runs:
        option = f"run:{run['run_id']}"
        records[option] = run
        labels[option] = _history_label(run)
    history_key = f"stage3_history_{task}"
    if just_run:
        option = f"run:{just_run['run_id']}"
        records[option] = just_run
        labels[option] = _history_label(just_run)
        st.session_state[history_key] = option
    if not records:
        st.info("尚无验收记录。准备好本地行情后，点击“运行本次验收”。")
        return
    if st.session_state.get(history_key) not in records:
        st.session_state[history_key] = next(iter(records))
    selected = st.selectbox("查看记录", list(records), format_func=labels.get, key=history_key)
    st.caption("以下展示所选记录的结果；上方运行选项只影响下一次验收。")
    record_key = hashlib.sha256(selected.encode()).hexdigest()[:8]
    _record_view(records[selected], task, data_dir, f"{key}_{record_key}")
