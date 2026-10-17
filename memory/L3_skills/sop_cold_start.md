# L3 Skill SOP: 陌生个股 10 秒冷启动建图 (Cold-Start Graph Initialization)

1. **适用场景**：当查询标的未命中 `memory/L2_graphs/{stock_code}.json` 时触发。
2. **输入要素（严守 `timestamp <= as_of_date`）**：
   - `fetch_market_data` 获取的近 60 日量价与截至 `as_of_date` 的最近 15 条新闻/归档事件。
   - `verify_priced_in` 计算的 20 日涨跌幅、60 日价格分位数、换手率状态与 `priced_in_ratio`。
3. **建图规范**：
   - 提炼 2~4 个核心多空逻辑节点（`ThesisNode`，涵盖 `BULLISH_LOGIC` / `BEARISH_LOGIC`），每个节点必须绑定 `#EV_YYYYMMDD` 证据指针与明确的可证伪条件 `invalidation_condition`。
   - 构建节点间因果或证伪关系边（`Edge`），并调用 `L2Graph.compute_net_score()` 确定性计算初始净多空得分。
   - 落盘至 `memory/L2_graphs/{stock_code}.json` 并同步将路由条目注册至 `memory/L1_insight_index.md`。
