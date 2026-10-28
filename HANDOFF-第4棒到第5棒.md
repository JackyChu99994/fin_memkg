Fin-MemKG · 交接文档（第 4 棒 → 第 5 棒）
交接日期：2026-10-28
上游基线：https://github.com/JackyChu99994/fin_memkg  提交 61f8d6a（2026-10-23，PR #6 合并后）
本棒新增：modules/l0l4-memory/（92 个文件）+ 本文件
根目录改动：0 个文件（原有代码一行未动）

═══════════════════════════════════════════
0. 先读这里
═══════════════════════════════════════════

【前提】本棒只在 modules/ 下新增一个目录，不修改根目录任何文件。
  合并后 modules/l0l4-memory 与根目录的行情数据层并存，互不覆盖。

【定位】根目录 = 模块 A（行情数据层，第 3 棒）；modules/l0l4-memory = 模块 B（记忆与判断层，第 4 棒）。
  两层通过 data/market/{bars,index,universe}.parquet 对接，模块 B 只读、不写。

═══════════════════════════════════════════
1. 本棒交付了什么
═══════════════════════════════════════════

一句话：把"读新闻做判断"从现场发挥，变成一张带状态、可回溯的活地图。

五个问题（详见 modules/l0l4-memory/PROBLEM.md）：

  Q1 新闻该不该进图     L1 路由 + L0 六条元规则；40 条真实新闻过滤掉 51.3%
  Q2 新消息推翻旧逻辑   状态机：反向证伪（不删除）、同向合并证据、反转惩罚
  Q3 结论凭什么         每条边带 archive_ref → L4 原文；可回溯率 100%
  Q4 产业链怎么传导     行业节点 + 供应商边，两跳路径
  Q5 结论对不对         事件研究 CAR，支持 as_of 时点约束（防未来函数）

配套：Streamlit 三栏大屏、每日任务、60 秒近实时监听、降噪漏斗实验、幻觉对照实验。

═══════════════════════════════════════════
2. 怎么跑（5 分钟）
═══════════════════════════════════════════

  cd modules/l0l4-memory
  python setup_env.py          # 装依赖 + 写 .env + 测 Neo4j + 建约束 + 灌演示图 + 跑测试
  streamlit run app.py         # http://localhost:8501

只体检不改动： python setup_env.py --check
没有 Neo4j：   .env 里设 MEMKG_STORE=local，自动落到本地 JSON

═══════════════════════════════════════════
3. 与模块 A 的接口
═══════════════════════════════════════════

  模块 A ──写出──► data/market/bars.parquet      列：date, close, code（其余列忽略）
                   data/market/index.parquet     指数（symbol 形如 sz399006）
                   data/market/universe.parquet  股票池 + 行业
                   data/market/meta.json         版本/区间/覆盖

  模块 B ──只读──► market_bridge.py
                   命中：source="snapshot"（离线、可复现、带版本）
                   未命中：自动回退 AkShare（source="akshare"）→ 缓存 → 模拟

  规则：个股与基准必须同源，绝不混用，否则 β 会失真。

═══════════════════════════════════════════
4. 验证记录（2026-10-28，本机实测）
═══════════════════════════════════════════

  测试              python -m unittest discover -s tests → 25 passed
  CAR（快照）        300750 @2026-10-20：CAR −5.68%，β=0.44，source=snapshot
  降噪漏斗           40 条真实新闻 → 19 条通过 L0 → 4 条独立逻辑（压缩比 10:1）
  全市场扫描         1411 只快照上 1396 只有效样本，0.57 秒算完（脚本 car_scan.py）
  幻觉对照           44 条语料 × 3 轮：V4 无编造数字（1 次自相矛盾）；结论见 docs

═══════════════════════════════════════════
5. 已知限制
═══════════════════════════════════════════

  1. 默认快照为 14 只自建（创业板 1411 只的大快照已被移出仓库，data/ 不入库）
  2. 非创业板标的（002/600/000）不在快照里，会回退 AkShare，需要联网
  3. CAR 使用前复权序列，属"采集时点复权"，仍有轻微前视偏差（报告需写明）
  4. 抽取评测（P/R/F1）与 RAG 对照实验尚未做——这是第 5 棒的主要任务

═══════════════════════════════════════════
6. 第 5 棒要做什么（按收益排序）
═══════════════════════════════════════════

  1) 抽取评测：人工标 40 条，算实体/关系的 P/R/F1 —— 报告第 6 章的数字
     建议：在 modules/l0l4-memory/experiments/ 下加 eval_extraction.py
  2) RAG 对照：检索 top-k 喂 LLM vs 本系统，证明"状态化记忆"的价值
     脚本可复用 experiments/hallucination_demo.py 的检测逻辑（数字核对/矛盾检测）
  3) 报告正文 + PPT：素材在 docs/报告写作包.md、docs/全局复盘与答辩防守.md
  4) 可选：把模块 B 的输出接进模块 A 的 task 验收流程（加分项，非必需）

  验收标准：
      cd modules/l0l4-memory && python -m unittest discover -s tests   # 25 passed
      streamlit run app.py                                             # A 场景能反转

═══════════════════════════════════════════
7. 文件清单（只列新增）
═══════════════════════════════════════════

  modules/l0l4-memory/
    ├── 14 个 .py：config / l0_rules / l1_router / l4_archive / store / pipeline /
    │              market_bridge / l3_event_study / agent / viz / app /
    │              fetch_real / watch / daily_job
    ├── demo_graph.py、update_logic.py（薄封装示例）
    ├── setup_env.py、setup.bat、start_app.bat
    ├── README.md、PROBLEM.md、requirements.txt、.env.example
    ├── docs/（7 份：交接、Git 指南、报告写作包、复盘防守、融合方案等）
    ├── experiments/（降噪漏斗、画图、幻觉对照）
    ├── tests/（25 个用例）
    ├── scripts/（建快照、全市场 CAR 扫描）
    ├── tools/、scheduler/、memory/、archive/
    └── 不含：.env、data/、logs/、*.bak.py

═══════════════════════════════════════════
8. 一句话交接
═══════════════════════════════════════════

  数据和判断分两层，接口是四个 parquet 文件；
  本棒把"判断"做成了可回溯、可证伪、可检验的东西，下一棒把它变成实验数字和稿子。
