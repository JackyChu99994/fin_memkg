# Fin-MemKG: a guide for first-time readers

Updated: 2026-11-02. Start here if you have not read the code or earlier handoffs.
For implementation details and follow-up priorities, read the
[stage-five handoff](../HANDOFF-stage5-to-team.md).

## 1. What problem does this project address?

Financial research involves reading announcements, connecting companies and
events, remembering earlier information, and revising conclusions when new
evidence arrives. A language model can summarize a document, but a useful research
assistant also needs to show where its claims came from and what was known at
the time of a question.

Fin-MemKG is a course research prototype for this workflow. It combines language
models, knowledge graphs, market-data tools and source archives. It studies
whether structured, updated memory helps answer financial questions compared
with retrieving original documents. The evaluated factual questions concern
announcements, especially share repurchase schemes. The project has not
established profitable trading or reliable future-price prediction.

## 2. A running example

The following company and dates are illustrative, not an experimental result.

| Date | New disclosure | What the system should remember |
| --- | --- | --- |
| January 5 | Company A announces a share repurchase plan | A plan exists; an actual purchase is not yet established |
| February 10 | The company reports its first purchase | Repurchase has started |
| June 20 | The company reports completion | Repurchase has completed |

For a question dated March 1, using the June completion disclosure would reveal
the future. The system must use only evidence available by the question cutoff.
If Company A has two plans, it must also distinguish their identities rather
than attaching one plan's completion to another plan.

A stored fact might therefore contain company, scheme, field, value, availability
time and an original-source quotation. Preserving the older record explains
why the answer changed. It also lets a reader inspect whether the extracted claim
actually follows from the announcement.

## 3. Terms used in the project

| Term | Plain-language meaning |
| --- | --- |
| Knowledge graph (KG) | A structured record of objects and their relationships, such as company -> scheme -> disclosure |
| Extraction | Asking a model to turn text into named fields or relationships; an extracted claim can still be wrong |
| RAG | Retrieve relevant document passages, then ask a model to answer using those passages |
| Memory | Previously extracted information retained for later questions, with its source and time |
| State update | Change the currently applicable record when new evidence arrives, while preserving history |
| Agent | A model-driven loop that chooses tools and observes their results to pursue a task |
| Cutoff / `as_of` | The latest time whose available evidence a question may use |
| Baseline / ablation | A comparison method, or a controlled version with one component removed |
| Silver reference | A machine-assisted expected answer with documented source checks; it is not independent human gold |
| Token | A unit used by the provider to measure model input/output; it is not identical to a character |

The inherited L0-L4 vocabulary describes organizational layers: L0 rules,
L1 routing/index, L2 facts, L3 skills or analysis procedures, and L4 source archives.
These are software conventions inspired by GenericAgent, not five separately
trained neural networks. Their exact responsibilities vary across the prototypes.

## 4. What the earlier stages contributed

These are work stages, not a certified list of independent people. Git author
handles alone do not establish real identities or contribution percentages.

| Stage | Contribution | Why it matters | Boundary |
| --- | --- | --- | --- |
| 1 | Original financial KG workbench: bullish/bearish theses, state changes, evidence pointers, market context and supply-chain demonstration | Makes a conclusion inspectable and revisable | Demonstration mechanisms are not proof of predictive gains |
| 2 | `ga_core/`: a general tool-using loop, file/tool interfaces and memory/skill primitives, with supporting data-source repairs | Gives a model a way to call tools rather than only produce text | Framework tests do not establish a complete live financial Agent workflow |
| 3 | Market snapshots, intraday/sector adapters and fixed task acceptance screens | Makes prices and task outputs easier to obtain and inspect | Full historical data coverage and all external benchmark tasks are not certified |
| 4 | `modules/l0l4-memory/`: a separate extraction, archive, typed-relation memory and event-study application | Demonstrates filtering, evidence retention and updating old conclusions | It has its own schema and UI; it is not automatically the root application's memory backend |
| 5 | Audits, provenance repair, extraction evaluation, new announcements, fair comparisons, source-graph access and final reporting | Tests what works, exposes failures and supplies reproducible evidence | Current results do not establish stable memory superiority |

The root application already included financial judgment and a KG before stage
four. Calling it only a market-data layer would hide that work. Stage four adds
a parallel prototype rather than replacing every earlier component.

## 5. How the pieces fit together

```text
Original announcements                     Market snapshots / adapters
          |                                           |
          v                                           v
Source archive + available time                 Price/context tools
          |
          +--> Retrieve original passages ----------+
          |                                         |
          +--> Model extraction                     |
                 |                                  |
                 v                                  v
           Source/time checks --> Stored claims --> Answer / UI
                                      |
                                      v
                              Historical evidence query

Separate evaluation: fixed questions + references + saved answers --> analysis
```

This is a conceptual workflow. It does not mean that all repository applications
share one storage schema or execute one unified pipeline. The final comparison
has its own frozen executor; the integrated historical evidence-query graphs
belong to an earlier lifecycle study.

The root UI is `app.py`. The parallel memory UI is
`modules/l0l4-memory/app.py`. `ga_core/` is the generic tool framework.
`market_snapshot.py` and related modules provide market data. `research_kg.py`
and `scripts/query_research_kg.py` provide source/time-aware graph access.

## 6. What stage five actually tested

The old request to "prove memory's value" was reframed as a testable question:
under the same model and eligible source evidence, does memory help, hurt or
cost more than retrieval? A negative result is a legitimate experimental result.

| Method | Evidence made available to the answering model |
| --- | --- |
| Full text | Eligible original text within the common evidence ceiling |
| TF-IDF RAG | Passages ranked using lexical similarity |
| Append memory | Accumulated extracted observations plus retrieved evidence |
| Current flat memory | Current selected observations in a flat representation plus retrieved evidence |
| Graph-assisted retrieval | Evidence selected with source/scheme/observation links, including machine observations and originals |

Final runs use `qwen-plus`, temperature zero, common eligible sources and fixed
public answer instructions. Memory alternatives share one blind extraction pass.
References do not enter model prompts. Evidence has a common character ceiling;
this does not guarantee equal token counts. Failed memory construction is recorded
as a blocked answer, rather than silently substituted with a successful baseline.

Development data are used to debug methods. Reserved data are used after the
protocol and analysis plan are frozen. The final reserved answers were not
regenerated to improve their scores.

## 7. How much data is there?

| Dataset or stage | Size | Correct interpretation |
| --- | --- | --- |
| Original extraction development task | 40 news excerpts | A separate reviewed pilot, not 40 new independent companies |
| Earlier lifecycle source pool | 196 announcements from 40 candidate companies | Earlier expanded study; after qualification, 39 schemes and 77 cutoff questions |
| New acquisition pool | 80 companies and 599 original PDFs, with three additional development sources | Source collection size; not the number of formally evaluated questions |
| Final development study | 23 cards, 20 companies, 108 unique eligible sources | Development and method preparation |
| Final reserved study | 91 cards, 48 companies, 251 unique eligible sources | Primary final comparison; reference tier is AI silver |

A card is a question with a time cutoff and reference. A company may supply more
than one card; cards from that company can be correlated. Do not add historical
and final question counts together as if they formed a single independent test.

## 8. What did the final experiment find?

| Method | Strict successes / 91 | Rate |
| --- | ---: | ---: |
| Full text | 57 | 62.64% |
| RAG | 63 | 69.23% |
| Append memory | 55 | 60.44% |
| Current flat memory | 58 | 63.74% |
| Graph-assisted retrieval | 64 | 70.33% |

"Strict success" requires the expected answer structure, scheme identity, field
values and valid supplied citations. It is not simply "understood the financial
fact correctly." For example, a null-filled answer object can fail the validator
even if it correctly says the evidence is insufficient. A separate post-hoc
diagnostic documents this issue without changing the frozen primary scores.

Graph retrieval succeeds on one more card than RAG. Company-clustered paired
analysis gives a difference of +2.43 percentage points in company-macro success,
with a 95% interval from -10.07 to +15.28 points. This is a different aggregation
from the table's per-card rate. Because the interval includes zero, the study
does not establish a stable gain. Three temporal episodes are too few to support
a general state-memory claim; RAG and full text pass three, each memory method two.

The complete development and reserved study contains 570 planned slots and 504
actual answer calls; 66 memory slots were blocked. Together with 359 shared
source-extraction calls, there are 863 actual calls. Construction costs matter:
the common available-card comparison does not demonstrate graph input-token savings.

## 9. What is complete, and what remains uncertain?

Completed deliverables include the applications and integration changes,
source/reference ledgers, saved comparison records, offline analyses, an editable
report, a 9-page Chinese PDF, and a read-only inspector of all 455 reserved slots.
Recorded software checks passed 220 root tests and 99 separate memory-module
tests. These are code checks, not additional research samples or truth guarantees.

The main limitations are AI-silver references, extraction rejection and missing
memory coverage, an imperfect abstention contract, limited independent temporal
cases, and incomplete isolation of graph topology from other retrieval changes.
The evaluated facts do not establish trading returns or industry-chain causality.

Priorities are independent reference review, clearer answer contracts, better
verified extraction coverage, new temporal episodes and controlled ablations.
Improve on development data, freeze a new protocol, then test on new reserved
data. Do not tune on the current reserved answers and call it a fresh test.

PPT is deferred. The actual team must supply identities, contributions and peer
reviews and submit the course work. GitHub publication needs a verified branch/PR;
a local commit or prepared patch alone does not mean the work has been merged.

## 10. Where should a new reader start?

1. Read this overview and the [stage-five handoff](../HANDOFF-stage5-to-team.md).
2. Read the [complete final results](stage5-completion-20261102.md) for protocol,
   uncertainty, costs and reproduction commands.
3. Open the delivered Chinese report and `正式对照逐题核查.html` to inspect concrete
   questions and answers before reading experiment code.
4. Obtain both the code/data ZIP and original-announcement ZIP. Large data are
   ignored by Git, so a fresh source clone alone cannot reproduce saved studies.
5. Run `scripts/validate_final_stage5.py` and the offline analysis first. These
   do not need an API key. Install dependencies in a separate environment following
   the handoff; model-driven UI actions can call the paid provider.

The project's defensible contribution is an inspectable financial memory
prototype and a documented comparison that exposes its present strengths and
weaknesses. Demonstrating an update mechanism and proving a reliable advantage
are different milestones; this delivery makes that distinction explicit.
