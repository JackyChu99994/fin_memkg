# Fin-MemKG · Qwen 动态金融知识图谱与投资论点记忆更新工作台

本项目固定使用阿里云 DashScope 提供的 **Qwen OpenAI 兼容 Chat Completions 接口**，完成面向金融事件的**单事件结构化要素抽取 + L2 多空论点状态机更新 + L3 经验分位校准 + 两跳三节点产业链传导**推演演示与同底座真实大模型评测。

## 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 配置 Qwen 环境变量

系统仅读取以下三个配置项（读取顺序：**1. 系统环境变量 $\to$ 2. 项目根目录 `.env` 文件**）：

- `QWEN_API_KEY`（必填）
- `QWEN_BASE_URL`（可选，默认：`https://dashscope.aliyuncs.com/compatible-mode/v1`）
- `QWEN_MODEL`（可选，默认：`qwen-plus`）

可在系统环境变量中导出，或写入项目根目录 `/Users/huaijinchu/Desktop/fin_memkg/.env`：

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
