# RealFin-12 真实 LLM 评测结果（2026-10-18）

> 运行 ID：`run_real12_20261018T144942Z`
> 数据：`memory/L4_archive/real_fin_events_12.json`（N=12：6 反转 / 3 利好出尽 / 3 两跳传导）
> 模型：`qwen-plus`，`temperature=0`，`max_tokens=2600`（重试 4096）
> 调用：108 条记录 = 96 次 LIVE_API_CALL + 12 条 0-Token B0；**0 失败、0 截断、0 HEURISTIC_FALLBACK**
> 归档：`memory/L4_archive/runs/run_real12_20261018T144942Z/`

> **先看结论：Ours 明显优于文本基线 B1/B2；但与 Node-Only C1 的差异在 3 次重复后消失（majority 均为 83.3%，12/12 平），单次 91.7% vs 83.3% 是采样噪声。2 跳边在当前 12 例上既不能证明有益，也不能证明有害。N=12，不宣称统计显著。**

## 1. 主结果

| 方法 | T+5 Acc | Macro-F1 | Node F1 | Long-Short CAR | Avg Tokens | Avg Latency |
|---|---:|---:|---:|---:|---:|---:|
| B0 20 日动量 | 33.3% | 24.8% | 0.0% | +0.45% | 0 | 0 |
| B1 全文本 + LLM | 66.7% | 45.2% | 75.0% | +3.55% | 2,349 | 18.3s |
| B2 Top-3 + LLM | 58.3% | 40.3% | 91.7% | +3.60% | 2,347 | 18.4s |
| B2+Prior 产业链文本先验 | 58.3% | 38.1% | 75.0% | +3.21% | 2,621 | 18.0s |
| Ablation A 禁用 INVALIDATE | 75.0% | 55.6% | 66.7% | +6.14% | 3,763 | 18.0s |
| Ablation B 禁用 PRICED_IN | 83.3% | 57.4% | 78.3% | +6.02% | 3,694 | 16.7s |
| **Ablation C1 Node-Only** | **91.7%** | **63.6%** | **100.0%** | **+7.10%** | 3,462 | 15.4s |
| Ablation C2 1-Hop | 83.3% | 60.0% | 100.0% | +6.65% | 3,508 | 16.2s |
| **Ours Full 2-Hop** | **83.3%** | **60.0%** | **100.0%** | **+6.65%** | 3,630 | 15.9s |

## 2. 分场景

| 方法 | 反转（n=6） | 利好出尽（n=3） | 两跳传导（n=3） |
|---|---:|---:|---:|
| B0 | 50.0% | 0.0% | 33.3% |
| B1 | 66.7% | 33.3% | 100.0% |
| B2 | 66.7% | 0.0% | 100.0% |
| Ablation A | 100.0% | 0.0% | 100.0% |
| Ablation B | 100.0% | 33.3% | 100.0% |
| **Ablation C1** | **100.0%** | **66.7%** | **100.0%** |
| Ablation C2 | 100.0% | 33.3% | 100.0% |
| **Ours** | **100.0%** | **33.3%** | **100.0%** |

**最弱的是 PRICED_IN_TRAP：单次运行 Ours 只有 1/3，C1 有 2/3。** 但 REAL_09 的差异在重复实验中被证明是模型非确定性（见 3.1），不能据此说“边把 C1 的 BEARISH 拖成了 NEUTRAL”。

## 3. Paired 对比（同 case，exact McNemar）

| 对比 | Ours 赢/输/平 | p | Δ Long-Short CAR（bootstrap 95% CI） |
|---|---:|---:|---:|
| vs B0 | 6 / 0 / 6 | **0.031** | +6.19% [+3.12, +9.60] |
| vs B1 | 3 / 1 / 8 | 0.625 | +3.09% [+0.09, +6.58] |
| vs B2 | 3 / 0 / 9 | 0.250 | +3.05% [+0.58, +5.90] |
| vs B2+Prior | 3 / 0 / 9 | 0.250 | +3.43% [+0.65, +6.56] |
| vs Ablation A | 1 / 0 / 11 | 1.000 | +0.50% [+0.00, +1.51] |
| vs Ablation B | 1 / 1 / 10 | 1.000 | +0.62% [-0.92, +2.24] |
| vs Ablation C1 | **0 / 1 / 11** | 1.000 | **-0.46% [-1.38, +0.00]** |
| vs Ablation C2 | 0 / 0 / 12 | 1.000 | +0.00% |

解读：

- **对 B0 动量基线**：Ours 6 胜 0 负，p=0.031；这是目前唯一在配对检验下“看起来显著”的对比。
- **对 B1/B2 文本基线**：Ours 分别 3/1、3/0，方向准确率高 16.6/25.0 个百分点，CAR 高约 3 个百分点；但 N=12，McNemar 不显著，只能写“描述性优于”。
- **对 C1 Node-Only**：单次 0 胜 1 负，但 3 次重复后 majority 均为 83.3%、12/12 平；**单次差异是采样噪声，不是边因果。**
- **对 C2 1-Hop**：完全相同（12 平），2 跳 vs 1 跳在 12 例上没有差别。

### 3.1 关键修正：Ours vs C1 的差异不是边造成的

`temperature=0` 并不保证完全确定。对比 `Ours` 与 `Ablation C1` 的完整 prompt：

| 项目 | 数值 |
|---|---:|
| prompt 完全相同（system + user） | **7 / 12** |
| prompt 相同但预测不同 | **1 / 12（REAL_09）** |
| prompt 不同（有 2 跳路径） | 5 / 12 |
| prompt 不同但预测不同 | **0 / 12** |

也就是说：

- 在有 2 跳路径的 5 个 case（REAL_01/03/05/07/11）上，Ours 和 C1 的**预测完全相同**；
- 在 7 个没有路径的 case 上，prompt 完全相同；唯一不同的是 REAL_09，而这是模型自己波动；
- 对 REAL_09 单独重复 3 次：

| 方法 | 3 次结果 |
|---|---|
| Ours | BEARISH / BEARISH / NEUTRAL |
| C1 | NEUTRAL / NEUTRAL / NEUTRAL |

全量单次运行恰好是 Ours NEUTRAL、C1 BEARISH，所以 C1 多对一例、总分 91.7% vs 83.3%。这不是边的因果效应，而是 **单次采样噪声**。

**正确结论：**

> 在 RealFin-12 上，2 跳边没有改变任何预测；Full 2-Hop 与 Node-Only 的差异是单次采样噪声。要判断边是否有用，必须做 **多次重复 + 多数投票/均值**，而不是一次运行。

### 3.2 3 次重复稳定性检查（`stability_real12_20261018T152511Z`）

对 Ours 与 C1 各跑 3 次（2 × 12 × 3 = 72 次真实调用，0 失败）：

| 方法 | 三次准确率 | 均值 ± 标准差 | 多数投票准确率 | 平均 Tokens |
|---|---|---|---:|---:|
| Ours | 91.7% / 83.3% / 91.7% | **88.9% ± 4.0** | **83.3%** | 3,642 |
| C1 Node-Only | 83.3% / 83.3% / 91.7% | **86.1% ± 4.0** | **83.3%** | 3,433 |

- Ours vs C1 的 majority 对比：**0 胜 / 0 负 / 12 平**。
- 两个方法的 majority 错误都集中在 REAL_02（三季报预增）和 REAL_09（国庆动销），与单次全量运行一致。
- **结论：Full 2-Hop 与 Node-Only 在 12 例上没有可测差异；单次 C1 91.7% 是运气，不是边有害。**
- Ours 的均值 88.9% 略高于 C1 的 86.1%，差异在 ±4.0 的波动范围内，不能当增益。

## 4. 逐例观察

| Case | GT | CAR | Ours | 关键差异 |
|---|---|---|---:|---|
| REAL_01 Blackwell 推迟 | BEARISH | -7.84% | BEARISH | 正确 INVALIDATE；B1/B2 都 NEUTRAL |
| REAL_02 三季报预增 | BEARISH | -6.93% | NEUTRAL | PRICED_IN 命中；B1/B2 BULLISH；C1 也 NEUTRAL |
| REAL_03 DeepSeek 冲击 | BEARISH | -15.75% | BEARISH | 正确 INVALIDATE；B1/B2 NEUTRAL |
| REAL_04 新易盛三季报 | BEARISH | -6.05% | BEARISH | 正确 PRICED_IN；B1 BULLISH、B2 NEUTRAL |
| REAL_05 EML 扩产 | BULLISH | +7.53% | BULLISH | 全部方法大多正确 |
| REAL_06 新易盛预增 | BULLISH | +10.35% | BULLISH | 全部 LLM 方法正确 |
| REAL_07 茅台批价急跌 | BEARISH | -3.50% | BEARISH | 正确；B0/Abl-A 错 |
| REAL_08 茅台半年报+分红 | BULLISH | +2.43% | BULLISH | 正确 |
| REAL_09 国庆动销符合预期 | BEARISH | -5.50% | **单次 NEUTRAL** | 单次 Ours NEUTRAL / C1 BEARISH；重复 3 次 Ours 2/3 BEARISH、C1 3/3 NEUTRAL → **模型不稳定，不是边因果** |
| REAL_10 比亚迪 DM5.0 | BULLISH | +8.95% | BULLISH | 正确 |
| REAL_11 锂矿放量+比亚迪销量 | BULLISH | +7.75% | BULLISH | 正确 |
| REAL_12 天神之眼 | BULLISH | +9.60% | BULLISH | 正确 |

## 5. 必须写进报告的局限

1. **N=12，且只有 4 只股票**，置信区间很宽；不宣称统计显著。
2. **B1 不是长上下文压力测试**：real12 每个 case 只有 3 条 `prior_chunks`，B1 与 B2 看到的文档几乎相同；如果要回答老师“大量信息”的质疑，需要另做 20–50 条干扰文档的 B1-Long 压力集。
3. **单模型、单温度、单次运行**：`qwen-plus`, `temperature=0`，未做多模型/多种子；REAL_09 与 3 次稳定性检查都证明单次运行不可靠。
4. **C1 与 Ours 的差异不能当因果结论**：prompt 相同 7/12，有路径的 5/12 预测完全相同；3 次重复后 majority 均为 83.3%、12/12 平。**不能写“边有害”，也不能写“边有益”；当前只能写“未被验证”。**
5. **PRICED_IN_TRAP 仍然是弱项**：单次 Ours 1/3；3 次重复后 majority 错误仍集中在 REAL_02/09。这是下一步最该补的场景。

## 6. 对期中/期末的讲法

- 可以讲：“结构化论点记忆 + L3 Priced-in 相对文本基线有描述性增益：83.3% vs 66.7%/58.3%，CAR +6.65% vs +3.55%/+3.60%。”
- 必须同时讲：“3 次重复后 Ours 均值 88.9%±4.0，C1 86.1%±4.0，majority 都是 83.3%，12/12 平；单次 91.7% vs 83.3% 是采样噪声。当前 2 跳边既不能证明有益，也不能证明有害。”
- 不要把 2 跳边说成“已验证的增益”；也不要把单次 C1 高分说成“边有害”。
- 下一步：REAL_02/09 的 PRICED_IN 分析、扩大重复次数、边触发条件/边质量、B1-Long 压力集、更多事件与多模型。

## 7. 复现

```bash
.venv/bin/python -m eval_benchmark --dataset real12 --limit 0 --no-cache
.venv/bin/python scripts/analyze_run.py memory/L4_archive/runs/run_real12_20261018T144942Z
```

原始记录：`memory/L4_archive/runs/run_real12_20261018T144942Z/records.jsonl`
