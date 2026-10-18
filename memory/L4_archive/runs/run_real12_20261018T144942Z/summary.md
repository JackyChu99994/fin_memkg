# Fin-MemKG 真实大模型评测报告 (`run_real12_20261018T144942Z`)

## 1. 评测运行元数据 (Run Manifest)
- **评测模式 (`evaluation_mode`)**: `LIVE_LLM_BENCHMARK`
- **运行 ID (`run_id`)**: `run_real12_20261018T144942Z`
- **时间戳 (`timestamp`)**: `20261018T144942Z`
- **数据集 (`dataset`)**: `real12` (样本数 `N = 12`)
- **各场景样本分布 (`scenario_counts`)**: `TEMPORAL_REVERSAL=6`, `PRICED_IN_TRAP=3`, `SECTOR_CONTAGION=3`
- **底座模型 (`model_name`)**: `qwen-plus`
- **接口地址 (`base_url`)**: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- **生成参数**: `temperature=0.0`, `max_tokens=2600 (retry=4096)`, `timeout=60.0s`, `max_retries=1`
- **三分类阈值说明**: `car_5d_pct >= +1.5% -> BULLISH`, `<= -1.5% -> BEARISH`, 其余为 `NEUTRAL`；B0 动量基线采用 20 日涨跌幅 `±3.0%` 阈值。

## 2. 主实验与正交消融结果表

| Method | Valid/Failed | T+5 Acc (95% CI) | Macro-F1 | Node Inv/PI F1 | Avg CAR Traded (仅有仓位) | Avg CAR All (NEUTRAL=0) | Long-Short CAR (95% CI) | Avg Tokens | Avg Latency (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| B0: 20-Day Price Momentum Baseline (±3% Threshold, 0-Token) | 12/0 | 33.3% ([8.3%, 58.3%]) | 24.8% | 0.0% | -2.58% | -1.93% | +0.45% ([-3.43%, +4.71%]) | 0 | 0 |
| B1: Long-History Context + LLM (Full-Text) | 12/0 | 66.7% ([41.7%, 91.7%]) | 45.2% | 75.0% | +2.46% | +2.05% | +3.55% ([+0.28%, +6.54%]) | 2349 | 18310 |
| B2: Lexical Top-K Retrieval + LLM (Char-Bigram Top-3) | 12/0 | 58.3% ([33.3%, 83.3%]) | 40.3% | 91.7% | +4.52% | +3.02% | +3.60% ([+0.83%, +6.50%]) | 2347 | 18353 |
| B2+Prior: Lexical Top-K + Supply-Chain Text Prior + LLM (Top-3) | 12/0 | 58.3% ([33.3%, 83.3%]) | 38.1% | 75.0% | +3.51% | +2.63% | +3.21% ([+0.05%, +6.19%]) | 2621 | 17968 |
| Ablation A: w/o Invalidation Only | 12/0 | 75.0% ([50.0%, 100.0%]) | 55.6% | 66.7% | +2.17% | +1.63% | +6.14% ([+3.57%, +8.95%]) | 3763 | 17993 |
| Ablation B: w/o Priced-in Only | 12/0 | 83.3% ([58.3%, 100.0%]) | 57.4% | 78.3% | +0.64% | +0.59% | +6.02% ([+2.94%, +9.04%]) | 3694 | 16666 |
| Ablation C1: w/o Supply-Chain Prior & KG Edges (Node-Only) | 12/0 | 91.7% ([75.0%, 100.0%]) | 63.6% | 100.0% | +0.72% | +0.66% | +7.10% ([+5.00%, +9.43%]) | 3462 | 15375 |
| Ablation C2: 1-Hop KG Only (cutoff=1) | 12/0 | 83.3% ([58.3%, 100.0%]) | 60.0% | 100.0% | +1.35% | +1.12% | +6.65% ([+4.27%, +9.21%]) | 3508 | 16217 |
| Ours: Fin-MemKG (Full: Revision + PricedIn + 2-Hop KG) | 12/0 | 83.3% ([58.3%, 100.0%]) | 60.0% | 100.0% | +1.35% | +1.12% | +6.65% ([+4.27%, +9.21%]) | 3630 | 15865 |

> **统计与指标口径说明**：
> 1. `Avg CAR Traded (仅统计有方向仓位的案例)`：仅对模型预测为 `BULLISH` 或 `BEARISH` 的有方向仓位案例求标的原始 `car_5d_pct` 均值；`Avg CAR All (NEUTRAL=0)`：对全部 `N = 12` 个案例求均值（`NEUTRAL` 空仓计为 `0.0%`）；`Long-Short CAR`：`BULLISH` 做多（`+car_5d_pct`）、`BEARISH` 做空（`-car_5d_pct`）、`NEUTRAL` 空仓（`0.0%`）的全样本多空组合均值。
> 2. 表中 95% 置信区间由案例级 Bootstrap（`B = 1000` 次重采样，`seed = 42`）计算。由于当前评测样本量较小（`N = 12`），置信区间较宽，**本报告仅用于机制与经济含义对比，不宣称统计显著（not statistically significant）**。

## 3. 分场景准确率明细 (%)

| Method | TEMPORAL_REVERSAL (n=6) | PRICED_IN_TRAP (n=3) | SECTOR_CONTAGION (n=3) |
| :--- | :---: | :---: | :---: |
| B0: 20-Day Price Momentum Baseline (±3% Threshold, 0-Token) | 50.0% | 0.0% | 33.3% |
| B1: Long-History Context + LLM (Full-Text) | 66.7% | 33.3% | 100.0% |
| B2: Lexical Top-K Retrieval + LLM (Char-Bigram Top-3) | 66.7% | 0.0% | 100.0% |
| B2+Prior: Lexical Top-K + Supply-Chain Text Prior + LLM (Top-3) | 66.7% | 0.0% | 100.0% |
| Ablation A: w/o Invalidation Only | 100.0% | 0.0% | 100.0% |
| Ablation B: w/o Priced-in Only | 100.0% | 33.3% | 100.0% |
| Ablation C1: w/o Supply-Chain Prior & KG Edges (Node-Only) | 100.0% | 66.7% | 100.0% |
| Ablation C2: 1-Hop KG Only (cutoff=1) | 100.0% | 33.3% | 100.0% |
| Ours: Fin-MemKG (Full: Revision + PricedIn + 2-Hop KG) | 100.0% | 33.3% | 100.0% |

## 4. 规则机制自检 (`RULE_MECHANISM_SIMULATION`) vs 真实 LLM 评测 (`LIVE_LLM_BENCHMARK`)

1. **规则机制自检 (`RULE_MECHANISM_SIMULATION`)**：
   - 对应仓库中的静态历史文件 `memory/L4_archive/benchmark_results.json` 与 `memory/L4_archive/eval_results.csv`（其中 `inference_mode` 标注为 `HEURISTIC_FALLBACK`）。
   - 其作用仅为在无 API Key 环境下对图谱状态机算子（`INVALIDATE` / `PRICED_IN` / `ADD_NODE`）与符号传播公式进行确定性软件单测自检，**绝不能作为大模型知识图谱增益的实验证据**。
2. **真实 LLM 评测 (`LIVE_LLM_BENCHMARK`)**：
   - 对应本目录 `memory/L4_archive/runs/run_real12_20261018T144942Z/` 下的 `run_manifest.json`、`records.jsonl`、`summary.json` 与 `summary.md`。
   - 所有 LLM 方法（`B1`、`B2`、`B2+Prior`、`Ours` 及其消融变体）均真实调用同一底座模型（`qwen-plus`），遇到 API 错误直接记录为 `FAILED`（绝不降级至启发式规则），并增设 0-Token 动量基线 `B0` 作为客观参照。
   - **严禁将规则机制自检数字与真实 LLM 评测结果混用**。
