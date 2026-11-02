# Completed initial annotation and provisional experiments

This document records the initial AI annotation and development runs. The frozen
AI version retains its original provenance. The user subsequently checked and
accepted the forty extraction annotations; see [the confirmation and rescoring
record](stage5-user-review-status.md). Current editable labels are user-reviewed,
while the initial AI snapshot and episode-answer drafts remain distinct.

## Annotation delivery

The frozen `annotations-ai-v1.jsonl` contains 25 directed event relations across
16 documents. The other 24 records have explicit exclusion or ambiguity notes.
Every positive event includes exact evidence spans from the frozen input.
Headlines count as part of the input; linked full articles were not substituted.
Ten records need priority adjudication.

| Category | Documents |
| --- | ---: |
| In-scope event documents | 16 |
| Pure market statistics | 17 |
| Facts outside the six-relation ontology | 2 |
| Insufficient attribution | 1 |
| Insufficient source context | 3 |
| Holdings statistics excluded by L0 | 1 |
| Total | 40 |

Priority decisions include unnamed subsidiaries, joint investment, prospective
supplier relationships, industry forecasts, headline-only company guidance,
collective announcements, and unlabelled financial tables. Net profit remains
distinct from attributable profit where the excerpt does not state that scope.
Similar stories are assigned event groups. Quarterly/year-to-date results,
year-on-year/quarter-on-quarter changes, and proposals/completed actions are kept
distinct. No future return is used to assign these event labels.

The canonical local directory is `data/experiments/stage5-news40-unique/`:

- `annotations-ai-v1.jsonl`: frozen AI reference for provisional scoring.
- `annotations.jsonl`: editable labels for the user's review.
- `annotation-ai-v1-manifest.json`: corpus/reference hashes and counts.
- `annotation-review-ai-v1.html`: all forty inputs, labels, evidence, and notes.
- `annotation-review-ai-v1.md`: linear review copy.
- `episodes-ai-v1.jsonl`: five initial evidence-consistency episode labels.

The HTML packet exports checked labels after a reviewer identifies themselves and
checks individual records. Unchecked records remain unreviewed. Use the local
annotation editor to modify relations. The formal scorer still refuses an
unreviewed label file unless the explicit development flag is supplied.

## Extraction preflight

Plain, L0, and L0+L1 each ran once with `qwen-plus` against the frozen AI reference.
All 120 calls returned complete, parseable results. Exact directed relation F1
was zero in each method. These are development measurements, not final scores.

The original prompt permitted company/self/industry targets, while reference
events used event nodes. A second protocol, `event-target-v2`, added shared task
instructions about endpoints, scope, periods, and comparison bases for ALL
methods. It used the SAME reference without changing labels to fit predictions.
All 120 further calls completed. Exact relation F1 remained zero.

| Clarified-task method | Typed entity F1 | Exact relation F1 | Exact document accuracy |
| --- | ---: | ---: | ---: |
| Plain | 0.3284 | 0.0000 | 0.6000 |
| L0 | 0.1481 | 0.0000 | 0.6000 |
| L0+L1 | 0.2857 | 0.0000 | 0.6000 |

The 0.60 document accuracy is explained by the large empty-reference fraction;
it does not establish useful relation recall. Some correct financial outputs
fail exact matching because event names add years or amounts. Others have actual
errors: revenue decline classified as positive, prospective supplier ties
asserted as current, unsupported codes/dates, and missed mixed-sign disclosures.
An adjudicated event-naming policy is required. Post-hoc reference changes would
bias the comparison, so the frozen references and original outputs are preserved.

The original and clarified protocols are different development settings and must
not be pooled as repeated trials. The revised protocol was prompted by observed
errors; it is not an untouched held-out evaluation. No improvement is claimed.

## Evidence-consistency preflight

Five real-source episode drafts ask limited questions about repurchase intent,
mixed indicators, orders, and profit comparison bases. They do not predict future
returns or guarantee temporal-reversal coverage. Their AI answers await review.

One repeat of three methods completed with no API/parse failures:

| Method | Correct / episodes | Input tokens including memory build | Output tokens including build | Invented citation IDs |
| --- | ---: | ---: | ---: | ---: |
| Full text | 4 / 5 | 8,064 | 1,327 | 0 |
| Sparse TF-IDF RAG | 5 / 5 | 3,360 | 880 | 0 |
| State memory | 3 / 5 | 80,375 | 6,672 | 6 |

There were 55 calls: ten direct baseline answers and 45 state-memory calls
including construction and final answers. Combined with both extraction
protocols, this stage used 295 live calls, excluding the earlier connectivity
preflight. Token totals are provider-reported, not a verified billing statement.

State memory currently costs more and does not outperform the baselines on these
five provisional episodes. The sample and labels do not support a general
conclusion that memory is harmful or RAG universally superior. They identify
development failures that should be inspected before any broader claim.

## Next review

Inspect the forty records and adjudicate ontology, granularity, financial scope,
and event naming. Freeze a user-reviewed version and rescore saved outputs where
the task definition is unchanged. Use independent evaluation episodes where
possible; run repeated trials after fixing the protocol. A second independent
review subset is needed before reporting inter-annotator agreement.

This historical delivery records AI initial annotation and provisional runs.
The subsequent extraction review and rescoring do not establish a general
accuracy estimate or a demonstrated state-memory benefit.
