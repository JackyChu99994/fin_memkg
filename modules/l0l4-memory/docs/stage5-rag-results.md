# Task two repeated RAG comparison results

State memory has lower majority accuracy than sparse RAG on this small development set. No memory benefit is demonstrated.

Protocol: `memory-comparison-v3`. Configured model: `qwen-plus`. Provider response model names: qwen-plus. There are 5 unique episodes and 3 repetitions.

References are mechanically derived from the forty user-reviewed extraction annotations. They are not five newly independent human annotations. This is evidence-sign consistency, not return prediction.

## Results

| Method | Accuracy by repeat | Mean +/- sample SD | Majority | Direction + required source IDs | Invalid citation IDs |
| --- | --- | --- | --- | --- | --- |
| Full text | 80.0%, 80.0%, 80.0% | 80.0% +/- 0.0% | 4/5 | 12/15 | 0 |
| Sparse TF-IDF RAG | 100.0%, 100.0%, 100.0% | 100.0% +/- 0.0% | 5/5 | 15/15 | 0 |
| State memory | 40.0%, 40.0%, 60.0% | 46.7% +/- 11.5% | 2/5 | 7/15 | 0 |

## Cost including memory construction

| Method | Input tokens | Output tokens | Mean total tokens / answer | Calls | Mean elapsed seconds / answer |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full text | 27,021 | 3,588 | 2040.6 | 15 | 5.71 |
| Sparse TF-IDF RAG | 11,439 | 2,842 | 952.1 | 15 | 4.65 |
| State memory | 184,532 | 18,228 | 13517.3 | 135 | 30.53 |

Cold-start memory construction is included. Cached or amortized long-running-agent cost was not evaluated. Token counts come from provider responses and are not verified billing amounts.

## Paired majority comparison

- state_memory_vs_full_text: 1 wins, 3 losses, 1 ties; exact McNemar p=0.6250.
- state_memory_vs_tfidf_rag: 0 wins, 3 losses, 2 ties; exact McNemar p=0.2500.

Only five unique episode units enter this calculation. Repeated calls do not enlarge the independent sample. The protocol was developed after prior failure inspection, and source events share market context. Do not interpret these calculations as proof of generalization.

## Errors

| Episode | Repeat | Method | Reference | Prediction | Invalid citations |
| --- | ---: | --- | --- | --- | --- |
| DERIVED_EP_002466 | 1 | full_text | NEUTRAL | BEARISH | none |
| DERIVED_EP_300308 | 1 | state_memory | BULLISH | NEUTRAL | none |
| DERIVED_EP_300502 | 1 | state_memory | BULLISH | NEUTRAL | none |
| DERIVED_EP_300750 | 1 | state_memory | BULLISH | NEUTRAL | none |
| DERIVED_EP_002466 | 2 | full_text | NEUTRAL | BEARISH | none |
| DERIVED_EP_300308 | 2 | state_memory | BULLISH | NEUTRAL | none |
| DERIVED_EP_300502 | 2 | state_memory | BULLISH | NEUTRAL | none |
| DERIVED_EP_300750 | 2 | state_memory | BULLISH | NEUTRAL | none |
| DERIVED_EP_002466 | 3 | full_text | NEUTRAL | BEARISH | none |
| DERIVED_EP_300502 | 3 | state_memory | BULLISH | NEUTRAL | none |
| DERIVED_EP_300750 | 3 | state_memory | BULLISH | NEUTRAL | none |

### Failure inspection

State memory supplied an empty final graph in 6/15 predictions. Required reference-source coverage was zero in 8/15. This localizes an important end-to-end bottleneck to loss of relevant facts during memory construction, rather than an API or JSON parser failure.

In 3 retained outputs, the direction field differs from the reason's explicit 'yields NEUTRAL' text. The direction-field score is retained; the reason is not used to silently correct it.

The retained graph context also contains a market-share fact invalidated by a revenue-related reason. Different financial metrics require separate thesis identities; opposite signs alone do not establish contradiction.

Grounded accuracy can still fail through omitted required evidence even when the table has no direction or invalid-ID error. Inspect `records.jsonl` for evidence coverage and reasons. Valid citation identifiers alone do not establish entailment.

## Evidence and scope

Run directory: `data/experiments/stage5-rag-reviewed-v3-20261030`.

The directory retains `manifest.json`, `episodes.jsonl`, `records.jsonl`, and `summary.json`. The adjacent plan froze inputs and reference rules before requests. Old single-repeat protocols are preserved separately and are not pooled into this comparison.

Task two's bounded comparison is complete. These results do not establish improved financial returns, neural-RAG superiority, two-hop topology benefit, autonomous skill evolution, or completion of the official RealFin forty-task benchmark.
