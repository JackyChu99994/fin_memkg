# Task two RAG comparison protocol

This comparison implements item two in the fourth-to-fifth-stage handoff. It
measures consistency with the supplied documentary evidence, not realized stock
returns. A positive graph-memory result is not assumed.

## Fixed inputs and references

The experiment uses the frozen forty-record news corpus and
`annotations-user-reviewed-v1.jsonl`, confirmed by the project owner on
2026-10-29. The five episode references are mechanically derived from selected
reviewed facts. They are not described as five independently human-annotated
questions. The complete derivation specification is in
`experiments/reviewed_comparison.py`.

The reference rule is fixed: positive-only facts imply BULLISH, negative-only
facts imply BEARISH, and coexisting positive/negative facts imply NEUTRAL. The
question specifies the aspect to consider. These labels concern evidence signs,
not future investment returns. Questions address a repurchase, mixed domestic
and overseas business signals, orders, a repurchase plan, and mixed profit
comparison bases.

Source document identifiers and selected facts are kept outside model prompts.
The model receives raw eligible documents or its method's derived memory. Input
and reference hashes, queries, gold answers, and method settings are frozen in
the run plan before any requests. Equivalent syndicated reports can satisfy the
same evidence requirement, but only when their reviewed facts and event groups
match. Sources supporting different financial facts are not interchangeable.

## Methods and controls

1. Full text receives the episode's complete eligible raw document collection.
2. Sparse RAG receives the Top-3 documents ranked by character-bigram TF-IDF
   cosine similarity to the question. This is lexical vector retrieval, not a
   neural embedding retriever.
3. State memory receives the actual module's chronological extraction and graph
   state, including invalidated edges and supporting raw source identifiers.

All methods use `qwen-plus`, temperature zero, the same output cap, the same
eligible source collection, and the same answer contract. All model calls are
live; rule fallback, provider substitution, and hidden retries are disabled.
Failures remain in accuracy denominators. Methods rotate execution order across
three repetitions. There are five unique episodes, not fifteen independent
financial events.

Memory construction remains automatic and model-generated. Reviewed reference
facts are NOT inserted into the evaluated graph. The parent labels only derive
the answer key and evidence requirements. This distinction prevents oracle
memory from being mistaken for end-to-end system performance.

## Citation and serialization repairs

The earlier development run mixed graph relation identifiers, archive paths,
and raw news identifiers in final context. Protocol `memory-comparison-v3`
uses an explicit `allowed_evidence_ids` list for every method and distinguishes
`relation_id` from source IDs. Final memory context contains only semantic facts,
publication dates, status, reasons, and source IDs; temporary filesystem paths
and ingestion timestamps are removed.

A sidecar in the evaluation wrapper preserves all accepted source IDs when
the local graph reinforces a relation. It keys support by actual relation
instance, so a renewed relation does not inherit evidence from an invalidated
earlier lifecycle. These changes repair the experiment wrapper; they do not claim
the underlying production Neo4j/local-store implementations were rewritten.
Publication timestamps anchor memory updates instead of model-guessed period
ends. No future documents are admitted before retrieval or graph construction.

The old single-repeat development results remain unchanged. They must not be
pooled with v3 or used as an untouched held-out comparison: this is explicitly a
development protocol revised after inspecting earlier failures.

## Metrics and accounting

The report includes per-repeat accuracy, mean and sample standard deviation,
majority vote over each unique episode, citation validity, required-evidence
coverage, and grounded correctness. Grounded correctness requires a correct
direction, valid raw-source IDs, and complete reference evidence-group coverage.
A valid ID alone does not prove semantic entailment.

State-memory costs include every extraction call plus the final answer. Full-text
and RAG calls include their respective final prompts. Provider-reported input and
output tokens and elapsed times are retained; they are not monetary billing
statements. The current protocol rebuilds memory per episode and repetition, so
it reports cold-start cost. It does not establish warm-cache or amortized
long-running-agent cost.

Paired wins/losses/ties and exact McNemar calculations operate on the five
majority episode outcomes. Wilson intervals are descriptive small-sample ranges.
They assume independent episode units; shared market context can weaken that
assumption. No significant improvement is assumed, and repetitions do not
increase the number of independent source events.

## Reproduction

From `modules/l0l4-memory`:

```powershell
$env:PYTHONUTF8 = "1"
../../.venv/Scripts/python.exe -m experiments.offline_check
../../.venv/Scripts/python.exe -m experiments.reviewed_comparison --corpus data/experiments/stage5-news40-unique/corpus.jsonl --labels data/experiments/stage5-news40-unique/annotations-user-reviewed-v1.jsonl --provider qwen --model qwen-plus --repeats 3 --top-k 3 --out data/experiments/stage5-rag-reviewed-v3-20261030
```

Use a fresh output name when rerunning. The plan is written before calls;
per-prediction progress and completed call records are retained alongside it.
The final directory contains records, aggregate statistics, the source manifest,
and the mechanically derived episode file. Secrets remain in ignored local
configuration and are never included in those outputs.
