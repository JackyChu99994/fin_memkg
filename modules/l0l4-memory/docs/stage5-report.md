# Fin MemKG evaluation of structured financial memory

## Abstract

Financial news research requires a system to retain evidence, distinguish new
facts from repeated reports, and revise conclusions when information changes.
Fin-MemKG represents this task using layered memory and a financial knowledge
graph. We describe the inherited prototype and an evaluation extension that
separates knowledge extraction from reasoning over changing evidence. The
extension provides exact-match extraction metrics, a human annotation workflow,
and a same-model comparison between full-text context, sparse lexical retrieval,
and chronological state memory. Forty attributable news excerpts were collected
from five stock-code searches, with unique source URLs and exact text hashes.
Their AI initial annotations were subsequently checked and accepted by the
project owner. An isolated offline regression suite passes
46 tests; these checks establish software behavior rather than model performance.
Development extraction outputs have been rescored against the user-reviewed
reference. A repeated comparison uses five reference answers mechanically
derived from those facts. Mean accuracy is 80.0% for full text, 100.0% for sparse
RAG, and 46.7% for state memory. This development study establishes no memory
benefit or generalization claim. The resulting
protocol supports auditable experiments
without treating rule demonstrations, synthetic fixtures, or inherited results
from a different system as evidence for the new module.

## 1 Introduction

Investment research combines information that differs in form, timing, and
reliability. An announcement may describe a contract, a report may repeat the
announcement, and a later disclosure may cancel it. A useful memory must retain
the original evidence while representing the change in the contract's status.
Otherwise, an analyst or language model can retrieve an obsolete positive report
and mistake it for a current fact. This is a knowledge-maintenance problem as
well as a document-search problem.

The course project studies whether explicit financial knowledge can help with
that maintenance. Its scope includes companies, industries, products, supply
relationships, events, and market observations. The prototype organizes these
objects in L0-L4 memory. Rules and a concept dictionary guide extraction; a graph
stores relations and their states; analysis tools inspect event windows; and an
archive preserves evidence. The architecture draws on the layered-memory idea
illustrated by GenericAgent, while adding a domain-specific relation model.

This report focuses on measurement. A convincing demonstration of a state change
does not establish extraction accuracy, and a favorable historical return does
not establish that a graph caused a correct prediction. We therefore separate
software validation, knowledge extraction, consistency with documentary evidence,
and realized-return prediction. Each requires different labels and supports a
different claim. This separation is particularly important because the repository
contains several generations of prototypes and evaluation artifacts.

The stage-five contribution is a reproducible evaluation workflow rather than a
newly established model-performance gain. It freezes source inputs, binds labels
to input hashes, excludes unreviewed labels from formal scoring, and records
failures explicitly. It also compares memory representations using one configured
model and counts the cost of constructing structured memory. These choices make
future comparisons interpretable even if the graph provides no measurable gain.

## 2 Existing system and project scope

The repository root contains the earlier financial workbench, a GenericAgent-style
tool loop, market snapshot construction, and evaluation of twelve curated events.
A later module under `modules/l0l4-memory` implements a separate memory workbench
with a local JSON store and an optional Neo4j backend. The two workbenches share
project goals but differ in schemas, execution paths, and provider configuration.
They must not be treated as one fully integrated agent merely because both are
present in the repository.

The root market layer publishes complete snapshot generations and changes a
`CURRENT.json` pointer atomically. Stage five updates the new module's bridge to
follow that pointer and default to the repository market directory. A regression
test verifies that an old compatibility Parquet file does not override a newer
published generation. Another test rejects pointers that escape the designated
data directory. This is an integration repair; it does not independently validate
the market data or eliminate financial sampling biases.

The new module's `MemoryAgent` is a fixed sequence of routing, extraction,
validation, storage, event study, and decision rendering. It should be described
as an orchestration pipeline. The presence of named tools does not demonstrate
autonomous tool selection or skill self-evolution. Those capabilities would need
separate integration and evaluation through the root agent loop.

## 3 Data and annotation

### 3.1 Collection

The local evaluation collection contains forty records obtained through AkShare's
Eastmoney news interface on 2026-10-29. Searches cover stock codes 300750, 002594,
300308, 300502, and 002466. Each record preserves a title, provider text, publication
time, original URL, source name where supplied, retrieval time, and SHA-256 of its
text. Records are deduplicated by both exact text hash and source URL.

The source interface frequently returns search excerpts, including fragments of
tables, rather than complete articles. The extraction unit is therefore the
frozen title and excerpt actually supplied to the model. We do not claim that the
collection consists of forty full articles. A source link supports attribution;
it does not certify the truth, completeness, or independence of every report.
Different URLs can describe the same underlying event, so future splits and
confidence intervals must account for event-level clustering.

The collection includes noise under the inherited task definition. Price tables,
fund-flow rankings, and financing-balance summaries contain financial information
but are excluded from the module's investment-logic extraction policy. This
distinction should remain visible in the annotation protocol and the results.
A model that returns no relations for every item may achieve apparent document
accuracy on a noise-heavy sample while having no useful relation recall.

### 3.2 Human reference annotations

The annotation editor displays each frozen input beside an editable events list.
It stores the reviewer identifier, review status, notes, and the hash of the input
being reviewed. Assistant-created proposals are retained separately from the
reference `events` field. They do not become gold labels automatically. Formal
scoring requires every document to have a matching hash, a reviewed flag, and a
reviewer identifier. These fields record the annotator's assertion rather than
independently verifying the quality of the review.

Reference annotations describe directed relations with typed endpoints and
states. Reviewers should preserve the existing Chinese ontology values so the
evaluation remains compatible with the inherited module. Event names require a
consistent policy: an explicitly reported share repurchase can be represented as
an event target, while an amount or percentage remains an attribute. Unsupported
counterparties and inferred supply relationships must not be added from general
knowledge. Ambiguities should be adjudicated before model predictions are viewed.

The final study should include independent annotation of a subset by a second
reviewer. Agreement should be calculated before adjudication, with both original
versions retained. The project owner checked and accepted all forty AI-initial
extraction annotations through an explicit chat confirmation. There is no
independent second annotation or agreement study. Any final report must state
the actual number of reviewers and
their actual procedure rather than infer human review from a file name or flag.

### 3.3 Development fixtures

Eight author-created synthetic extraction cases and six synthetic memory episodes
exercise the evaluation code. Extraction cases include supported relations and
noise rejection. Memory episodes include a contract followed by cancellation or
confirmation, unrelated documents, and a future document that must be excluded.
These fixtures are explicitly marked as synthetic and unreviewed. They support
debugging and mechanism checks, not claims about real financial forecasting.

## 4 Task definitions

### 4.1 Knowledge extraction

Given a frozen news record, a model outputs a JSON object containing an events
list. Each event specifies a source entity, a directed relation, a target entity,
endpoint types, and a relation state. The six inherited relation categories cover
positive events, negative events, suppliers, customers, competitors, and industry
membership. The existing status vocabulary distinguishes active, invalidated,
and priced-in relations. An empty list is the expected output when the text does
not support an in-scope fact.

The evaluation reports three set-based measurements: exact typed entities,
directed triples, and directed triples with state. Wrong relation labels produce
both false positives and missed reference facts. Duplicate predictions are
collapsed for these set metrics. Exact matching does not tolerate arbitrary
aliases, paraphrased event names, or ontology changes. Consequently, reference
normalization rules must be agreed before evaluating a model.

### 4.2 Current-evidence consistency

A memory episode supplies timestamped documents, an as-of timestamp, a question,
and a separately stored reference answer. The output identifies whether the
current investment thesis is bullish, bearish, or neutral and cites supporting
document identifiers. This task asks whether the answer respects documentary
changes such as contract cancellation. It does not ask whether the stock will
actually rise over a future trading window.

Future documents are removed before any method performs retrieval or memory
construction. Timestamps must include timezones, avoiding ambiguous comparisons
between local time and UTC. Reference answers and evidence labels remain outside
the prompts. Reference evidence must belong to the eligible documents; otherwise
the run is rejected before model execution. These checks protect the experiment
inputs but do not remove information leakage already present inside a source.

## 5 Method

### 5.1 Layers and extraction variants

L0 contains rules for temporal boundaries, evidence pointers, the ontology, noise,
and status maintenance. L1 uses a concept dictionary to identify a subset of
candidate companies. L2 stores directed relations with confidence, date, status,
and archive references. L3 provides event-study calculations, while L4 records
source text using content-derived identifiers. The evaluation imports these
existing mechanisms rather than implementing an unrelated demonstration graph.

The extraction comparison includes three variants. The plain variant receives
the shared output schema and a short instruction to extract supported financial
facts. L0 adds the inherited rule block. L0 plus L1 adds the actual dictionary
router output. The shared schema controls formatting differences while the
variants isolate changes in instruction and candidate context. All variants use
one explicitly configured provider and model within a comparison.

### 5.2 Full text and retrieval baselines

The full-text baseline receives all eligible episode documents in chronological
order. The retrieval baseline forms character-bigram TF-IDF vectors and ranks
documents by cosine similarity to the question. It returns the top three by
default, breaking score ties deterministically by document identifier. This is a
sparse lexical RAG baseline. It does not use neural embeddings, and results must
not be described as defeating semantic embedding retrieval.

All methods begin with the same eligible raw documents. Their representations
differ after that point. Full text can retain irrelevant material; retrieval can
miss a low-overlap correction; state memory can lose details or incorrectly merge
facts during extraction. These are empirical hypotheses, not assumed outcomes.
The synthetic episodes have more documents than the retrieval cutoff so that
full text and Top-3 do not trivially receive identical inputs.

### 5.3 Chronological state memory

State memory processes documents in timestamp order. For each document, the model
receives its text, the inherited extraction contract, L0/L1 context, and existing
graph relations. Accepted events pass through the module's actual commit logic.
Same-direction relations can reinforce evidence; opposite-polarity relations
with matching endpoints can invalidate older edges. The final answering call
receives the resulting graph, including invalidated relations and evidence IDs.

The implementation uses a temporary graph and archive per episode. It does not
write experimental events into the demonstration memory. Archive identifiers are
mapped back to raw document identifiers for citation scoring. Unit tests check
that a cancellation changes graph state and that evidence citations remain
resolvable. These tests use scripted responses and establish implementation
behavior, not the quality of an external model's extraction.

The inherited invalidation rule is coarse. Opposite statements about the same
entities can describe different contracts, products, or time horizons. Treating
every polarity reversal as a contradiction can erase valid information. This
limitation is part of the evaluated method. Improving it would require explicit
thesis identity, qualified event scope, or a verified contradiction judgment,
followed by renewed evaluation.

### 5.4 Execution and cost accounting

The experiment client makes explicit calls with temperature zero and a fixed
output cap. It disables automatic SDK retries and never substitutes another
model or rule engine after an error. Incomplete output, malformed JSON, and API
errors are recorded as failures. This differs from the demonstration pipeline,
which intentionally offers a visibly labeled rule fallback for usability.

Token accounting includes memory-building extraction calls as well as final
answers. This prevents a comparison in which structured memory appears cheap
only because its construction cost is omitted. Provider-reported token counts
are retained where available. A failed request may still incur provider charges
without returning usage; the report must not present unavailable usage as a
verified billing total. No monetary savings are claimed by this implementation.

Completed runs write records, summaries, and manifests into a fresh directory.
The manifest binds input hashes, relevant code hashes, configured model settings,
call status, the base Git revision, and whether the checkout was dirty. Because
the current work is uncommitted, source hashes are necessary to identify the
evaluated code. Prompts and responses remain local artifacts for later audit.

## 6 Metrics and experimental protocol

For extraction, precision equals TP divided by TP plus FP, recall equals TP
divided by TP plus FN, and F1 equals twice TP divided by twice TP plus FP plus FN.
Counts are aggregated across documents for micro metrics. Undefined denominators
are reported as null. Exact document accuracy separately captures correct empty
predictions. Failed documents receive zero exact accuracy and contribute missed
reference facts, preventing API failures from disappearing from the denominator.

Schema validation can make accepted predictions look cleaner by rejecting bad
candidates. The evaluator therefore reports rejected-event counts and raw
relation precision in addition to accepted relation metrics. A malformed or
invented candidate remains visible as a raw false positive. These measurements
do not cover every hallucination: an invented amount inside a reason field can
escape relation matching. Numeric faithfulness would require a separate span-
or claim-based annotation and should not be claimed from this metric alone.

For memory episodes, the summary reports answer accuracy including failures,
invented evidence identifiers, and total tokens including construction. Per-case
records retain evidence recall where reference citations exist. A cited document
identifier does not prove that the cited text entails the answer, so citation
validity and evidential entailment must remain distinct. Future work should add
independent assessment of contradictory or unsupported answer statements.

Each real comparison should repeat methods three times using the same corpus,
labels, provider, model, and settings. Method order is rotated across repeats to
reduce confounding from provider conditions over time. Repeated calls on one
event are not independent financial events. Report per-event outcomes and paired
differences rather than treating repetitions as a larger independent sample.
With only forty excerpts, uncertainty and event clustering remain substantial.

## 7 Results available at handoff

The isolated module regression contains 46 passing tests, including twenty-one
new measurement and integration tests. New checks cover false-positive and
false-negative counting, relation direction, undefined empty metrics, human-review
and text-hash requirements, API failure accounting, malformed-output handling,
invalid relation visibility, prompt exclusion of gold fields, deterministic
retrieval, future-document exclusion, isolated state changes, citation mapping,
and snapshot pointer behavior. The remaining tests are inherited module checks.

The collection contains forty unique source URLs and forty exact text hashes.
These are acquisition properties. All forty extraction annotations have been
checked and accepted by the project owner after AI initial annotation. No
independent blind second annotation is claimed. Live
development extraction and memory comparisons have run. Exact relation F1 is
zero. In the earlier single-repeat preflight, state memory answers three of five provisional episodes correctly,
compared with four for full text and five for sparse RAG. Both genuine extraction
errors and event-name matching problems are documented separately. A formal
user-reviewed exact-match result is now available by rescoring saved outputs:
relation F1 remains zero under both development protocols. Original AI episode
labels have not been promoted to independent human annotations. The follow-up
comparison instead derives five answers from selected reviewed facts under
explicit positive-only, negative-only, and mixed-sign rules.

The follow-up repeats full text, sparse TF-IDF Top-3 RAG, and actual state-memory
construction three times with Qwen: five unique episode units, 165 live calls,
45 final answers, and zero API/parse failures. Full-text accuracies are 80% in
each repetition; RAG accuracies are 100% in each; state-memory accuracies are
40%, 40%, and 60%, giving a mean of 46.7% and sample standard deviation of
11.5 percentage points. Majority outcomes are 4/5, 5/5, and 2/5 respectively.
No memory advantage is established.

Including construction, mean total tokens per answer are approximately 2,041
for full text, 952 for RAG, and 13,517 for memory. These are cold-start costs,
not amortized long-running-agent costs. Memory supplied an empty final graph
in six of fifteen predictions and lacked required source evidence in eight.
Inspection found cross-metric invalidation and a direction field contradicting
its reason. Exact scores are retained. See [the comparison results](stage5-rag-results.md)
and [fixed protocol](stage5-rag-protocol.md) for evidence and limitations.

A development-only run applies the inherited keyword heuristic to eight
synthetic extraction cases. Entity micro F1 is approximately 0.462, directed
relation F1 is 0, and exact document accuracy is 0.125. The experiment makes zero
model calls. This negative result indicates that the demonstration heuristic's
entity and event choices do not match the stricter task references. It motivates
careful reference normalization and real-model measurement; it does not measure
Qwen, DeepSeek, or real-world graph effectiveness.

Earlier root-level documentation reports twelve-event model experiments and
three-repeat comparisons. Those results belong to the earlier workbench. Its
own analysis states that the complete method and Node-Only share the same
majority outcomes, so the two-hop-edge contribution was not established. Stage
five neither re-runs those experiments nor transfers their accuracy to the new
memory module. The official forty-task RealFin benchmark is also distinct from
the forty-excerpt extraction dataset created here.

## 8 Prototype use

The annotation interface runs locally on a separate Streamlit port. A reviewer
selects a record, checks its timestamp and linked source, edits events, supplies
notes, and explicitly confirms review. When an AI proposal exists, the interface
labels it as such. Saving updates the reference events while keeping provenance.
A dataset validation action identifies records that remain unreviewed or whose
text no longer matches the annotation hash.

The command-line extraction evaluator accepts the frozen corpus and labels,
selects one method, and writes an independent run directory. The memory evaluator
accepts reviewed episodes and runs all three representations with repeated
calls. Neither command needs Neo4j; memory experiments use an isolated local
store. The existing financial demonstration remains a separate application and
can still offer its explicitly labeled rule mode.

## 9 Limitations

The collected sample is small, recent, and determined by provider search results.
Its stock coverage is narrow, its label distribution has not been adjudicated,
and syndicated or overlapping stories can reduce the effective sample size.
Excerpts can omit decisive context. These limitations prevent broad claims about
financial-news understanding. A larger study should stratify event types,
include a held-out time period, and report event-clustered uncertainty.

The ontology permits financial implications but lacks a precise contract or
thesis identifier. Automatic merging and invalidation can therefore conflate
different facts. The dictionary router can miss companies outside its vocabulary,
and the sparse retrieval baseline is weaker than a properly tuned semantic
retriever in some settings. A favorable result against this baseline would not
justify a universal claim about RAG.

Financial evaluation has additional timing constraints. A local snapshot records
a data version but does not automatically provide point-in-time adjusted prices,
historical industry memberships, delisted constituents, or the information dates
of every financial field. The inherited event-study tool is separate from the
evidence-consistency benchmark and must not supply future outcomes to an earlier
prediction. A trading study would also need transaction costs, tradability, and
proper separation between model selection and testing.

## 10 Conclusion

Stage five supplies a measurable path from the existing memory demonstration to
an empirical course report. It adds a source-bound annotation workflow, strict
extraction scoring, and a same-model memory comparison with explicit failure
and construction-cost accounting. Offline tests verify these mechanisms and a
forty-record collection has undergone AI-assisted user review. The remaining
empirical work is to resolve task and event-matching issues and evaluate any
subsequent improvements on independently chosen cases under a fixed protocol.
The supported conclusion concerns observed implementation and development-set
behavior, rather than a demonstrated memory benefit.

## References

1. GenericAgent project. [Official repository](https://github.com/lsdefine/GenericAgent).
2. Fin-MemKG project. [Repository](https://github.com/JackyChu99994/fin_memkg).
3. Earlier workbench evaluation. [Evaluation protocol](../../../EVALUATION.md).
4. Market-layer handoff. [Data scope and limitations](../../../docs/STAGE3_HANDOFF.md).
5. Fourth-stage memory module. [Module documentation](../README.md).
6. Stage-five annotation protocol. [Reviewer instructions](stage5-annotation-guide.md).

## Personnel and peer assessment

The Git history identifies contributions from JackyChu99994, jckinpku,
qiudi0503-art, and jiangjieshi250 before this stage. The current stage adds
evaluation code, source collection, annotation tooling, and report materials on
a local feature branch. Git account names do not establish the complete real-name
team roster. Before submission, the team must supply actual names, specific
contributions, annotation reviewers, and independently written peer assessments.
No peer evaluation or unverified individual contribution is fabricated here.
