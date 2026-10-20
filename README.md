# Fin-MemKG · Qwen 动态金融知识图谱与投资论点记忆更新工作台

本项目固定使用阿里云 DashScope 提供的 **Qwen OpenAI 兼容 Chat Completions 接口**，完成面向金融事件的**单事件结构化要素抽取 + L2 多空论点状态机更新 + L3 经验分位校准 + 两跳三节点产业链传导**推演演示与同底座真实大模型评测。

## 1. 安装依赖

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```powershell
# Windows
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> 依赖已锁定 `pandas>=2.1.0,<3.0`；`pandas 3.x` 的 Arrow 字符串后端会导致 `akshare.stock_news_em` 报 `ArrowInvalid`。新增的 `pyarrow` 用于本地行情快照（`market_snapshot.py`）。

## 2. 配置 Qwen 环境变量

系统仅读取以下三个配置项（读取顺序：**1. 系统环境变量 $\to$ 2. 项目根目录 `.env` 文件**）：

- `QWEN_API_KEY`（必填）
- `QWEN_BASE_URL`（可选，默认：`https://dashscope.aliyuncs.com/compatible-mode/v1`）
- `QWEN_MODEL`（可选，默认：`qwen-plus`）

可在系统环境变量中导出，或写入**项目根目录**的 `.env` 文件（不要提交到 Git）：

```ini
QWEN_API_KEY=你的_DashScope_API_Key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
```

> **注意**：当前版本不读取或推断 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`LLM_*`、`DEEPSEEK_*` 或 `OPENAI_WIRE_API`。

## 3. 启动工作台与运行测试

### 启动 Streamlit 交互式工作台

```bash
.venv/bin/streamlit run app.py
```

页面启动后会默认加载项目内置的固定金融事件与截至基准日的 L2 图谱快照（启动时不会自动发起任何 API 请求）。

### 运行全量离线单元测试

```bash
.venv/bin/python -m unittest discover -s tests -v
```

### 运行真实 API 连通性与三场景冒烟测试

```bash
# 单次最小连通性检查
.venv/bin/python scripts/check_api.py

# 三大预设场景（A 逻辑反转 / B 利好出尽 / C 两跳传导）真实 Qwen 端到端冒烟验证
.venv/bin/python scripts/smoke_demo.py
```

> Windows 下把 `.venv/bin/python` 换成 `.venv\Scripts\python.exe`；运行脚本前可设置 `PYTHONUTF8=1` 避免 GBK 解码问题。

## 4. 调用参数、重试策略与一次点击实际调用次数

1. **生成参数与超时上限**：
   - `SINGLE_MAX_TOKENS = 1200`（独立单事件分析函数上限）
   - `GRAPH_MAX_TOKENS = 2600`（统一图谱推演首次调用 `max_tokens`）
   - `GRAPH_MAX_TOKENS_RETRY = 4096`（触发截断或 JSON 解析重试时的扩容 `max_tokens`）
   - `LLM_TIMEOUT = 60.0`（单次请求超时时间 60 秒，`temperature = 0`）
2. **一次点击实际调用次数**：
   - 页面已将单事件结构化分析字段（`event_summary`、`entities`、`event_type`、`impact_direction`、`risk_level`、`event_confidence`）统一合并进 `InferenceResponse`。
   - 点击 **“📋 使用演示结果”**：**0 次**网络请求（使用内置确定性状态转移引擎，并明确标识 `当前为演示数据，未调用 Qwen API`）。
   - 点击 **“🚀 调用 Qwen API”**：
     - 命中本地缓存时：**0 次**网络请求；
     - 未命中缓存且首次输出完整时：**1 次**网络请求；
     - 触发可重试异常时：最多 **2 次**网络请求（首次请求 + 最多 1 次重试）。
3. **有限重试策略（截断 / 5xx / 超时可重试一次；401 / 403 / 404 不重试）**：
   - 当首次调用遇到 **输出被截断（`finish_reason == "length"`）**、**JSON 解析/契约校验失败**、**HTTP 5xx 网关异常** 或 **请求超时** 时，系统允许自动重试 **1 次**（总请求数 $\le 2$），重试时切换至 `GRAPH_MAX_TOKENS_RETRY = 4096` 并追加紧凑 JSON 字数约束（每条 `reason/reasoning` $\le 80$ 字、`patch_ops` $\le 3$ 条、`watch_indicators` $\le 3$ 条；5xx/超时前等待 1 秒）。
   - 当遇到 **HTTP 401（认证失败）、HTTP 403（权限拒绝）、HTTP 404（模型或地址不存在）** 或 **配置缺失** 时，**绝不重试**（`call_count = 1`），立即报错。

## 5. 失败不静默降级原则

- **绝不将 API 失败伪装成模型成功**：当 Qwen API 调用（含最多 1 次重试后）仍失败时，界面会立即清空上一次的成功结果（`last_res`），展示清楚的错误类型、原因与下一步提示，**绝不自动调用 `_heuristic_fallback()` 冒充真实大模型结果**。
- **审计元数据透明可见**：每次推演在 `ExecutionMeta` 与侧边栏审计徽章中明确记录 `finish_reason`、`retry_count` 与 `json_repaired`。

## 6. 规则机制自检 (`RULE_MECHANISM_SIMULATION`) vs 真实 LLM 评测 (`LIVE_LLM_BENCHMARK`)

详细评测协议、0-Token 动量基线 `B0`、三分类超额收益阈值（`car_5d_pct` $\pm 1.5\%$）、多空组合 CAR 与 Bootstrap 95% CI 说明请参阅 [EVALUATION.md](EVALUATION.md)：

- **规则机制自检 (`RULE_MECHANISM_SIMULATION`)**：对应 `memory/L4_archive/benchmark_results.json` 与 `eval_results.csv`（`inference_mode="HEURISTIC_FALLBACK"`），仅用于离线校验状态机算子代码逻辑，**不作为大模型知识图谱增益证据**。
- **真实 LLM 评测 (`LIVE_LLM_BENCHMARK`)**：通过 `eval_benchmark.py` 执行，每次运行独立写入 `memory/L4_archive/runs/{run_id}/`（含 `run_manifest.json`、`records.jsonl`、`summary.json`、`summary.md`），所有 LLM 方法真实调用同一 `qwen-plus` 模型，失败计入 `failed_cases`。

## 7. 仓库结构（2026-10-18 合并后）

| 路径 | 作用 |
|---|---|
| `app.py` | KG 可视化 / 演示工作台（Streamlit） |
| `agent_loop.py` | KG 推演管线：单事件 + L2 patch + 统一 `InferenceResponse` |
| `tools.py` | L2/L4 读写、事件极性、两跳传导、行情三级回退、时间隔离 |
| `schema.py` / `prompts.py` | Pydantic 契约与 Prompt 模板 |
| `eval_benchmark.py` + `EVALUATION.md` | RealFin / 合成事件真实 LLM 评测 |
| `ga_core/` | GenericAgent 风格的通用 Agent 内核（工具循环、会话、记忆） |
| `market_snapshot.py` | 本地行情快照构建与读取（`data/market/` 已 gitignore） |
| `memory/L0..L4` | 元规则、索引、L2 图谱、L3 技能、L4 证据 |
| `tests/` | `unittest` + `pytest` 两套回归 |

## 8. 最新真实评测（2026-10-18，RealFin-12）

- 运行：`run_real12_20261018T144942Z`，108 条记录（96 次真实 API + 12 条 0-Token B0），**0 失败 / 0 截断 / 0 规则冒充**。
- 单次 T+5：**Ours 83.3%**，B1 66.7%，B2 58.3%，B0 33.3%；Long-Short CAR：**Ours +6.65%**，B1 +3.55%，B2 +3.60%，B0 +0.45%。
- **3 次重复稳定性**：Ours **88.9%±4.0 / majority 83.3%**；B1 **61.1%±4.0 / 58.3%**；B2 **61.1%±4.0 / 58.3%**。Ours 对 B1/B2 的 majority 对比均为 **3 胜 0 负 9 平**。
- **必须同时报告的消融结果**：Ours 对 C1 Node-Only 的 majority 是 **0 胜 0 负 12 平**；单次 C1 91.7% vs Ours 83.3% 是采样噪声。**2 跳边既不能证明有益，也不能证明有害。**
- 逐例 / 配对 McNemar / 稳定性分析：[docs/REAL12_RESULTS_2026-10-18.md](docs/REAL12_RESULTS_2026-10-18.md)

> 口径提醒：N=12、4 只股票、单模型单温度；不宣称统计显著。B1 在 `real12` 上每例只有 3 条历史文本，不是真正的长上下文压力测试；要回答“大量信息”问题，需另做 20–50 条干扰文档的 B1-Long 压力集。

## 9. 行情数据层与验收（2026-10-21）

本次按阶段成果交付，完成内容和剩余限制见 [阶段提交说明](docs/STAGE_DELIVERY.md)。完整操作、字段口径、历史数据限制见 [行情数据层交接](docs/STAGE3_HANDOFF.md)，任务范围见 [需求表](docs/STAGE3_REQUIREMENTS.md)，本机真实结果见 [验收摘要](docs/stage3/acceptance.json)。

- 日线支持区间续传、历史上市过滤、完整快照原子发布、默认离线及显式限时补采。
- 本机两只样本实测可获取新浪/腾讯近期 30 分钟线；task_36 的 2024 年历史范围不可得时，使用明确标注的官方允许日线近似。
- 细分行业保留来源和观察时间；历史查询不会静默把当前分类当作过去事实。
- task_01 固定 RSI14 与同日信号口径，官方自动评分与独立重算分别保存。
- 测试通过隔离副本运行，防止旧测试的假模型响应污染演示缓存。

```powershell
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe scripts/realfin_contract.py --fetch
.\.venv\Scripts\python.exe scripts/validate_task01.py
.\.venv\Scripts\python.exe scripts/validate_task36.py
.\.venv\Scripts\python.exe scripts/audit_stage3.py
.\.venv\Scripts\python.exe scripts/check_stage3.py
```

验收需要先有本地日线快照；分钟来源探测见交接文档。生成数据在 `data/market/`，不提交 Git。新版本数据应通过 `load_*` 或 `snapshot_paths()` 读取，根目录旧 Parquet 仅作兼容保留。

行情数据与验收功能也可以在网页操作：

```powershell
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

打开 `http://127.0.0.1:8501`，选择“行情数据与验收”，可浏览行情缓存、筛选行业映射、运行 task_01/task_36、查看历史记录并下载结果。网页运行记录保存在忽略目录 `data/market/web_runs/`；原图谱页面可从左侧“金融事件与图谱”进入。操作说明见 [交接文档第 7 节](docs/STAGE3_HANDOFF.md#7-网页使用)。
