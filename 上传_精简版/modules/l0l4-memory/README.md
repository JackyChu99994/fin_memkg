# 模块 B · L0-L4 记忆层

> 本目录是模块 B；仓库根目录是模块 A（行情数据层）。两层通过 `data/market/*.parquet` 对接。

# Fin-MemKG · L0–L4 分层记忆的股票量化情报系统（课程 Demo 包）

> 选题 5：股票量化情报——多源市场信息融合与投资研究系统
> 参考理念：复旦梁老师 L0–L4 分层记忆 + GenericAgent（**只借思想，不抄代码**）
> 本包是在你现有 `demo_graph.py` / `update_logic.py` 基础上的**增量升级**，不是重写。

---

## 0. 它解决你哪几个具体问题

| 你现在的状态 | 本包给你的东西 |
|---|---|
| L4 只是每批新闻一个 JSON，L2 用 `archive_path` 指向整个批次 | `memory/L4_archive/news.jsonl` 单行归档 + `archive_ref = 文件#事件ID` 精确到**一条**新闻，任何一条 L2 边都能一键还原原文 |
| L1 还不存在，Prompt 里只有“宁德时代” | `l1_router.py` + `memory/L1_concept_index.json`：14 只标的 → 命中簇的 3~5 只，Prompt token 降 40%+ |
| 只有被动抽取，没有“运动器官” | `agent.py`：感知→路由→回忆→推演→写回→L3 复盘→决策卡，7 个工具可解释地串起来 |
| 演示只能看 Neo4j 网页 | `app.py`：左输入 / 中 pyvis 图谱（利好红、利空绿、证伪灰虚线）/ 右结论 + CAR |

---

## 1. 架构

```
                    ┌─────────────────────────────────────────────┐
   新闻 / 公告 ───▶ │ L1 路由：概念词典 → 候选标的（0 token）        │
                    └───────────────┬─────────────────────────────┘
                                    ▼
                    ┌─────────────────────────────────────────────┐
                    │ L0 元规则（Prompt 层）+ 白名单校验（代码层）    │
                    └───────────────┬─────────────────────────────┘
                                    ▼
        ┌───────────────────────────────────────────────────────────┐
        │ L2 逻辑图谱（Neo4j / 本地 JSON 双后端）                     │
        │   公司 -[利好事件/利空事件 {status, confidence, date}]-> 公司 │
        │        每条边带 archive_ref ─────────────┐                 │
        └───────────────────────────────┬──────────┼─────────────────┘
                                        │          ▼
                    ┌───────────────────▼───┐  ┌──────────────────────────┐
                    │ L3 技能：事件研究 CAR  │  │ L4 归档：news.jsonl（原文）│
                    └───────────────────┬───┘  └──────────────────────────┘
                                        ▼
                             决策卡：方向 / 动作 / 证据链
```

**记忆分层职责**

| 层 | 内容 | 存储 | 何时读 |
|---|---|---|---|
| L0 | 6 条元规则（时间隔离、无证据不入图、按需展开、本体约束、噪音过滤、状态机） | `l0_rules.py` | 每次抽取常驻 |
| L1 | 概念簇 → 标的映射（4 簇 14 只） | `memory/L1_concept_index.json` | 每条新闻先过 |
| L2 | 投资逻辑图谱（含状态机：发酵中/已被证伪/已兑现） | Neo4j 或 `data/local_graph.json` | 推理与可视化 |
| L3 | 可复用“技能”：事件研究、CAR、结论一致性检验 | `l3_event_study.py` | 结论落地时 |
| L4 | 原始新闻全文（append-only） | `memory/L4_archive/news.jsonl` | 点“查看原文”时 |

---

## 2. 快速开始

```powershell
cd modules\l0l4-memory
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\setup_vscode.ps1   # 终端固定到项目根目录
python setup_env.py         # 一条命令：装依赖 + 写 .env + 测 Neo4j + 灌数据 + 跑测试
streamlit run app.py
```

手动版（脚本失败时）：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # 填入 DeepSeek / Neo4j 凭据
python -m unittest discover -s tests -v      # 25 个离线用例应全绿
streamlit run app.py
```

没配 Neo4j 也能跑：`MEMKG_STORE=auto` 时若无连接信息，自动落到 `data/local_graph.json`，
答辩现场断网也不会白屏（右上角会标注“本地 JSON 兜底”）。

把旧数据接进来（一次性）：

```python
import l4_archive as l4
from pathlib import Path
for p in Path("archive/news").glob("*.json"):
    l4.import_legacy_batch(p)      # 幂等，重复跑不会重复归档
```

### 接入真实数据

```powershell
# 先空跑，看看今天能抓到什么、会被 L1 路由到哪几只票（不写库）
python fetch_real.py --codes 300750,002466 --limit 10 --dry-run

# 正式入库：抓新闻 + 抓日线 + L1 路由 + L2 抽取/合并/证伪 + L4 归档
python fetch_real.py --watchlist --limit 6 --llm

# 单独跑"每日任务"（会额外生成 reports/daily_YYYY-MM-DD.md）
python daily_job.py --watchlist --limit 6 --llm
```

真实新闻的典型结果：**10 条新闻 → 5 条被 L0 判为行情快照/无关而过滤 → 4 条三季报合并成 1 条边（`n_evidence=3`）**。
这正是"以存代算"要展示的降噪比。

### 每日自动跑（Windows 任务计划程序，最轻量）

```powershell
schtasks /Create /TN "FinMemKG_Daily" /F /SC DAILY /ST 08:30 ^
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\28968\知识图谱\scheduler\run_daily.ps1"
schtasks /Run /TN "FinMemKG_Daily"      # 立刻跑一次验证
schtasks /Query /TN "FinMemKG_Daily" /V /FO LIST
```

日志在 `logs/daily_*.log`，自动保留最近 30 份。
不需要常驻进程、不装 APScheduler；电脑关机那天的任务会在下次开机后补跑一次。

---

## 3. 三个演示场景（答辩直接照着点）

| 按钮 | 新闻 | 期望现象 | 讲解点 |
|---|---|---|---|
| **A 逻辑反转** | 监管未通过，暂停对上海时代宸远的 4 亿投资 | 原“利好事件”变灰色虚线并标注`已被证伪`，同时新增绿色“利空事件” | 记忆不是 append，而是**有状态的知识更新** |
| **B 竞争替代** | 特斯拉把订单转给比亚迪 | 宁德→特斯拉 利好被证伪，整体方向由偏多翻为**偏空** | 跨公司传导 + 反转惩罚改变结论 |
| **C 产业链传导** | 碳酸锂涨停、锂矿收紧 | 上游（天齐/赣锋）利好、下游（宁德/亿纬）利空，图上出现两跳路径 | 多跳推理：`天齐-供应商->宁德` 让传导可解释 |

每个场景都可切换「大模型」/「规则引擎（0 Token）」：后者完全离线、确定性复现，
**UI 会明确标注**“本次由规则引擎产出”，不会把规则结果冒充成模型结果。

---

## 4. 四个关键设计（写报告时的“创新点”）

### 4.1 L4 指针协议：`archive_ref = 相对路径#事件ID`

```text
memory/L4_archive/news.jsonl#EV-20261022-db9c2ac7
```

* `EV-<日期>-<内容 sha1 前 8 位>`：**内容寻址**，同一条新闻重复抓取不会重复入库；
* 一条新闻抽出多个三元组时，边 ID 为 `EV-…-01`、`EV-…-02`，共享同一个 `archive_ref`；
* `l4_archive.resolve(ref)` 是唯一的读取入口，UI/报告/评测都走它，避免“指针指向整个批次”的模糊。

**可量化指标**：`archive_ref 非空率 = 100%`（写入前 `commit()` 强制绑定，L0-2 的代码级落实）。

### 4.2 L1 路由：词典匹配，0 token，可解释

`route(text)` 输出：命中概念簇、命中别名、候选标的、`full_tokens_est / routed_tokens_est / saved_pct`。
在 14 只标的的池子上，锂矿类新闻 `321 → 182 token`（-43%）；池子越大，
每多一只标的只增加 L1 词典命中概率、不增加常驻 Prompt，节省比例近似线性上升（可外推写进报告）。

### 4.3 L0 的两层执行

* Prompt 层：`OUTPUT_CONTRACT` 明确实体/关系白名单、数字不入节点、噪音返回空；
* 代码层：`store.upsert_event()` 在写库前再校验一次，越界直接 `ValueError`，
  `pipeline.validate_events()` 把被拦截的条目放进 `rejected`，UI 可展开查看 —— **“模型说错话也写不进图”**。

### 4.4 反转惩罚（Reversal Penalty）

```python
score = Σ 活跃边(极性 × 置信度) − 0.5 × Σ 被证伪边(极性 × 置信度)
```

被推翻的旧逻辑会削弱它原本支持的方向。场景 A 中：
`+0.88(特斯拉合同) −0.55(新利空) −0.36(被证伪的投资利好 0.72×0.5) ≈ −0.03 → 中性`；
场景 B 中特斯拉合同本身被证伪：`+0.72(投资利好) −0.55(新利空) −0.44(被证伪的 0.88×0.5) ≈ −0.27 → 偏空`。
这比“简单数利好利空条数”更接近研究员的真实判断，也是你答辩时能讲清楚的“为什么结论会翻转”。

---

## 5. 对照课程要求（选题 5 基础功能）

| 课程要求 | 本包实现 | 证据 |
|---|---|---|
| 收集公告/财务/行业/新闻/行情 | AkShare（新闻 + 个股 + 指数） | `demo_graph.py` 原有能力 + `l3_event_study.load_prices` |
| 抽取公司/行业/产品/供应商/客户/竞争对手/事件 | L0 白名单 6 类关系 | `config.REL_TYPES`、`l0_rules.py` |
| 构建公司—行业—产业链—事件—时间网络 | 行业节点 + `属于行业` + `供应商` + 时间属性 | `demo_data.py`、`store.py` |
| 跨公司/跨行业查询与产业链追踪 | 一跳子图 + 两跳传导（场景 C） | `store.subgraph(hops=2)`、`pipeline` |
| 事件与行情/财务关联展示 | L3 事件研究 CAR + 逐日表 | `l3_event_study.py` |
| 关系网络 / 事件时间线 / 情报可视化 | pyvis 交互图 + Mermaid 静态图 + Agent 轨迹 | `viz.py`、`app.py` |

PDF 里点名要“避免未来信息泄露”“信息可信度”“可解释影响路径”，对应实现：
事件日 `date` 与抓取日分离（L0-1）、`confidence` 字段、`archive_ref` 证据链、Agent 轨迹面板。

---

## 6. 报告提纲（对齐 PDF 的章节要求，≥5000 字）

1. **摘要**：一句话问题（海量新闻 → 可回溯、可更新的投资逻辑记忆）+ 三个数字（token 降幅、证伪条数、CAR）。
2. **引言**：LLM/RAG 的三个缺陷（无状态、不可回溯、多跳弱），引出分层记忆。
3. **数据集与 KG 构造**：AkShare 抓取范围、L1 词典、本体（4 实体 6 关系）、L2 Schema、L4 归档格式。
4. **任务定义**：给定新闻流，输出 (主语, 关系, 宾语, 状态, 证据指针)；下游任务=方向判断 + CAR 检验。
5. **方法**：L0–L4 各层算法；状态机与反转惩罚；L1 路由的匹配与降噪。
6. **实验（抽取）**：人工标 30~50 条新闻的三元组，报 P/R/F1；对比（a）无 L0 提示（b）L0 提示（c）L0+L1 路由；同时报 token 成本。
7. **原型系统**：三栏界面截图、三个场景、一次完整的 Agent 轨迹。
8. **实验（下游）**：事件窗口 CAR；对比“直接问 LLM 看多/看空”与“本系统”的方向准确率；消融 L1、L4。
9. **结论与局限**：样本小、单模型、CAR 窗口未走完、规则引擎≠模型能力。
10. **参考文献 / 人员分工 / 组内互评**。

---

## 7. 目录

```
config.py            # 唯一配置源 + L0 白名单常量
market_bridge.py     # 数据层融合：优先读队友的本地行情快照（parquet），否则回落 AkShare
l0_rules.py          # 6 条元规则 + 输出契约 + Prompt 片段
l1_router.py         # 概念路由（0 token）
l4_archive.py        # JSONL 归档 + archive_ref 协议 + 旧数据导入
store.py             # L2 双后端（Neo4j / 本地 JSON）+ 同向合并/反向证伪
demo_data.py         # 演示图谱 + 三个场景
pipeline.py          # 抽取 → 校验 → 对账（反转/合并）→ 写库 → 结论
fetch_real.py        # 真实数据接入：AkShare 新闻 + 日线 → L1 → L2 → L4
daily_job.py         # 每日增量任务 + 自动生成日报
demo_graph.py        # 修复版：抓取入库入口（替代你原来的脚本）
update_logic.py      # 修复版：反转演示入口（替代你原来的脚本）
l3_event_study.py    # 市场模型 CAR（akshare / 缓存 / 模拟三级回退）
viz.py               # pyvis HTML + Mermaid
agent.py             # 运动器官：7 个工具的行动闭环
app.py               # Streamlit 三栏大屏
scheduler/run_daily.ps1   # 任务计划程序调用的入口
docs/报告写作包.md         # 学术说辞 + 摘要/引言模板 + PPT 大纲 + Q&A
memory/L1_concept_index.json
tests/test_offline.py
```

---

## 8. 已知局限（写进报告反而加分）

* 规则引擎只是**兜底**，不能当作模型能力证据；
* L1 词典覆盖 4 个簇 14 只标的，泛化性有限，冷启动需要人工维护；
* 事件研究用日频、市场模型，未做稳健性检验（可补 BMP 检验 / 不同窗口）；
* Neo4j 免费版实例在演示高峰期可能超时，已做本地兜底；
* `date` 若直接用抓取时间会引入前视偏差，务必用新闻发布日。
