# Expanded source-anchored study and deployed evidence query

Date: 2026-10-31. PPT authoring is deferred at the owner's request. This report
records completed technical work, not a claim of independent human gold labels.

## Data and reference qualification

The existing pool contains 196 original announcements from forty candidate
companies, 679 PDF pages, and a frozen company split. Original PDFs/full texts
and all AI drafts remain unchanged. Source-anchored execution-stage adjudication
excludes one 2023-approved company's five documents and five documents about
different schemes. Eighteen further documents lack a decisive supported stage;
they remain raw inputs where chronologically eligible but are not scored as
reference questions. The source ledger has 186 adjudication records, explicit
exclusion reasons, aligned actual-source windows and the unchanged original drafts.

The resulting study uses 39 company schemes and 77 cutoff questions: ten
development companies/19 questions and 29 reserved companies/58 questions.
Each scheme contributes its earliest and latest source-verifiable cutoff where
distinct. These cutoffs are correlated, not 77 independent events. References
are machine-assisted source-anchored **silver**, not independent human truth.
The target is disclosed repurchase execution, not sentiment, cancellation of a
plan, share-cancellation completion, or future returns.

## Frozen comparison

The separate forty-excerpt extraction development study retains the owner's
original review provenance. Saved shared-task runs have entity P/R/F1 of
0.458/0.256/0.328 for plain, 0.364/0.093/0.148 for L0, and
0.370/0.233/0.286 for L0+L1; exact relation/state F1 is zero throughout.
Twenty-four empty references dominate the 60% exact-document score. Free-form
event naming is one limitation, not an excuse to dismiss real missed facts.
The new neutral-fact task does not retroactively establish extraction improvement.

Qwen Plus, temperature zero, identical eligible original sources, lexical
character-bigram TF-IDF Top-3 retrieval, and one pass are used throughout.
One blind extraction pass is shared by all memory variants, so upstream model
differences do not masquerade as state-update effects. Extraction sees no reference
fields/proof. Invalid document extractions are quarantined, not replaced by rules.

Five methods: full text; TF-IDF RAG; append-only factual observations plus RAG;
current flat observations plus RAG; and current graph-formatted observations plus
RAG. The last two compare representations of the same selected state. This is
not an industry-chain causal reasoning benchmark or a full topology ablation.

The physical run made 556 API calls with no provider failures: 171 shared source
extractions and 385 answers. Five source extractions were quarantined. There are
114 admitted observations, with two schemes producing none. "Admitted" means
format/span checks passed, not that every assertion is semantically true.
Provider-reported usage is 2,440,339 input and 63,558 output tokens.

## Same-day reference erratum

Error review found two initial-reference mistakes: the repurchase report and an
actual first-purchase notice were both disclosed on the same date. The next-day
availability rule admits both, so the answer must reflect actual purchases.
A third reference changed its designated source ID without changing the class.

The v4 reference resolves jointly available same-day evidence and cumulative
execution. Original prompts, predictions and original scores are preserved.
Every method was rescored offline against the same corrections, with **zero**
extra model calls. The erratum ledger is included. These corrected numbers remain
silver-reference findings, not a pristine independently annotated benchmark.

## Results on the reserved-company partition

| Method | Execution stage correct | Designated source hit with correct stage | Answer tokens | Standalone cold tokens |
| --- | ---: | ---: | ---: | ---: |
| Full text | 58/58 | 58/58 | 410,217 | 410,217 |
| TF-IDF RAG | 58/58 | 50/58 | 299,273 | 299,273 |
| Append memory + RAG | 58/58 | 58/58 | 317,635 | 587,256 |
| Current flat memory + RAG | 58/58 | 57/58 | 306,514 | 576,135 |
| Current graph representation + RAG | 57/58 | 55/58 | 310,714 | 580,335 |

The designated-source metric requires the reference-selected disclosure ID.
It is not a universal entailment/grounding score: an earlier disclosure can still
be a legitimate citation for an unchanged cumulative state. No answer invented
a citation ID. Higher designated-source recovery cannot alone prove better truthfulness.

The reserved partition contains 27 no-execution and 31 started questions after
the erratum, **no completed-class question**. The sole scored completed-class
example is in development. The majority baseline learned on development predicts
no execution and scores 27/58 on reserved companies. Results are near a ceiling
for this narrow task; completion, termination, complex contradictions, and long
histories are not established by these aggregate scores.

Standalone cold memory costs charge the same shared construction once for each
memory method as it would operate separately. They are estimates from shared
physical calls, not additional billed calls. Graph-formatted memory costs about
1.94 times RAG cold and 1.04 times RAG for answers alone. Full-text tokens exceed
RAG by about 37%. The data do not show an accuracy or cost advantage over RAG.
The one-answer graph/flat difference is not evidence that graph structures are
generally harmful. Group bootstrap intervals condition on silver references;
they cannot quantify annotation error.

## Deployed source graph and admission hardening

The root application now includes **Evidence research**, backed by `research_kg.py`.
It stores COMPANY, SCHEME, OBSERVATION and SOURCE nodes and HAS_SCHEME,
HAS_OBSERVATION, SUPPORTED_BY and SUPERSEDES_CURRENT_VIEW links. A dated query
traverses scheme-observation-source paths, checks source hashes, and selects the
latest admitted observation per dimension. Historical statements are retained;
advancing the current view does not declare an earlier true disclosure false.

`scripts/query_research_kg.py` exposes the same read-only path to `ga_core` through
its existing code tool. A real two-call Qwen integration with a strict JSON final
contract returned the supported stage and source ID, independently checked against
the graph. The first loose-prompt integration also retrieved correctly but added
an unsupported ThesisNode/general-bias claim. That record is preserved; the strict
contract and structured UI prevent such embellishments from becoming verified facts.
This is one integration check, not general Agent-task accuracy or automatic skill learning.

The existing family scheme `CANDIDATE_301193` shows first purchases available
on 2024-06-18, a progress disclosure on 2024-07-03 and completed implementation
available on 2024-07-26. The graph returns the correct dated source path without
new model/network calls. The source query SOP is manually consolidated in the
existing L3 skill directory, not claimed as autonomous self-evolution.

Error analysis added a conservative actual-purchase admission check. A separate
versioned deployment graph quarantines five unsupported observations, preserving
original observations, all source files and the frozen study graphs. Four valid
first-purchase/as-of quantity spans that an overly strict draft guard would have
rejected were restored during source review. The deployed guard is covered by
offline tests; no new post-hardening accuracy claim is made on the same cohort.

## Reproduction

From the root, run `python -m streamlit run app.py` in the project environment and
select **Evidence research**. No API call occurs on that page. Query directly:

```powershell
.\.venv\Scripts\python.exe scripts/query_research_kg.py --scheme CANDIDATE_301193 --as-of 2024-06-20
.\.venv\Scripts\python.exe scripts/query_research_kg.py --scheme CANDIDATE_301193 --as-of 2024-07-26
```

Paid generic-Agent smoke requires the explicit `--live` flag on
`scripts/demo_ga_research.py`. Existing run artifacts are preferable to rerunning.
The enlarged study and erratum live under the ignored module directory
`data/experiments/expanded-study-20261031/`; silver reference versions and source
reconciliation live under `source-adjudicated-v3-20261031/` and `source-adjudicated-v4-20261031/`.
Frozen inference code copies are retained in the study's `sources/` directory.

The result supports a practical deployment choice: use graph structure for source,
time and state maintenance, while keeping simple disclosure answering on a strong
retrieval baseline. It does not support claiming improved stock forecasting,
universal KG superiority, or completed official RealFin-40 coverage.
