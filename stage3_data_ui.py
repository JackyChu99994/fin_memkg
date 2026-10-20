"""只读行情数据工作台；界面查询不触发联网或行情重建。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import market_snapshot as ms
from market_sectors import load_sectors


def file_signature(paths: list[Path]) -> tuple:
    """路径、纳秒修改时间和大小共同标识数据版本，避免复用旧文件。"""
    return tuple((str(path.resolve()), path.stat().st_mtime_ns, path.stat().st_size)
                 if path.exists() else (str(path.resolve()), None, None) for path in paths)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@st.cache_data(show_spinner=False, max_entries=8)
def _universe(root: str, version: tuple) -> pd.DataFrame:
    return ms.load_universe(data_dir=Path(root))


@st.cache_data(show_spinner=False, max_entries=12)
def _daily(root: str, version: tuple, code: str, last_day: str) -> pd.DataFrame:
    # 日期或回看窗口改变时复用这一只股票的数据；每个版本首次选择股票才读取底层快照。
    return ms.load_bars(last_day, codes=[code], data_dir=Path(root))


@st.cache_data(show_spinner=False, max_entries=4)
def _index(root: str, version: tuple, last_day: str) -> pd.DataFrame:
    return ms.load_index(last_day, data_dir=Path(root))


@st.cache_data(show_spinner=False, max_entries=4)
def _sector_snapshot(root: str, version: tuple) -> pd.DataFrame:
    return pd.read_parquet(Path(root) / "industries" / "mapping_level3.parquet")


@st.cache_data(show_spinner=False, max_entries=12)
def _sectors(root: str, version: tuple, as_of: str, allow_current: bool) -> pd.DataFrame:
    return load_sectors(as_of, data_dir=Path(root), allow_current_snapshot=allow_current)


def select_daily_window(frame: pd.DataFrame, as_of: str, *, start: str | None = None,
                        lookback: int | None = None) -> pd.DataFrame:
    """闭区间日期过滤；回看窗口按该股票实际记录数计，不越过基准日。"""
    if start is not None and start > as_of:
        raise ValueError("开始日期不能晚于基准日。")
    if lookback is not None and lookback < 1:
        raise ValueError("回看记录数必须大于零。")
    result = frame.loc[frame["date"].le(as_of)].sort_values("date")
    if start:
        result = result.loc[result["date"].ge(start)]
    if lookback is not None:
        result = result.tail(lookback)
    return result.reset_index(drop=True)


def filter_industries(frame: pd.DataFrame, keyword: str = "", level1: str = "全部",
                      level2: str = "全部", level3: str = "全部") -> pd.DataFrame:
    result = frame.copy()
    for field, value in (("level1_name", level1), ("level2_name", level2), ("level3_name", level3)):
        if value != "全部":
            result = result.loc[result[field].fillna("未知").eq(value)]
    keyword = keyword.strip()
    if keyword:
        matched = pd.Series(False, index=result.index)
        for field in ("code", "name", "level1_name", "level2_name", "level3_name"):
            if field in result:
                matched |= result[field].fillna("").astype(str).str.contains(keyword, case=False, regex=False)
        result = result.loc[matched]
    return result.reset_index(drop=True)


def _csv(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def _prices(frame: pd.DataFrame, title: str) -> None:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.06,
                        row_heights=[.72, .28])
    fig.add_trace(go.Candlestick(x=frame["date"], open=frame["open"], high=frame["high"],
                                low=frame["low"], close=frame["close"], name="前复权价格",
                                increasing_line_color="#ef5350", decreasing_line_color="#26a69a"), row=1, col=1)
    colors = ["#ef5350" if close >= opening else "#26a69a"
              for close, opening in zip(frame["close"], frame["open"])]
    fig.add_trace(go.Bar(x=frame["date"], y=frame["volume"], name="成交量（股）",
                        marker_color=colors), row=2, col=1)
    fig.update_layout(title=title, height=470, showlegend=False, xaxis_rangeslider_visible=False,
                      margin=dict(l=15, r=15, t=45, b=10))
    fig.update_yaxes(title_text="元 / 股", row=1, col=1)
    fig.update_yaxes(title_text="成交量（股）", row=2, col=1)
    st.plotly_chart(fig, width="stretch")


def _probe_summary(data_dir: Path) -> None:
    with st.expander("30 分钟行情：已验证的数据源与历史范围"):
        report = _json(data_dir / "intraday" / "probe_report.json")
        attempts = report.get("attempts", [])
        if not attempts:
            st.info("本地还没有分钟行情源验证记录。本页面不会自动发起探测。")
            return
        successful = [item for item in attempts if item.get("rows", 0) > 0]
        target = report.get("target", [])
        if successful and not any(item.get("target_range_spanned") for item in attempts):
            target_label = " 至 ".join(target) if target else "题目要求的历史区间"
            st.warning(f"部分近期分钟行情可读取，但本次探测没有覆盖 {target_label}。"
                       "这不能作为已经获得该历史区间 30 分钟 K 线的证明。")
        columns = ["code", "source", "rows", "first", "last", "target_range_spanned", "status"]
        table = pd.DataFrame(attempts).reindex(columns=columns).rename(columns={
            "code": "股票代码", "source": "来源", "rows": "记录数", "first": "最早时间",
            "last": "最晚时间", "target_range_spanned": "覆盖题目区间", "status": "探测状态"})
        st.dataframe(table, width="stretch", hide_index=True)
        st.caption("以上来自已有验证记录；缺少对应历史数据时，题目运行结果应明确说明日线近似。")


def render_cache(data_dir: Path = ms.DATA_DIR) -> None:
    """日线及指数缓存浏览，只有本地读操作。"""
    data_dir = Path(data_dir)
    st.subheader("行情缓存")
    st.caption("按基准日查看本地行情；改变筛选条件不会联网下载。")
    try:
        paths = ms.snapshot_paths(data_dir)
        missing = [key for key in ("bars", "universe", "meta") if not paths[key].exists()]
        if missing:
            st.info("本机尚无完整日线快照，请先完成行情构建后再查看。")
            _probe_summary(data_dir)
            return
        root = str(paths["bars"].parent)
        version = file_signature(list(paths.values()))
        meta = _json(paths["meta"])
        universe = _universe(root, version)
        first, last = str(meta["date_min"]), str(meta["date_max"])
        start_day, last_day = date.fromisoformat(first), date.fromisoformat(last)
        a, b, c, d = st.columns(4)
        a.metric("当前缓存股票", f"{len(universe):,}")
        b.metric("日线记录", f"{int(meta.get('bar_rows', 0)):,}")
        c.metric("最早交易日", first)
        d.metric("最近交易日", last)
        st.caption(f"构建时间：{meta.get('built_at', '未记录')} · "
                   "股票清单为当前存续股票，历史查询排除尚未上市股票，但不补回已退市样本。")
        if paths["index"].exists():
            index_data = _index(root, version, last)
            if not index_data.empty:
                st.info(f"创业板指 399006：{index_data['date'].min()} 至 "
                        f"{index_data['date'].max()}，共 {len(index_data):,} 条日线。")
            else:
                st.warning("本地指数文件在行情截止日前没有记录。")
        else:
            st.warning("本地缺少创业板指 399006 数据，股票日线仍可浏览。")

        left, right = st.columns([1, 2])
        as_of = left.date_input("分析基准日", value=last_day, key="stage3_daily_asof").isoformat()
        eligible = universe.loc[universe["list_date"].le(as_of)]
        if as_of < first:
            st.warning(f"该基准日早于当前缓存起点 {first}，无法返回相应行情。")
            return
        if as_of > last:
            st.warning(f"基准日晚于本地最近交易日 {last}；以下最多显示到该日，不会补采数据。")
        if eligible.empty:
            st.info("当前股票池中没有在该基准日前上市的股票。")
            return
        labels = dict(zip(eligible["code"], eligible["name"] + " · " + eligible["code"]))
        code = right.selectbox("股票（可输入名称或代码查找）", eligible["code"].tolist(),
                               format_func=lambda value: labels[value], key="stage3_daily_code")
        mode_col, range_col = st.columns([1, 2])
        mode = mode_col.radio("查看范围", ["最近若干条日线", "指定开始日期"], horizontal=True,
                              key="stage3_daily_range_mode")
        lookback, requested_start = None, None
        if mode == "最近若干条日线":
            lookback = range_col.number_input("回看日线条数", min_value=5, max_value=2000,
                                             value=60, step=5, key="stage3_daily_lookback")
        else:
            requested_start = range_col.date_input("开始日期（含当日）", value=start_day,
                                                  key="stage3_daily_start").isoformat()
            if requested_start < first:
                st.warning(f"开始日期超出本地历史覆盖，实际数据最早从 {first} 开始。")
        with st.spinner("读取本地行情…"):
            all_bars = _daily(root, version, code, last)
            frame = select_daily_window(all_bars, as_of, start=requested_start, lookback=lookback)
        if frame.empty:
            st.warning("所选股票在该日期范围内没有缓存记录；可能尚未上市、停牌或数据存在缺口。")
            return
        if lookback and len(frame) < lookback:
            st.info(f"所选股票截至基准日只有 {len(frame)} 条可用记录，少于请求的 {lookback} 条。")
        st.caption(f"{labels[code]} · 实际区间 {frame['date'].min()} 至 {frame['date'].max()} · "
                   f"{len(frame)} 条日线 · 价格为前复权，成交量为股，换手率为百分数。")
        _prices(frame, labels[code])
        renamed = frame.rename(columns={"date": "交易日", "code": "股票代码", "open": "开盘",
                                        "high": "最高", "low": "最低", "close": "收盘",
                                        "volume": "成交量（股）", "amount": "成交额（元）",
                                        "turnover_pct": "换手率（%）"})
        st.dataframe(renamed.sort_values("交易日", ascending=False), hide_index=True, width="stretch")
        st.download_button("下载当前行情 CSV", _csv(frame), file_name=f"daily_{code}_{as_of}.csv",
                           mime="text/csv", key="stage3_daily_download")
        _probe_summary(data_dir)
    except (OSError, ValueError, KeyError) as exc:
        st.error(f"无法读取所选行情：{exc}")


def render_industries(data_dir: Path = ms.DATA_DIR) -> None:
    """当前申万三级行业及严格历史查询；明确披露任何当前分类近似。"""
    data_dir = Path(data_dir)
    st.subheader("细分行业")
    st.caption("申万 2021 分类，支持一级、二级和三级筛选。历史归属不会由当前分类自动替代。")
    mapping_path = data_dir / "industries" / "mapping_level3.parquet"
    if not mapping_path.exists():
        st.info("本机还没有申万三级行业映射，请先完成行业数据构建。")
        return
    try:
        paths = ms.snapshot_paths(data_dir)
        version = file_signature([mapping_path, data_dir / "industries" / "report_level3.json", paths["universe"]])
        snapshot = _sector_snapshot(str(data_dir), version)
        available = pd.to_datetime(snapshot["available_at"], utc=True, errors="coerce")
        observed = available.dropna().max()
        if pd.isna(observed):
            st.error("行业映射缺少观测日期，无法证明在所选时点可用。")
            return
        observed_day = observed.tz_convert("Asia/Shanghai").date()
        mapped = snapshot["status"].eq("mapped")
        a, b, c, d = st.columns(4)
        a.metric("当前映射覆盖率", f"{100 * mapped.mean():.1f}%")
        b.metric("已映射 / 股票池", f"{int(mapped.sum()):,} / {len(snapshot):,}")
        c.metric("三级行业数", f"{snapshot.loc[mapped, 'level3_name'].nunique():,}")
        d.metric("未映射或冲突", f"{int((~mapped).sum()):,}")
        report = _json(data_dir / "industries" / "report_level3.json")
        source_label = ("申万宏源研究官方分类文件" if "official" in report.get("source", "").lower()
                        else "乐咕申万分类分发数据" if "legulegu" in report.get("source", "").lower()
                        else "本地已保存分类；请核对来源报告")
        st.caption(f"当前分类最近观测日期：{observed_day.isoformat()} · 来源：{source_label}。"
                   "历史文件可能追溯修订，计入日期不等于当时已公开。")
        as_of = st.date_input("行业查询基准日", value=observed_day, key="stage3_sector_asof").isoformat()
        allow_current = st.checkbox("允许用当前分类作描述性比较（不作为历史行业事实）",
                                    value=False, key="stage3_sector_allow_current")
        try:
            frame = _sectors(str(data_dir), version, as_of, allow_current)
        except ValueError:
            st.warning(f"本地分类是在 {observed_day.isoformat()} 观察到的，无法证明在 {as_of} 已经可用。"
                       "严格历史查询已停止。仅作描述性比较时，可显式勾选上方选项。")
            return
        universe_version = file_signature(list(paths.values()))
        universe = _universe(str(paths["universe"].parent), universe_version)
        roster = universe.loc[universe["list_date"].le(as_of), ["code", "name", "list_date"]]
        frame = frame.merge(roster, on="code", how="inner", validate="one_to_one")
        if frame.empty:
            st.info("当前股票池中没有在所选基准日前上市的行业记录。")
            return
        if frame["historical_snapshot_override"].any():
            st.warning("正在使用后来观察到的当前分类作描述性比较。这不是该基准日的历史行业归属；"
                       "表格与下载文件保留了“使用当前分类近似”标记。")
        keyword = st.text_input("搜索股票代码、公司名称或行业", key="stage3_sector_search",
                                placeholder="例如：300750、宁德时代、半导体")
        c1, c2, c3 = st.columns(3)
        level1 = c1.selectbox("一级行业", ["全部"] + sorted(frame["level1_name"].dropna().unique()),
                             key="stage3_sector_level1")
        first = filter_industries(frame, level1=level1)
        level2 = c2.selectbox("二级行业", ["全部"] + sorted(first["level2_name"].dropna().unique()),
                             key="stage3_sector_level2")
        second = filter_industries(first, level2=level2)
        level3 = c3.selectbox("三级行业", ["全部"] + sorted(second["level3_name"].dropna().unique()),
                             key="stage3_sector_level3")
        filtered = filter_industries(frame, keyword, level1, level2, level3)
        st.caption(f"符合筛选条件：{len(filtered):,} 只。分布图和导出文件与当前筛选一致。")
        if filtered.empty:
            st.info("没有符合当前筛选的股票，请调整行业或搜索词。")
            return
        distribution_level = "level1_name" if level1 == "全部" else "level2_name" if level2 == "全部" else "level3_name"
        distribution = filtered[distribution_level].fillna("未知").value_counts().rename_axis("行业").reset_index(name="股票数")
        fig = px.bar(distribution.head(30), x="股票数", y="行业", orientation="h",
                     title="当前筛选的行业分布" + ("（最多显示 30 类）" if len(distribution) > 30 else ""))
        fig.update_layout(height=max(280, min(650, 28 * len(distribution) + 80)),
                          yaxis=dict(autorange="reversed"), margin=dict(l=10, r=10, t=45, b=10))
        st.plotly_chart(fig, width="stretch")
        labels = {"code": "股票代码", "name": "公司名称", "level1_name": "一级行业",
                  "level2_name": "二级行业", "level3_name": "三级行业", "status": "映射状态",
                  "available_at": "观测时间", "historical_snapshot_override": "使用当前分类近似"}
        display = filtered[list(labels)].rename(columns=labels)
        display["映射状态"] = display["映射状态"].replace({"mapped": "已映射", "missing": "缺失", "conflict": "冲突"})
        st.dataframe(display, width="stretch", hide_index=True)
        st.download_button("下载当前行业筛选 CSV", _csv(display),
                           file_name=f"industries_{as_of}.csv", mime="text/csv", key="stage3_sector_download")
    except (OSError, ValueError, KeyError) as exc:
        st.error(f"无法读取行业数据：{exc}")
