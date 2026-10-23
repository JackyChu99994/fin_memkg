"""Streamlit entry for the local market data and acceptance workspace."""
from pathlib import Path

import streamlit as st

from market_snapshot import DATA_DIR


def render_stage3(data_dir: Path = DATA_DIR) -> None:
    from stage3_data_ui import render_cache, render_industries
    from stage3_results_ui import render_acceptance

    st.markdown("<style>.block-container{padding-top:4rem;}</style>", unsafe_allow_html=True)
    heading, refresh = st.columns([5, 1])
    with heading:
        st.title("行情数据与验收")
        st.caption("查看本地行情和行业分类，按官方基准日运行验收并下载结果。")
    with refresh:
        st.button("刷新显示", key="stage3_refresh", width="stretch")

    cache, industries, acceptance = st.tabs(["行情缓存", "行业映射", "任务验收"])
    with cache:
        render_cache(data_dir)
    with industries:
        render_industries(data_dir)
    with acceptance:
        render_acceptance(data_dir)
