# Stage five handoff

2026-10-31: [the whole-project audit](../../../docs/project-audit-20261031.md)
and [revised stage-five assignment](../../../docs/stage5-revised-handoff.md)
supersede this local progress log as the scope/acceptance contract. The deployed
module now shares Qwen configuration and fails LLM mode without model/rule
substitution. Current checks pass 115 root tests and 95 module tests. Prior
experiment numbers below are retained under their original protocols.

Branch: `codex/stage5-evaluation`, based on upstream `6c739eb`.
No changes have been pushed and no pull request has been created.

The project owner selected Qwen for stage-five experiments on 2026-10-29.
Use `qwen-plus` consistently across all methods and repetitions. The local ignored
repository `.env` is configured. A two-call live preflight on 2026-10-29 passed:
basic JSON connectivity and extraction of one ungraded news excerpt. The provider
reported 997 input tokens and 153 output tokens. This is not an accuracy study.

## Implemented and checked

The 2026-10-30 follow-up repairs archive sources after empty extraction, constrain
state updates by financial scope, preserve evidence references, and add matched
archive retrieval controls. The isolated suite now passes 87 tests. A two-case
live regression passed for both RAG and archive-augmented memory; it does not
establish a memory advantage. A five-series historical price subset is available,
but inherited news timestamps remain unverified. See
[the repair and historical-data audit](memory-repair-audit.md) before running
additional effectiveness experiments. The original v3 results below are unchanged.

Two official-notice-backed delayed-entry historical pilots now have full-report
inputs and separately stored five-session outcomes. They are not held out and
lack prior-state histories. See [the historical pilot](historical-pilot.md).

A four-filing BYD repurchase chain now supports four dated lifecycle cutoffs.
Two development diagnostics exposed empty polarity graphs and erroneous state
admission. The factual-memory prototype and subsequent offline admission repairs
are recorded in [the lifecycle audit](lifecycle-development.md). Its references
are AI drafts pending review; no additional memory gain or held-out result is
claimed. The latest admission repairs now pass a 32-call known-chain live
regression: all three methods score 4/4 with grounded citations and no validation
failures. State memory uses about 2.14 times RAG's total tokens including memory
construction. This recovers known failures but does not beat RAG. Additional
chains will follow [fixed prospective rules](lifecycle-expansion-plan.md).

The owner subsequently requested a substantial expansion. Forty company-level
candidate groups and 196 original filings (679 pages) have been acquired and
extracted, with ten companies/47 documents in development and thirty/149 reserved
for test. Group assignments were fixed before source annotation and prediction.
Scheme identity and new references still require review; these are not yet forty
verified test schemes. See [the expanded corpus](expanded-corpus.md).
All 196 source-based reference drafts are now available with a review index and
editor. Quotation checks pass for 87 and flag 109 for adjudication; no new record
is human reviewed. The batch used 197 calls including one explicitly logged
same-prompt timeout retry. No effectiveness inference has run on the expanded
cohort. Reserved-test preparation and evaluation both enforce a review gate.

Task two is complete as a bounded development comparison: five questions
mechanically derived from the reviewed facts, three repetitions, 165 live Qwen
calls, and 45 final answers. Mean accuracy is 80.0% for full text, 100.0% for
sparse TF-IDF RAG, and 46.7% for state memory. No memory benefit is demonstrated.
See [the results](stage5-rag-results.md) and [fixed protocol](stage5-rag-protocol.md).

Update: all forty records now have completed AI initial annotations, including
25 event relations, 24 justified empty outputs, evidence spans, and ten priority
adjudication cases. The user has now confirmed all forty extraction annotations;
the reviewed reference is frozen and all six saved extraction runs were rescored
without new API calls. See [the confirmation record](stage5-user-review-status.md).
Two development extraction
protocols and one memory preflight have completed. See
[the annotation and preliminary-run status](stage5-ai-annotation-status.md).

- Source collector with text/URL deduplication and provenance metadata.
- Forty local source records from five stock-code searches, with hashes, links,
  publication times, and AI initial labels subsequently checked by the user.
- Local human annotation editor and explicit annotation instructions.
- Extraction comparison: shared schema, L0, and L0 plus L1.
- Memory comparison: full text, sparse TF-IDF RAG, and the actual state machine.
- Strict model failure accounting, chronological cutoff, token accounting that
  includes memory construction, immutable run directories, and source hashes.
- Market bridge reads the root market directory and `CURRENT.json` generations.
- Isolated regression: 87 passing tests, including 62 added tests.
- English technical-report draft and a presentation of methods and current status.

The acquired text is provider search excerpts. Source attribution is preserved,
but the facts have not been independently verified. Distinct URLs are not
necessarily independent events. Raw data and run outputs remain ignored.

## Task status and remaining work

1. Completed: user review of forty extraction annotations. Preserve the frozen
   reference. An independent second review is only needed if reporting agreement.
2. Keep the verified local Qwen configuration consistent across methods. The
   connection preflight is complete and the extraction reference is now reviewed.
3. Completed task-two comparison: references were mechanically derived from
   reviewed facts under explicit rules. No independent episode annotation is
   claimed. Older AI episode drafts are preserved separately.
4. Archive recovery and conservative cross-metric guards are implemented. Event
   naming and extraction omissions remain open. Verify historical news availability
   and freeze a held-out protocol before making improvement claims.
5. Replace pending empirical sections in the report with audited results; add
   actual team names and peer assessments, then create the submission PDF/PPT.

The first task's annotation/metric delivery and second task's bounded comparison
are complete. Report/PPT finalization and optional integration remain separate.
The current tests and experiments do not establish general graph-memory gains
or complete the official RealFin benchmark.

## Evidence and next commands

Read [the experiment README](../experiments/README.md) for commands and input
formats. The canonical local news directory is
`data/experiments/stage5-news40-unique/`. Earlier trial collections under the same
ignored parent were superseded after URL deduplication and must not be mixed in.
The recorded development run is `data/experiments/stage5-offline-extraction/`.

The inherited fourth-stage handoff references experiment scripts and writing
materials omitted from its slim upload. This stage implements its own documented
entry points and does not pretend those omitted artifacts were recovered.

## Claim and evidence review

| Claim | Evidence | Status |
| --- | --- | --- |
| Snapshot bridge follows the published generation | Dedicated stale-file and path-escape regression tests | Supported implementation behavior |
| Forty attributable news records are locally available | Unique source URLs and SHA-256 counts | Supported collection property |
| Extraction quality is measured reliably | Counting, validation, failure and label-binding tests | Supported for tested cases |
| The state machine improves real-model results | No reviewed live comparison yet | Needs experiment |
| Two-hop topology improves results | Not isolated by this comparison | Unsupported |
| Neural RAG is inferior | No neural retrieval baseline | Unsupported |
| Token use is lower overall | No live comparison yet; building cost is included | Needs experiment |
| Financial return predictions improve | No new point-in-time return benchmark | Unsupported |

## Five-dimension review

- Contribution: implemented evaluation and integration repairs are concrete;
  scientific novelty and empirical benefit are not yet established.
- Clarity: tasks, source scope, methods, and commands are documented separately.
- Experimental strength: offline behavior is checked, Qwen is configured, and
  development outputs have been rescored against user-reviewed extraction labels.
  Broader performance claims remain unsupported.
- Completeness: real episodes, reviewer agreement, and final comparisons remain.
- Method soundness: coarse automatic invalidation, excerpt quality, event
  dependence, and sparse-baseline limits are explicitly disclosed.
