# L0 元认知与记忆图谱硬约束 (Meta Rules)

1. **时间戳隔离原则 (Temporal Isolation)**
   严禁在推演与验证中引入未来函数或调用系统当前时间。所有行情特征计算、新闻事件检索及节点状态变更，必须严格锚定基准日 `timestamp <= as_of_date`，杜绝前视偏差（Look-Ahead Bias）。

2. **无验证不入图原则 (Verification Before Ingestion)**
   未经客观数据或 L4 归档事实验证的市场传闻严禁直接写入 L2 逻辑图谱。每个 `ThesisNode` 入图或更新时，必须绑定至少一个可回溯的 `evidence_pointers`（如 `#EV_YYYYMMDD`）及明确的证伪阈值 `invalidation_condition`。

3. **按需展开原则 (On-Demand Expansion)**
   常驻 Prompt 仅加载 L0 元规则与 L1 概念簇索引（严格控制在 2,500 tokens 内）。仅当分析任务路由至特定个股或产业链传导节点时，才按需读取对应的 `memory/L2_graphs/{stock_code}.json` 与 `memory/L4_archive/` 原始记录。
