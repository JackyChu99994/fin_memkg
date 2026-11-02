Final technical completion (2026-11-02): see [the complete study and handoff](stage5-completion-20261102.md). The 23-question development run and 91-card reserved AI-silver comparison are complete. PPT is deferred; earlier readiness counts below are historical.

# Revised stage-five assignment: integration and evidence

Completion update: see [delivery](stage5-delivery.md),
[final findings](stage5-final-results.md) and [reproduction](stage5-reproduction.md).
This assignment remains the audit-time record; current results supersede its
intermediate counts. PPT is deferred by the owner.

Date: 2026-10-31. Owner: the fifth-stage participant. This follows the owner's
request to reassess the whole project. Earlier handoffs and planning notes are
context, not binding new commands or evidence that their claims are established.

## Objective

Deliver a reproducible financial-KG research prototype and an honest account of
its conditions and limitations. The role is integration and evidence owner,
not someone required to manufacture a memory advantage. Do not rebuild every
earlier module or treat repeated BYD cutoffs as new independent evidence.

## Completed now

| Task | Deliverable and acceptance |
| --- | --- |
| Reconcile course, previous stages and architecture | [Whole-project audit](project-audit-20261031.md), including missing resources and unsupported claims |
| Align deployed model with evaluation | Root Qwen reuse, explicit provider selection, no hidden model/rule fallback, actual deployment preflight |
| Enforce consistent extraction/failure behavior | Scope-safe prompt; missing configuration, truncation and malformed output fail before commit; rules explicitly separate |
| Reproduce whole-project checks | Local dependency repaired; Windows writer fixed; 115 isolated root tests and 95 module tests pass; isolated UI initial render passes |
| Qualify enlarged data before inference | Read-only inventory finds 40 candidate companies/196 sources, zero reviewed new references and zero formal-ready labels |

From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/check_stage3.py
Push-Location modules/l0l4-memory
..\..\.venv\Scripts\python.exe -m experiments.offline_check
Pop-Location
.\.venv\Scripts\python.exe scripts/project_readiness.py
```

These checks do not call paid models. Fake responses run only in isolated copies.

## Remaining work, in acceptance order

### 1. Close source and reference quality

Preserve the company split. Correct flagged quotations against originals, confirm
scheme identity and original approval dates, and record exclusions with reasons.
AI flags (109 span cases, five identity cases, seven year cases) overlap and need
source review; they are not automatic truth. Do not exclude hard cases after
seeing system predictions. Only actual reviewer actions may mark new references
reviewed; the earlier forty-excerpt approval does not cover these 196 files.

Acceptance: frozen sources, scheme IDs, reviewed references with provenance,
evidence spans and an exclusion ledger. Unknowns may remain explicit exclusions.
Until then, the enlarged sample is candidate data, not a formal test benchmark.

### 2. Show the inherited application's real KG role

Use the root financial-thesis workbench as the primary whole-project entry point.
Describe the fourth module as a parallel prototype connected by market reads.
State precisely which code path each experiment exercises. Do not call the
experimental list of lifecycle observations a graph-topology experiment.

Acceptance: a chronological real-source case showing structured nodes/relations,
evidence pointers, a valid-time update and a downstream answer. Include a
different-metric coexistence control and genuine correction/termination control.
Keep synthetic/rule scenes labeled as mechanisms. Completed share cancellation
is not abandonment of a plan, and state correctness is not trading profit.

### 3. Run a frozen comparison without prejudging the outcome

After reference readiness, compare full-text LLM, matched Top-K RAG, append-only
memory and updated memory where supported by the task. Keep provider/model,
sources, cutoffs, answer contracts and archive retrieval fixed. Prefer identical
extracted observations for append-versus-update analysis; otherwise report
extraction variability. Never insert reference states into evaluated memory.

Report extraction metrics separately from factual state correctness, evidence
recovery, false invalidation, task success and costs. Keep per-scheme results and
whole-scheme uncertainty; repeated cutoffs are correlated. TF-IDF is lexical, not
embeddings. A topology claim requires graph-enabled versus graph-disabled paths
on a task that uses relations, not merely different prompts.

Acceptance: complete auditable results, including negative or tied outcomes,
with raw calls, hashes, failures, exclusions, observations and costs. Do not
repeatedly tune on the reserved test. No predetermined gain or savings is required.

### 4. Finish evidence-grounded submission materials

Prepare the course report, PPT, dataset/code instructions, actual work allocation
and peer review. Use actual team names; do not invent contributions or scores.
Label inherited numbers by source/protocol limits. Separate implementation,
mechanism demos, measured accuracy, descriptive returns and untested hypotheses.

Acceptance: required report length/sections and formats, a demo reproducible from
documented data, and a supported explanation of the KG's actual function.
A fair negative result with a supported failure analysis remains valid research.

## Boundaries and team coordination

Full RealFin-40, general PC/browser automation, minute-history backfills and
universal stock forecasting are optional unless the team separately commits to
them. Earlier handoffs assigned final evaluation/reporting to a sixth stage and
integration to the fifth; the fourth handoff changed that allocation. Final
ownership must be reconciled, not assumed completed. No teammate is messaged by
this audit. The completed repairs do not complete the reviewed large experiment,
production neutral-graph integration or final report/PPT.
