# Stage-five technical completion

Date: November 2, 2026. PPT remains deferred by the owner. This document supersedes
earlier intermediate readiness counts, without overwriting their evidence.

For the numbered team handoff, completed work, known problems and prioritized
improvements, see [stage five to the team](../HANDOFF-stage5-to-team.md).

## Completed scope

Stage five now includes the course/handoff audit, the owner-reviewed 40-news
extraction development study, source acquisition and reference provenance,
source/time-aware KG application access, real Generic-Agent source-query
integration, a matched five-method executor, complete development and reserved
runs, offline analysis, a Chinese technical report, result inspector and code/data
handoff. This is an evidence delivery, not a requirement to manufacture a gain.

The new corpus acquisition has 80 companies and 599 original announcements plus
three development supplements. Realized development questions cover 20 companies,
23 cards and 108 unique eligible sources. The reserved AI-silver bank covers
48 companies, 91 cards and 251 unique eligible sources. Its 12 unused reserved
companies are not counted as evaluated companies. Original 180-template
opportunities and 101 shortages remain preserved; supplemental cards do not
retroactively alter that schedule.

All 91 references have explicit AI-silver provenance, not independent human gold.
Twenty-two negative references use a Qwen full-context audit with assistant
quotation and rationale review; the assistant does not claim to have manually
read all their sources in full. Nine quotation repairs, five answer errata and
six scheme-identity errata preserve their original values and raw model outputs.

## Frozen study

`scripts/complete_stage5_study.py` completes development, freezes the protocol,
then permits one reserved run. The source/answer stages share `qwen-plus`,
temperature zero, no retries/fallback, identical eligible sources and public
answer contracts. Memory variants share one blind source extraction; no reference
values enter extraction, retrieval, memory construction or answer prompts.

Retrieval uses character-bigram TF-IDF, 1,200-character chunks, 150-character
overlap, top 16, public source-ID lookup and fixed Chinese field aliases. Evidence
has a common 48,000 serialized Unicode-character ceiling, not equal token length.
Memory notes consume that ceiling and have an 8,000-character sublimit. Full-text
overflow and incomplete memory are explicit failed slots. Current memory retains
same-day conflicts and separates scheme/field keys; graph-assisted retrieval
traverses source/scheme/observation links and supplies originals with machine claims.

Development finished before the reserved freeze. The analysis plan predates
reserved inference; it specifies company clustering, 5,000 paired bootstrap
replicates and seed 20261102. All original code snapshots and the frozen manifest
hash are verified. No reserved answer was regenerated or used to tune the methods.

## Primary results

The primary measure is strict typed-task success, including scheme ID, answer
shape, field values and valid supplied citations. Blocked slots count wrong.

| Method | Development / 23 | Reserved / 91 | Reserved company macro | Company macro 95% interval |
| --- | ---: | ---: | ---: | --- |
| Full text | 21 | 57 | 61.67% | 50.56% to 71.81% |
| TF-IDF RAG | 20 | 63 | 67.71% | 58.33% to 76.39% |
| Append memory | 16 | 55 | 60.69% | 50.28% to 70.83% |
| Current flat | 17 | 58 | 65.90% | 54.72% to 76.32% |
| Graph-assisted retrieval | 16 | 64 | 70.14% | 59.03% to 80.56% |

Graph retrieval is one strictly successful card ahead of RAG. Its paired company
macro difference is +2.43 percentage points, with a bootstrap interval of
-10.07 to +15.28 points. This does not establish a stable memory advantage.
Purposeful sampling and AI references further limit generalization.

In development, 18 memory slots were blocked. In reserved, 48 slots were blocked
(16 per memory method). All remain in primary denominators. The secondary
all-five-available subset has 75 cards: correct counts are 43, 49, 55, 58 and 64.
This availability-conditioned subset is not substituted for the 91-card primary
result and is not a causal estimate of graph topology.

The three selected temporal episodes are three units, not nine independent
samples. Full text and RAG each pass all three complete episodes; each memory
method passes two, partly reflecting build availability. State-update gain is
not established by these diagnostics.

## Contract diagnostics and interpretation

Post-hoc descriptive decomposition exposes an important boundary of the frozen
strict metric. RAG has all 66 positive cards' field values correct and identifies
all 25 negative cards as insufficient. Its ten multi-scheme date mappings are
correct, but it chooses the earlier scheme as the top-level target, violating
the stated later-scheme target convention. Seventeen negative answers return a
nonempty object containing null rather than the empty answer object required
by the validator. Graph retrieval has six such negative payload failures.

The public instructions did not provide a separate explicit empty-object
abstention example. This under-specification means strict format failures must
not be presented as failures of financial fact understanding. Primary scores
are unchanged; `scripts/diagnose_stage5_contract.py` produces a separately labeled
post-hoc decomposition without regenerating responses or relaxing the frozen
criteria. A future protocol should clarify the abstention shape on new data.

The 958 admitted reserved observations and 704 rejected candidates are admission
records, not true extraction precision/recall or independent facts. Span matching
does not establish semantic entailment. The old 40-news entity/relation results
remain a separate development extraction experiment; they are not replaced by
the typed question success rate.

## Costs

The two complete study phases use 863 actual calls: 359 shared source extractions
and 504 answers, across 570 planned answer slots. Reported provider usage totals
7,904,074 input and 385,357 output tokens. Historical pilots, reference authoring
and audits are outside this study total. Shared extraction is physically charged
once, even though each memory alternative's cold-deployment comparison includes
that build cost.

| Reserved method | Warm answer input tokens | Cold input tokens |
| --- | ---: | ---: |
| Full text | 1,239,993 | 1,239,993 |
| RAG | 1,066,652 | 1,066,652 |
| Append memory | 1,025,593 | 1,834,515 |
| Current flat | 992,412 | 1,801,334 |
| Graph retrieval | 1,000,090 | 1,809,012 |

Unmatched warm totals have unequal answer counts and cannot alone establish
savings. On the common 75-card subset, RAG uses 846,873 answer input tokens and
graph retrieval 1,000,090. No lower graph input cost is demonstrated there.
Provider prices and monetary savings are not inferred from these token counts.

## Reproduction and verification

Saved outputs are authoritative for offline reproduction; calling a provider
alias again is a new stochastic experiment. Large data and raw calls are
delivered separately, not committed to Git. After unpacking the code/data bundle:

```powershell
python -m pip install -r requirements.txt
python scripts/validate_final_stage5.py
python scripts/analyze_stage5_study.py --run modules/l0l4-memory/data/experiments/stage5-complete-reserved-20261102 --out workspace/new-analysis
python scripts/diagnose_stage5_contract.py --run modules/l0l4-memory/data/experiments/stage5-complete-reserved-20261102 --analysis workspace/new-analysis/analysis.json --out workspace/contract-diagnostics.json
python scripts/query_research_kg.py --scheme CANDIDATE_301193 --as-of 2024-06-20
python scripts/query_research_kg.py --scheme CANDIDATE_301193 --as-of 2024-07-26
python -m streamlit run app.py
```

The final validator verifies source hashes, archived code, all 570 answer slots,
actual prompt cutoffs, absence of private reference fields, observation spans and
the reserved freeze hash. It makes no API calls and certifies neither annotation
truth nor semantic entailment. Root tests pass 220 cases; the separate fourth-stage
module passes 99 cases. Legacy saved-study checks also pass for 196 source
documents, 385 saved answers and 39 deployment graphs.

The PDF report has over 5,000 Chinese characters excluding references and has
been rendered for page inspection. A read-only HTML inspector exposes all 455
reserved slots and their actual model inputs, references and original sources.
Credential values, virtual environments, Git internals and raw logs are excluded
from the delivery archive. Environment package versions are recorded with no
credential export.

## Remaining owner actions and publication boundary

PPT is deliberately deferred. Real names, student IDs, contribution confirmation
and subjective peer ratings require the actual team; no scores or identities are
fabricated from Git author handles. The supplied form records these owner actions.
Course submission itself remains the owner's action.

GitHub branch creation returned HTTP 403 (`Resource not accessible by integration`)
and local Git has no noninteractive push credentials. Therefore this delivery
provides a local commit and patch for a PR; it does not claim an online push or PR
was created. No main-branch merge is performed.
