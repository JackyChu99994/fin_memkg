# Fin-MemKG handoff: stage five to the project team

Handoff date: 2026-11-02. Repository: [JackyChu99994/fin_memkg](https://github.com/JackyChu99994/fin_memkg).
Upstream baseline: `6c739eb9a129df8f63894753382faef2d9b1d2e6`.
Working branch: `codex/stage5-evaluation`. Implementation commit: `1f82ccd`;
this handoff is added by a subsequent documentation commit.

---

## 0. Read this first

First-time readers should start with the [project overview](docs/project-overview.md),
which explains the earlier stages and experiment terminology without assuming
familiarity with the code.

Stage five completes evidence evaluation and integration, rather than requiring
a positive memory result. The original stage-four assignment and its historical
counts are superseded by this handoff and the
[complete technical results](docs/stage5-completion-20261102.md).

PPT is intentionally deferred. Technical delivery is complete locally; remote
publication is a separate status and must be confirmed by an actual PR URL.
Real identities, student IDs, contribution confirmation, peer ratings and course
submission remain actions for the actual team.

Large source documents, experiment responses and references are ignored by Git.
Obtain the code/data bundle and original-announcement bundle before running
saved-study checks. A source-only clone does not contain the experiment data.
Never commit `.env`, provider credentials, raw logs or large experiment outputs.

## 1. What this stage delivered

| Work | Delivery |
| --- | --- |
| Whole-project and handoff audit | Reconciled the course task, architecture, missing resources and unsupported claims; [audit](docs/project-audit-20261031.md) and [revised assignment](docs/stage5-revised-handoff.md) |
| Original extraction evaluation | Preserved the owner's review provenance for the separate 40-excerpt development task and reported entity/relation results, including zero exact relation/state F1; [historical results](docs/stage5-final-results.md) |
| Source and reference governance | Collected announcements from 80 new companies; preserved original sources, quotations, scheme identity, cutoff rules, exclusions and errata; [collection](docs/diverse-source-collection.md) |
| Expanded evaluation | Completed the earlier 77-question lifecycle study and the final typed 23-question development / 91-question reserved study; retained their different reference tiers and denominators |
| Fair comparison | Used one Qwen configuration, common eligible sources, blind shared extraction, explicit failures, frozen protocol and a predeclared analysis plan across five methods |
| Application integration | Added chronological source-graph access to Evidence research and a read-only Generic-Agent source-query tool; original evidence and history remain traceable |
| Reproduction and reporting | Added offline validators, company-clustered analysis, failure/cost diagnostics, an editable report, a 9-page Chinese PDF and a read-only 455-slot HTML inspector |

This stage changes root application code and adds evaluation tooling; the old
stage-four promise of changing only `modules/` does not describe this delivery.
The original market snapshot and memory application remain separate components.

## 2. How to run it

Use Python 3.11; the experiment environment was 3.11.16. Unpack both delivery ZIPs
under the same parent, preserving their `fin_memkg/` prefix. Keep code/data bundle
metadata if the original-source bundle contains an overlapping metadata file.
From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/validate_final_stage5.py
.\.venv\Scripts\python.exe scripts/analyze_stage5_study.py --run modules/l0l4-memory/data/experiments/stage5-complete-reserved-20261102 --out workspace/new-analysis
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Validation and analysis above read saved data without provider calls. Model-driven
application actions require the owner's local Qwen configuration. Re-running live
inference is a new paid stochastic experiment, not a prerequisite for reproduction.
Provider aliases and temperature zero do not guarantee identical future responses.

For the integrated historical lifecycle graph, the following queries preserve
their original source-backed cutoffs; they are not the new 91-card benchmark:

```powershell
.\.venv\Scripts\python.exe scripts/query_research_kg.py --scheme CANDIDATE_301193 --as-of 2024-06-20
.\.venv\Scripts\python.exe scripts/query_research_kg.py --scheme CANDIDATE_301193 --as-of 2024-07-26
```

## 3. Interfaces and evidence boundaries

- The original market interface remains `data/market/{bars,index,universe}.parquet`
  plus metadata. Announcement QA evaluates disclosed facts, not return prediction.
- `research_kg.py`, `scripts/query_research_kg.py` and
  `memory/L3_skills/sop_source_graph_query.md` expose source/time-aware research
  graphs to the UI and Generic-Agent. Their deployment graphs belong to the
  earlier lifecycle study; they are not silently replaced by the final benchmark.
- `matched_disclosure.py` and `scripts/complete_stage5_study.py` implement the final
  comparison. Accepted machine observations require source/identity spans but are
  not certified true facts. Incomplete memory blocks the relevant answer slot.
- References, reference proofs and designated target identities do not enter
  actual extraction, retrieval, memory-building or answer prompts. Saved code
  snapshots and protocol hashes preserve what ran.

## 4. Verification and final results

| Check | Recorded result |
| --- | --- |
| Root tests | 220 passed |
| Separate memory-module tests | 99 passed |
| Final offline integrity | 570 planned slots; source hashes, observation spans, prompt cutoffs, reference separation and freeze hash passed |
| Independent unpacked-bundle check | Final validator passed against the extracted delivery bundle |
| Legacy integrity | 196 documents, 385 saved answers and 39 deployment graphs checked |
| Report and inspector | 9 rendered PDF pages; 8650 Chinese characters excluding references; all 455 reserved result views checked |

Final development: 23 cards / 20 companies / 108 unique eligible sources.
Final reserved: 91 cards / 48 companies / 251 unique eligible sources.
The 599 original PDFs describe the acquisition pool, not the formal sample size.

| Method | Development strict successes / 23 | Reserved strict successes / 91 |
| --- | ---: | ---: |
| Full text | 21 | 57 |
| TF-IDF RAG | 20 | 63 |
| Append memory | 16 | 55 |
| Current flat memory | 17 | 58 |
| Graph-assisted retrieval | 16 | 64 |

The company-macro paired difference of graph retrieval versus RAG is +2.43
percentage points, with a 95% company-bootstrap interval of -10.07 to +15.28
points. There is no established stable gain. Three selected temporal episodes
are three units: full text and RAG pass all three, each memory method passes two.
State-update gain is not established.

The complete final study made 863 actual calls: 359 shared source extractions
and 504 answers. Sixty-six blocked memory slots remain in the primary denominator.
Reported usage totals 7,904,074 input and 385,357 output tokens; older pilots and
reference-authoring costs are outside that total. Shared build calls are physically
charged once; cold standalone memory comparisons include their build cost.
No graph cost saving is demonstrated on the common available-card subset.

## 5. Known problems and limitations

1. **Reference quality:** the final bank is source-anchored AI silver, not
   independently human-certified gold. User review of the original 40 excerpts
   does not certify the new corpus. Negative audits, repairs and uncertainty are
   recorded; span agreement alone does not prove semantic entailment.
2. **Strict metric:** success combines field values, answer shape, scheme identity
   and supplied citations. RAG's positive field values can be correct while its
   top-level scheme convention fails. Abstention instructions lacked an explicit
   empty-object example; null-filled objects produce format failures. The separate
   post-hoc diagnostic preserves, rather than replaces, primary scores.
3. **Memory availability:** 48 reserved slots were blocked, 16 per memory method.
   All-rejected extraction and incomplete build coverage remain real weaknesses.
   Admission counts are not extraction precision/recall estimates.
4. **Generalization and power:** purposeful company selection, correlated cards,
   only three temporal episodes and a confidence interval crossing zero prevent
   broad superiority claims. Unused companies and repeated cutoffs are not extra
   evaluated samples. The 75-card available subset is secondary and conditional.
5. **Mechanism attribution:** graph-assisted retrieval supplies originals with
   machine claims. The experiment does not isolate topology, prove industrial-chain
   causal reasoning, or show that every L0-L4 component improves performance.
6. **Financial scope:** announcement fact QA does not establish investment returns,
   stock selection or CAR improvements. Historical market adjustment and snapshot
   coverage limitations remain; this stage does not claim to have repaired them.
7. **Reproduction and access:** large data are outside Git; dependency versions
   are recorded but requirements are not a fully locked environment. GitHub write
   access and real team information cannot be inferred from local authorship.

## 6. Recommended next work, in priority order

| Priority | Action | Acceptance criterion |
| --- | --- | --- |
| 1 | Have independent reviewers check references, especially negatives and scheme attribution; resolve disagreements with original sources | Publish reviewer provenance and a fixed gold subset without overwriting original AI drafts |
| 2 | Clarify the public answer schema, including an explicit abstention example and multi-scheme target selection; report semantic and contract metrics separately | Freeze on development data, then evaluate new reserved companies; preserve the present scores unchanged |
| 3 | Diagnose extraction rejection by cause and improve supported observation coverage on development data | Measure precision/recall against independently reviewed observations and coverage; include all blocked cases in end-to-end results |
| 4 | Expand independent temporal episodes covering correction, supersession, same-day conflict and multiple schemes | Predeclare company/episode units, scoring and sample-size rationale; no tuning on the existing reserved outputs |
| 5 | Isolate state updates and graph topology with controlled ablations | Compare matched observations and retrieval budgets; report paired uncertainty plus cold/warm cost and latency |
| 6 | Lock a reproducible environment and improve deployment status/error visibility | A teammate can unpack sources and reproduce offline results from a clean environment without keys |

If prediction or market-response validation is added later, treat it as a separate
task: freeze disclosure availability and point-in-time prices, use consistent
stock/benchmark provenance, and specify baselines before evaluating new data.
Adding price data to announcement QA alone does not establish predictive value.

## 7. Files and team handoff

Key source files: `matched_disclosure.py`, `repurchase_evaluation.py`,
`repurchase_catalogue.py`, `research_kg.py`, `scripts/complete_stage5_study.py`,
`scripts/analyze_stage5_study.py`, `scripts/diagnose_stage5_contract.py`,
`scripts/validate_final_stage5.py` and `scripts/build_final_review.py`.

Key documentation: this handoff, [complete results](docs/stage5-completion-20261102.md),
[project audit](docs/project-audit-20261031.md),
[revised assignment](docs/stage5-revised-handoff.md), and
[delivery scope](docs/stage5-delivery.md).

The owner's local final folder is
`C:/Users/Administrator/Desktop/fin_memkg-delivery-20261031/stage5-final-20261102/`.
This path is local, not a shared download URL. It contains the PDF/Markdown report,
HTML inspector, analysis files, code/data ZIP, original-source ZIP, patch, integrity
records and the personal-information/peer-review form. Share the two ZIPs through
an agreed team channel or release artifact; do not force-add ignored data to Git.

Technical implementation is complete; PPT remains deferred. Have the team fill
real identities and reviews, review the PR, and perform course submission. Remote
publication is only complete when its actual branch and PR have been verified.

## 8. One-sentence handoff

Stage five turns the memory prototype into a source-traceable, reproducible
comparison with explicit failures and uncertainty; the next improvement should
raise independently verified reference and observation quality before claiming
memory or graph gains.
