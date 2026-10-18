# Fin-MemKG 评测体系说明 (`EVALUATION.md`)

本文档说明 **Fin-MemKG** 仓库中两类评测模式的边界、指标定义、数据集上下文局限性、三分类阈值以及复现实验的标准流程。

## 1. 规则机制自检 (`RULE_MECHANISM_SIMULATION`) vs 真实 LLM 评测 (`LIVE_LLM_BENCHMARK`)

仓库中严格区分以下两类产物，**严禁将规则机制自检结果混同于真实大模型评测结果**：

| 维度 | 规则机制自检 (`RULE_MECHANISM_SIMULATION`) | 真实 LLM 评测 (`LIVE_LLM_BENCHMARK`) |
| :--- | :--- | :--- |
| **产物路径** | `memory/L4_archive/benchmark_results.json`<br>`memory/L4_archive/eval_results.csv` | `memory/L4_archive/runs/{run_id}/run_manifest.json`<br>`memory/L4_archive/runs/{run_id}/records.jsonl`<br>`memory/L4_archive/runs/{run_id}/summary.json`<br>`memory/L4_archive/runs/{run_id}/summary.md` |
| **推理引擎 (`inference_mode`)** | `HEURISTIC_FALLBACK`（确定性规则模拟） | `LLM_API`（真实调用 `qwen-plus`）+ `DETERMINISTIC_BASELINE`（仅限 0-Token 动量基线 `B0`） |
| **失败处理** | 无网络调用 | 严禁回退到启发式规则；API 失败（含重试 1 次后仍失败）如实计入 `failed_cases` |
| **用途定位** | 仅用于离线校验状态机算子（`INVALIDATE` / `PRICED_IN` / `ADD_NODE`）与符号传播公式的代码正确性 | 用于验证同一底座大模型下“知识图谱记忆（Ours）”相对于文本基线（`B1`/`B2`）、动量基线（`B0`）及消融变体的真实表现 |

## 2. 对比方法与基线定义（含 `real12` 上下文长度局限说明）

1. **`B0: 20-Day Price Momentum Baseline (±3% Threshold, 0-Token)`**：
   - 不调用大模型（`tokens = 0`，`inference_mode = "DETERMINISTIC_BASELINE"`）。
   - 仅根据事件前 20 日涨跌幅 `return_20d_pct` 判定：
     - `return_20d_pct >= +3.0%` $\to$ `BULLISH`
     - `return_20d_pct <= -3.0%` $\to$ `BEARISH`
     - `-3.0% < return_20d_pct < +3.0%` $\to$ `NEUTRAL`
2. **`B1: Long-History Context + LLM (Full-Text)`**：
   - 将去重并按 12,000 字符上限截断的历史文本全量输入给同一 `qwen-plus` 模型。
   - **重要局限说明（`real12` 下 `B1` 不是长上下文压力测试）**：在真实事件集 `RealFinEvent-12` (`real12`) 中，每个案例仅包含 **3 条** `prior_chunks`（总长约 230~260 字符），因此 `B1 (Full-Text)` 与 `B2 (Top-3)` 实际看到的 3 条历史文档内容几乎完全相同（仅排列顺序因词法相似度排序略有差异，Prompt Token 均约为 1,039 tokens）。因此，**在 `real12` 上 `B1` 并不能构成真正的长上下文噪声/截断压力测试**，仅代表“纯文本无图结构输入”的基线对照。
3. **`B2: Lexical Top-K Retrieval + LLM (Char-Bigram Top-3)`**：
   - 使用字符二元组余弦相似度检索 Top-3 历史片段输入给 `qwen-plus`（在 `real12` 的 3 条 `prior_chunks` 下与 `B1` 看到的文档集合相同）。
4. **`B2+Prior: Lexical Top-K + Supply-Chain Text Prior + LLM (Top-3)`**：
   - 在 `B2` 基础上附加同源产业链边的扁平文本描述，用于剥离“领域先验文本”与“图拓扑结构”各自的贡献。
5. **正交消融变体 (`Ablation A / B / C1 / C2`) 与完整方法 (`Ours`)**：
   - `Ablation A`: 禁用 `INVALIDATE`（w/o Invalidation Only）
   - `Ablation B`: 禁用 `PRICED_IN` 与分位折算（w/o Priced-in Only）
   - `Ablation C1`: 禁用图边与产业链传导（Node-Only，`max_hops=0, use_edges=False`）
   - `Ablation C2`: 仅允许一跳传导（`cutoff=1`）
   - `Ours`: 完整 Fin-MemKG（信念修正 + L3 Priced-in 校准 + 两跳三节点产业链传导）

## 3. 评测指标口径说明

1. **三分类超额收益阈值 (`CAR_3CLASS_THRESHOLD_PCT = 1.5%`)**：
   - 基于事件后 5 个交易日相对沪深 300 的累计超额收益 `car_5d_pct`：
     - `car_5d_pct >= +1.5%` $\to$ `BULLISH`
     - `car_5d_pct <= -1.5%` $\to$ `BEARISH`
     - `-1.5% < car_5d_pct < +1.5%` $\to$ `NEUTRAL`
   - `RealFinEvent-12` 中全部 12 个真实历史事件的 `|car_5d_pct|` 均 $\ge 2.43\%$，因此原有真实方向标签保持不变，同时评测代码原生支持 `NEUTRAL` 预测与三分类 Macro-F1。
2. **节点证伪/兑现定位 F1 (`Node Inv/PI F1`)**：
   - 核对模型输出的 `INVALIDATE` / `PRICED_IN` 目标节点 `pred_inv` 与真值节点 `gt_inv`：
     - 若 `pred_inv == gt_inv`（且非空），计 `TP += 1`；
     - 若预测了错误节点（`pred_inv is not None and pred_inv != gt_inv`），计 `FP += 1`，且当 `gt_inv is not None` 时同时计 `FN += 1`（既误杀错节点，又漏掉真值节点）；
     - 若未输出任何证伪/兑现节点（`pred_inv is None`）而 `gt_inv is not None`，计 `FN += 1`。
3. **CAR 均值口径区分 (`avg_car_traded_pct` vs `avg_car_all_pct` vs `long_short_car_pct`)**：
   - `avg_car_traded_pct`（仅统计有方向仓位的案例）：仅对模型预测为 `BULLISH` 或 `BEARISH` 的有仓位案例计算标的原始 `car_5d_pct` 均值；若全为空仓则为 `N/A`。
   - `avg_car_all_pct`（全样本均值，`NEUTRAL=0`）：对全部评测案例计算均值，预测为 `NEUTRAL` 或失败空仓的案例计为 `0.0%`。
   - `long_short_car_pct`（多空组合平均超额收益）：预测 `BULLISH` 做多（`+car_5d_pct`）、预测 `BEARISH` 做空（`-car_5d_pct`）、预测 `NEUTRAL` 空仓（`0.0%`）的全样本多空收益均值。
4. **分场景统计 (`by_scenario` 与 `scenario_counts`)**：
   - 显式输出当前评测样本在 `TEMPORAL_REVERSAL`、`PRICED_IN_TRAP`、`SECTOR_CONTAGION` 三个场景下的样本分布 `scenario_counts`；当某一场景在子集（如 `--limit 2`）中 `total == 0` 时，准确率输出为 `"N/A"`（绝不输出误导性的 `0.0%`）。
5. **Bootstrap 95% 置信区间 (`B = 1000`, `seed = 42`)**：
   - 对案例执行 1,000 次有放回重采样计算 `T+5 Acc` 与 `Long-Short CAR` 的 95% CI。小样本下置信区间较宽，**仅用于展示区间范围，不宣称统计显著**。

## 4. 标准运行顺序与离线重算命令

```bash
# Step a: 最小 API 连通性与 JSON 输出检查
.venv/bin/python scripts/check_api.py
.venv/bin/python -m eval_benchmark --check-only

# Step b: 2 例小规模真实 API Smoke 评测（强制在线调用 --no-cache）
.venv/bin/python -m eval_benchmark --dataset real12 --limit 2 --no-cache

# Step c: 不重跑 API，基于已有 records.jsonl 重新生成 summary.json 与 summary.md
.venv/bin/python -m eval_benchmark --recompute-run run_real12_20261018T144942Z

# Step d: 全量 12 例真实评测（约 108 条记录 / 96 次 API 调用）
.venv/bin/python -m eval_benchmark --dataset real12 --limit 0 --no-cache

# Step e: 按 case 与 paired 对比分析
.venv/bin/python scripts/analyze_run.py memory/L4_archive/runs/<run_id>
```

## 5. 最新一次真实评测（2026-10-18）

- `run_id`: `run_real12_20261018T144942Z`
- 108 条记录：96 次 `LIVE_API_CALL` + 12 条 `DETERMINISTIC_BASELINE`；**0 失败、0 截断、0 `HEURISTIC_FALLBACK`**
- 主结果（单次）：Ours **83.3%**，B1 **66.7%**，B2 **58.3%**，B0 **33.3%**；Long-Short CAR 分别 **+6.65% / +3.55% / +3.60% / +0.45%**
- **3 次重复稳定性**：Ours **88.9%±4.0 / majority 83.3%**；B1 **61.1%±4.0 / 58.3%**；B2 **61.1%±4.0 / 58.3%**。Ours 对 B1/B2 的 majority 对比均为 **3 胜 0 负 9 平**；结构化记忆的增益在重复下稳定。
- **关键消融结果**：Ours 对 C1 Node-Only 的 majority 是 **0 胜 0 负 12 平**；单次 C1 91.7% vs Ours 83.3% 是采样噪声。**当前不能声称“边有害”或“边有益”；2 跳边尚未被验证。**
- 逐例、配对 McNemar、失败案例分析见：[docs/REAL12_RESULTS_2026-10-18.md](docs/REAL12_RESULTS_2026-10-18.md)

