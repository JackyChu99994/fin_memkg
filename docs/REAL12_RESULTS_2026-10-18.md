# RealFin-12 真实 LLM 评测结果（2026-10-18）

> 运行 ID：`run_real12_20261018T144942Z`
> 数据：`memory/L4_archive/real_fin_events_12.json`（N=12：6 反转 / 3 利好出尽 / 3 两跳传导）
> 模型：`qwen-plus`，`temperature=0`，`max_tokens=2600`（重试 4096）
> 调用：108 条记录 = 96 次 LIVE_API_CALL + 12 条 0-Token B0；**0 失败、0 截断、0 HEURISTIC_FALLBACK**
> 归档：`memory/L4_archive/runs/run_real12_20261018T144942Z/`

> **先看结论：Ours 明显优于文本基线 B1/B2，但没有优于 Node-Only 消融 C1；2 跳边在当前 12 例上没有带来增益。N=12，不宣称统计显著。**

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

**最弱的是 PRICED_IN_TRAP：Ours 只有 1/3，而 C1 有 2/3。** 这说明“利好出尽”场景仍然靠 LLM 自己判断，图的边没有提供额外帮助，反而在 REAL_09 上把 C1 的 BEARISH 拖成了 NEUTRAL。

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
- **对 C1 Node-Only**：Ours 0 胜 1 负，C1 的 91.7% 高于 Ours 的 83.3%。**当前 2 跳边没有证明增益，甚至可能引入噪声。**
- **对 C2 1-Hop**：完全相同（12 平），2 跳 vs 1 跳在 12 例上没有差别。

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
| REAL_09 国庆动销符合预期 | BEARISH | -5.50% | **NEUTRAL** | **C1 正确 BEARISH；Ours 被边上下文拖成 NEUTRAL** |
| REAL_10 比亚迪 DM5.0 | BULLISH | +8.95% | BULLISH | 正确 |
| REAL_11 锂矿放量+比亚迪销量 | BULLISH | +7.75% | BULLISH | 正确 |
| REAL_12 天神之眼 | BULLISH | +9.60% | BULLISH | 正确 |

## 5. 必须写进报告的局限

1. **N=12，且只有 4 只股票**，置信区间很宽；不宣称统计显著。
2. **B1 不是长上下文压力测试**：real12 每个 case 只有 3 条 `prior_chunks`，B1 与 B2 看到的文档几乎相同；如果要回答老师“大量信息”的质疑，需要另做 20–50 条干扰文档的 B1-Long 压力集。
3. **单模型、单温度、单次运行**：`qwen-plus`, `temperature=0`，未做多模型/多种子。
4. **C1 优于 Ours**：这是当前最重要的负面结果。不要把它藏起来；它说明“边/2 跳”还不是有效增益，下一步要查边质量和触发条件。
5. **PRICED_IN_TRAP 只有 1/3**：这是最该补的场景；C1 的 2/3 说明不用边也能更好，问题可能在 Ours 的 prompt 或边上下文。

## 6. 对期中/期末的讲法

- 可以讲：“结构化论点记忆 + L3 Priced-in 相对文本基线有描述性增益：83.3% vs 66.7%/58.3%，CAR +6.65% vs +3.55%/+3.60%。”
- 必须同时讲：“Node-Only 消融 91.7% 高于 Full 2-Hop 83.3%，说明当前 2 跳边没有证明增益；这是下一步要解决的问题。”
- 不要把 2 跳边说成“已验证的增益”；老师最反感的就是把消融结果藏起来。
- 下一步：REAL_09 错误分析、边触发条件/边质量、B1-Long 压力集、更多事件与多模型。

## 7. 复现

```bash
.venv/bin/python -m eval_benchmark --dataset real12 --limit 0 --no-cache
.venv/bin/python scripts/analyze_run.py memory/L4_archive/runs/run_real12_20261018T144942Z
```

原始记录：`memory/L4_archive/runs/run_real12_20261018T144942Z/records.jsonl`
