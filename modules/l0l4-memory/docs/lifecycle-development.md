# Lifecycle evidence and memory admission audit

Date: 2026-10-30. This is development on one selected event chain. Four cutoffs
are correlated observations, not four independent cases. All references below
are AI drafted and pending a new user review. The prior approval of forty news
annotations does not cover these labels.

## Original evidence and draft references

Four original company filings were downloaded from CNINFO. The official query
response, PDFs, extracted complete text, and hashes are preserved under
`data/experiments/byd-lifecycle-20261030/`.

| Filing date | Primary source | Repurchase stage | Share-cancellation stage |
| --- | --- | --- | --- |
| 2024-04-20 | [Repurchase report, 2024-048](https://static.cninfo.com.cn/finalpage/2024-04-20/1219697440.PDF) | No execution disclosed | Intended |
| 2024-04-26 | [First repurchase, 2024-050](https://static.cninfo.com.cn/finalpage/2024-04-26/1219825342.PDF) | Started | Intended |
| 2024-04-30 | [Implementation completed, 2024-052](https://static.cninfo.com.cn/finalpage/2024-04-30/1219909909.PDF) | Completed | Intended |
| 2024-05-14 | [Share cancellation completed, 2024-056](https://static.cninfo.com.cn/finalpage/2024-05-14/1220039687.PDF) | Completed | Completed |

The first filing authorizes a plan; it does not disclose actual purchases. The
second records a first purchase of 959,900 shares. The third records aggregate
purchases of 1,877,000 shares and pending share cancellation. The fourth reports
that those shares were cancelled on 2024-05-10. Event occurrence is distinct from
disclosure availability. Each cutoff conservatively admits its filing on the
following calendar day at 00:00 Shanghai time. This is a policy bound, not a
verified exact release time. Later filings are filtered out at earlier cutoffs.
Share cancellation is distinct from abandonment of the repurchase plan.

## First diagnostic: the existing graph stayed empty

`byd-lifecycle-comparison-20261030` made 32 successful provider calls and produced
12 final answers using Qwen Plus, temperature zero, Top-3 retrieval, and one pass.
Every one of the eight constructed memory graphs was empty. The six-relation
investment ontology omitted neutral lifecycle facts rather than inventing their
polarity. Thus this was effectively raw retrieval with extra construction cost,
not a successful test of populated state memory.

All three methods got all four repurchase-stage fields right. Each scored only
one of four on the original exact two-field reference because the answer contract
did not clearly distinguish cancellation *intent* from cancellation *execution*.
The outputs acknowledged planned cancellation in their reasons while selecting
NOT_DISCLOSED. These scores are retained but must not be reported as substantive
25% system accuracy. No labels or original outputs were changed after inference.

## Second diagnostic: quoted text can still produce a false state

An experimental factual-memory adapter was added without forcing neutral facts
into bullish/bearish relations. It extracts two separate lifecycle dimensions
from the full eligible filings, requires source quotes, preserves history, and
maintains a latest-state view. The event identity is the question's specified
company/plan, not a reference state. Append-only and state variants use the same
extractor contract and Top-3 raw retrieval. Costs include cold memory building.
This prototype is connected to the experiment adapter only; the demonstration
application has not been migrated to a general lifecycle ontology.

`byd-lifecycle-factual-v2-20261030` used an explicit intent/execution answer
definition. It made 27 provider calls, all successful. Three memory episodes
stopped on source-quote validation; failures are included in denominators.

| Method | Exact two-field answers | Source-grounded exact answers | Validation failures | Input tokens | Output tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sparse RAG | 4/4 | 4/4 | 0 | 25,177 | 1,206 |
| Append-only facts plus archive | 2/4 | 2/4 | 1 | 49,527 | 1,290 |
| Latest-state facts plus archive | 1/4 | 1/4 | 2 | 36,514 | 958 |

The first filing caused both memory variants to misclassify account opening as
actual repurchase execution. The answer model trusted this erroneous stored
state despite having the original source. For three other failed episodes,
the model joined nonadjacent source spans with ellipses; the initial validator
required one contiguous quote and rejected them. These are pipeline validation
failures, not provider outages. A separate validation audit preserves the spans.
Early termination makes token totals incomparable to successful complete runs.

## Subsequent repairs and current limits

After preserving those runs, the admission layer was changed to:

- check every explicitly ellipsis-separated span against the source in order;
  changed numbers, absent spans, and reversed ordering still fail;
- reject account-opening-only evidence for STARTED, preserving the rejection in
  the audit instead of inventing a replacement state;
- retain evidence spans, document IDs, availability bounds, and full observation
  history separately from the current-state view.

The current protocol is `factual-lifecycle-v2-admission`. These last changes pass
offline tests and the subsequent known-chain live regression below. The final
isolated module suite passes 73 tests, including source-span validation, rejected
admissions, state-dimension separation, lifecycle scoring, and future exclusion.
Literal span matching and the account-opening guard are not general entailment
verification. State identity is supplied for one selected chain; automatic
cross-event identity matching, reliable correction handling, and persistence in
the production UI remain open. No state-memory benefit is established.

## Post-repair live regression

`byd-lifecycle-admission-v3-20261030` reran the frozen four cutoffs with Qwen Plus,
temperature zero, Top-3 retrieval, and one pass. All 32 provider calls succeeded;
all twelve final answers passed both exact state scoring and required-source
grounding. No API or validation failures occurred.

| Method | Before admission repair | After admission repair | After-repair total tokens | Total measured seconds |
| --- | ---: | ---: | ---: | ---: |
| Sparse RAG | 4/4 | 4/4 | 26,345 | 28.629 |
| Append-only facts plus archive | 2/4 | 4/4 | 57,397 | 44.730 |
| Latest-state facts plus archive | 1/4 | 4/4 | 56,342 | 42.073 |

Sources, questions, availability cutoffs, event identity, draft references, and
answer definitions were checked equal to the preceding factual-memory run.
At each cutoff all three methods received the same selected raw source IDs.
Each of the eight memory builds rejected the account-opening-only observation
and preserved an audit entry. Segmented quotations passed ordered span checks.
At the last cutoff both memory variants retained six admitted observations;
the state variant supplied two current observations while append-only supplied
all six. Raw final predictions, prompts, observations, calls, usage, source
hashes, and a separate audit are preserved. The earlier failures were not erased.

The state variant used about 2.14 times RAG's total tokens including cold memory
construction. Timings are a single serial run, not a stable latency estimate.
The pre-repair memory runs stopped early on validation failures, so before/after
cost totals would compare different amounts of completed work.

This establishes a known-case engineering regression recovery, not superiority
over RAG or general temporal reasoning. All methods reached the same accuracy
ceiling on one previously inspected chain. References remain AI drafts pending
review, and the special account-opening guard was developed on this chain.
The next collection follows [a prospective expansion plan](lifecycle-expansion-plan.md)
fixed before collecting additional company chains or scoring their answers.

## Reproduction and next evaluation

Use a fresh output name. This command runs the **current** admission protocol,
not the exact pre-repair versions whose original source hashes are preserved:

```powershell
../../.venv/Scripts/python.exe -m experiments.lifecycle_comparison --cache data/experiments/byd-lifecycle-20261030 --out data/experiments/byd-lifecycle-current-new
```

Add `--prepare-only` to freeze inputs and the plan without model calls. No model
input contains draft reference states or future stock returns. Existing runs,
reference snapshots, source hashes, calls, and progress files remain unchanged.

Next prioritize independent event chains under frozen selection rules and a new
reference review. Include unchanged facts and different-metric facts as controls,
and distinguish real contradiction from ordinary completion. Repeating this
single chain after tuning can validate regressions but cannot create held-out
evidence. Do not use its returns to determine whether a factual state is correct.
