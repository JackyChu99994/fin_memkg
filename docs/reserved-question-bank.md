# Reserved question/reference construction

Date: 2026-11-01. This is reference construction, not a five-method evaluation.
No held-out method response or performance result was produced.

## Free-generation attempt retained as a failure

A pre-recorded schedule assigned three of six task families to each of 60
reserved companies, 30 opportunities per family (180 total). One Qwen Plus call
per company saw its archived original documents, never method predictions or
development answers. No retry/model fallback occurred. All 60 responses parsed.
Reported usage was 1,234,562 input and 90,604 output tokens.

The model proposed 115 questions and marked 65 opportunities unavailable. All
115 candidates failed mechanical checks: 114 omitted the required reference
answer; there were also unsupported fields, source/time and proof issues. These
are unusable AI draft records, not 115 qualified labels or model test outcomes.
Some questions themselves leak their requested answer or mention unavailable
future sources. Preserve them for audit, not as public benchmark questions.

The authoring workflow should have verified a small reference-generation output
before dispatching all 60 companies. No repeated paid pass was used to hide this
failure. A deterministic source-template alternative was then built separately.

## Source-bound alternative

`reserved_source_templates.py` implements fixed, conservative templates using
explicit source statements and the existing board-decision parser. It never
copies the failed model's reference reasoning into labels. It reuses the same
180 company/family assignments, with no method-prediction-based selection.

Current **v2** produces 79 review candidates across 48 companies, leaving 101
opportunities unavailable under these templates:

| Family | Candidates | Scope |
| --- | ---: | --- |
| Stage | 23 | Stage explicitly disclosed in the named source, not automatically a whole-history current state |
| Historical | 17 | Actual first-purchase date disclosed by an earlier real cutoff |
| Multiple schemes | 10 | Specified original sources mapped to different board dates |
| Update | 3 | Explicit termination board decisions and unambiguous shareholder gates |
| Evidence trace | 1 | Sum actual completed counts across two different schemes, retaining operands and source IDs |
| Insufficient evidence | 25 | First-purchase date absent under a conservative pattern check in the supplied archive at that cutoff |

The stage subset contains 11 STARTED and 12 COMPLETED candidates, no
NO_EXECUTION_DISCLOSED candidate. Termination is not relabeled completion.
Update currently covers termination rather than the full variety of corrections.
The one two-source sum is not evidence that general graph reasoning works.
These shortages mean the planned 200-300-question balanced evaluation has NOT
been achieved. Do not use many simple questions to disguise missing hard cases.

All 79 records have source offsets/hashes, cutoff-eligible full-company source
sets and a typed reference. There are 170 identity/answer/context spans. The 54
answerable candidates and 25 insufficient candidates remain pending semantic
review. Pattern non-match cannot prove semantic absence; the latter subset is
especially provisional. An absence statement concerns only the supplied archive,
never absolute real-world nonexecution. The archive was not artificially truncated
per question except by its declared historical cutoff.

V1 and v2 are retained. V2 ensures the target identity proof belongs to the later
original board date in a comparison even if an older scheme's report is published
later. It does not change the underlying source snapshot or any method output.

## Reference levels and fairness

Current `source_qualification` stays **pending**, human-reviewed and formally
ready counts stay **zero**. The source-derived records declare silver provenance;
mechanical consistency does not certify factual correctness or independence.
Failed free-generated questions and these source templates are alternate banks,
not disjoint samples to add together. None are silently promoted to human gold.

Named-source questions must be equally easy for every baseline to locate. A
future RAG runner should support exact public source-ID lookup and metadata
indexing, and address English query/Chinese source mismatch using declared,
reference-free query construction. Do not weaken RAG by searching English-only
question text against Chinese bodies while giving the graph the requested IDs.
All compared methods must receive the same public field contract and eligible
source universe. The old 58-question study, 23-question development pilot and
this new bank have different tasks and cannot form a direct improvement curve.

## Readiness and local files

Under the ignored module experiment directory:

- `reserved-question-drafts-20261101`: 60 paid reference-generation calls, plans,
  raw outputs, invalid candidates, unavailable slots and frozen source.
- `reserved-source-questions-20261101`: initial fixed-template alternative.
- `reserved-source-questions-v2-20261101`: previous 79 source-bound candidates,
  101 shortages, source snapshots and provenance.
- `reserved-source-readiness-20261101`: checks the current bank. All 79 still
  require source identity/sufficiency review; no final method protocol is supplied.
  It does not create a freeze manifest or start evaluation.

## Source audit v3 (November 1)

`reserved-source-questions-v3-20261101` preserves the same 79 question IDs and
source cutoffs. Five reference answers have explicit, source-backed errata:

- 300200 historical: first purchase is February 2, 2024, rather than the January
  31 statistics cutoff preceding the transaction paragraph.
- 300454, 603777, 002611 and 688349 stage: the source explicitly states completion;
  the previous template incorrectly fell back to the reported-purchase label.

The label utility now evaluates each date independently and rejects another
calendar date before the actual share quantity. This fixes reference extraction;
it is not an evaluated-method change or a performance improvement. Completion
errata are applied to the existing records, without rebuilding question selection
or tuning the graph/memory algorithms on reserved answers. V1/v2 and their source
snapshots remain intact. The updated stage mix is seven STARTED and sixteen
COMPLETED; no NO_EXECUTION_DISCLOSED stage question has been added.

The 25 insufficiency packets inventory every eligible document, date mentions and
source-bound cue windows. Absence is explicitly **not certified**. The negative
claim is scoped to the target scheme: an older scheme's first-purchase date is
not the new scheme's answer. Full semantic/source review remains necessary.

A 15-anchor correction-scope ledger excludes three anchors from the scheme-update
pool: 603280 is equipment financing-lease buyback guarantee advice; 688639 and
605377 are general repurchase policies. These exclusions do not remove a company's
other valid scheme documents. Three explicit correction sources (301042, 600568,
688016) are recorded as supplementation leads, not newly qualified questions.
The remaining revised reports still need paired-original/semantic checks.

Source CNINFO_1223041731 (002947) contains both RMB 8,000 ten-thousand and RMB 8,000
as the minimum budget. The discrepancy is visible on original PDF pages 1 and 2,
not solely in extracted text. The anomaly ledger retains both quotes and blocks
a single budget reference until resolved. Its existing stage question requests
no amount, so no stage answer is changed. A matching file hash verifies file
identity, not factual consistency inside that file.

All 79 remain pending source qualification; human-reviewed and formal-ready counts
remain zero. This audit makes zero model calls and modifies no method outputs.
The root test directory passes 193 tests, including date-boundary regressions,
immutable errata provenance and complete negative-packet source coverage. Run
`python -m pytest tests -q` explicitly: unrestricted discovery also enters ignored
historical workspaces and the separate module suites with different imports.

```powershell
python scripts/audit_reserved_references.py --out workspace/new-reference-audit
```

## Scoped semantic review v4 (November 2)

`reserved-source-questions-v4-20261102` keeps the 79 V3 IDs and adds three
supplemental correction questions. They are outside the original 180-opportunity
schedule: the original 101 unavailable slots are not retroactively reduced.
The bank now has 82 records across six families; updates increase from three to
six, while evidence trace remains one. No evaluated method has been called.

The three new questions explicitly pair issuer correction notices with their
original notice numbers and original board identities:

- 301042: repurchase-window wording, registered category `other`.
- 600568: projected share-structure table, `projected_share_structure`; no numeric
  table reference is introduced or certified by this task.
- 688016: second-scheme funding wording changes from own funds and/or dedicated
  repurchase loans to own funds and/or self-raised funds, category `other`.

Each asks whether the named correction itself establishes a new execution stage;
the answer is false. This does not assert that no real-world purchases occurred.
The full correction texts were inspected. These are source-comprehension tasks,
not yet a test of updating memory across time; they cannot demonstrate a memory
gain. All eligible documents at the next-day cutoff remain available equally.
Same-day publication order is not inferred.

Two existing natural-gap questions have AI-assisted semantic reviews of their
entire eligible source sets. For 603708, three older-scheme documents concern the
February 5 scheme and its February 6 first purchase, while the target is the
September 11 second scheme. Its supplied proposal provides no actual first
purchase date. For 600231, the March shareholder pledge-repo transfer termination
is not an issuer buyback; the target June 25 scheme's proposal gives no actual
first purchase date. Abstention is scoped to the supplied archive and target
scheme. The other 23 insufficiency candidates remain pending.

The five records are marked `source_checked` **silver**, with review ledgers,
source hashes, scope decisions and evidence. `human_reviewed` stays false; they
are not independent human gold. The remaining 77 records still require source
qualification. No whole-bank readiness or positive RAG/memory result is claimed.
The review script snapshots inputs and refuses to overwrite an earlier version.
The root `tests` directory passes 196 tests. Added checks reject unlinked
corrections and later evidence, and ensure review metadata stays out of public
method tasks. The owner-review page embeds all 444 reserved source texts and
uses a fresh bank hash for V4; personal confirmations from older banks are not
silently carried forward.

```powershell
python scripts/extend_reserved_source_review.py --out workspace/new-scoped-review
```

## Temporal diagnostics and positive review v5 (November 2)

`reserved-source-questions-v5-20261102` contains 91 cards: 32 source-checked silver
records and 59 pending records. All 17 existing historical-date questions have
AI-assisted checks of issuer headers, original-board clauses and explicit dated
first-purchase clauses with positive quantities. These are localized positive
evidence checks, not full-archive absence reviews. The high-confidence date
references remain unchanged from V4.

One **scheme identity** erratum is recorded for 600823 historical. The source
says the board and shareholder meetings occurred respectively on June 4 and
June 27, 2023. The correct original-board key is `600823_BOARD_2023-06-04`.
The first-purchase date remains July 10. The prior parser chose the later date
from the coordinated sentence. Only reference identity is corrected; evaluated
graph/memory code and prior method outputs are not tuned or rescored here.

The full January 30 proposal for 300200 supplies no actual first purchase date;
its natural archive-gap question becomes the third checked insufficiency case.
The other 22 negative candidates still need semantic review. Later February
sources cannot answer the January cutoff.

Three selected same-scheme episodes (301042, 301300, 600231) add nine cards:

- At the first-disclosure cutoff: latest disclosed stage plus first-purchase date
  and first-purchase shares.
- At the completion-disclosure cutoff: update stage while preserving those two
  historical facts.
- At the later cutoff: compute final cumulative repurchases minus first-purchase
  shares from the two named endpoint sources.

The named endpoint texts were read in full. Scheme identity and integer operands
are source-bound. All eligible intervening documents, including other schemes,
remain in the common source universe; earlier cutoffs cannot see later filings.
The final cumulative repurchase total is not the remaining account balance
(especially for 600231, where shares were already used in incentives).

These are **three selected started-to-completed episodes**, not nine independent
samples or a representative test distribution. They supply mechanism diagnostics
and do not establish an accuracy gain. Unchanged states, no-execution cases,
terminations and broader independent schemes are still needed. The original
180-opportunity schedule and its 101 unavailable slots remain unchanged.

`temporal_evaluation.py` and `scripts/score_temporal_episodes.py` score saved
responses only. Per-episode measures separate stale-state failures from loss of
historical facts, joint snapshot correctness and cross-source arithmetic. Missing
responses count as failures; duplicate answers and cross-episode card reuse are
rejected. Citation-source coverage is reported separately from semantic entailment.
The diagnostic scorer does not create a method run or certify general memory gains.

```powershell
python scripts/build_reserved_temporal_review.py --out workspace/new-temporal-review
python scripts/score_temporal_episodes.py --bank workspace/new-temporal-review --corpus path/to/corpus.jsonl --predictions path/to/saved-responses.jsonl --out workspace/episode-scores.json
```

The original 82 records are retained by ID (with the explicit identity erratum),
and all review ledgers and input hashes are versioned. No new API calls are made,
no source text is altered, and no whole-bank freeze is declared.
The root test directory now passes 200 tests. Temporal regression checks separate
stale states from lost history, enforce future-source exclusion and scheme
identity, reject duplicate predictions and count missing responses as failures.

## Positive-task source audit v6 (November 2)

V6 keeps 91 cards and adds 37 explicit positive-source reviews: 23 stage, ten
multi-scheme, three termination-decision and one two-scheme arithmetic task.
There are now 69 source-checked silver records; all 22 pending records are
insufficiency candidates requiring full eligible-source semantic review.
No independent-human review, new model comparison or whole-bank freeze is claimed.

Five scheme-identity errata preserve old values and exact replacement evidence:

| Question | Previous original-board key date | Correct date | Distinction |
| --- | --- | --- | --- |
| 301047 stage | 2024-02-19 | 2024-02-02 | board versus shareholders |
| 000785 stage | 2024-12-06 | 2024-11-20 | board versus shareholders |
| 002611 stage | 2021-09-22 | 2021-08-31 | board versus shareholders |
| 002812 stage | 2024-02-18 | 2024-02-02 | original scheme versus purpose amendment |
| 301063 update | 2024-10-09 | 2024-02-07 | newly approved stability scheme versus terminated older scheme |

The 301063 public query is explicitly retargeted to termination source
CNINFO_1221354626. The former query named the new stability proposal, which cited
an older termination and caused a scope conflict. Original query text, target,
proofs and new query/proofs are retained. Its termination decision date remains
October 9, 2024. Other errata leave execution labels unchanged. The evaluated
parser/graph/memory algorithms and existing method outputs are not modified.

Multi-scheme tasks additionally use an eligible, source-bound completion or
termination of the earlier scheme before fresh approval of the later scheme.
Those sources already belong to each supplied context universe; no unseen
documents are introduced. This supports separate schemes beyond just different
board dates. Source coverage references now include these added proofs; any
future scoring must name the V6 reference version rather than compare it silently
against older proof lists.

Stage labels remain the predeclared three-label **execution-history** taxonomy.
The STARTED records for 002759, 002970 and 300891 describe actual purchases before
termination; they do not assert that these schemes remain active. Lifecycle and
execution history are different axes. The other stage references retain explicit
completion or ongoing purchase evidence. This review does not redefine the
taxonomy or manufacture a new-method accuracy gain.

The inspected two-scheme 002812 counts are 1,469,800 and 7,238,804 actual shares;
their sum remains 8,708,604. Scheme identities, completion evidence and issuer
headers are retained alongside quantity spans. Positive source review is not
a general semantic-necessity certificate.

```powershell
python scripts/review_reserved_positive_tasks.py --out workspace/new-positive-review
```

The script records a fixed inspected inventory and rejects issuer/cutoff/evidence
mismatches. It is not an automatic factual classifier for arbitrary new records.
The root test directory passes 203 tests. The V6 delivery also checks a one-to-one
match between the 69 checked question IDs and 69 semantic-review ledger rows.
Those records cover 42 companies; card counts must not be treated as independent
scheme counts. The remaining 22 pending records span 22 companies.

## Full-text negative audit (November 2)

The existing authorized Qwen configuration was used for a separate source-audit
pass over all 22 pending natural-gap candidates. This is reference research, not
RAG/memory predictions, independent human review or a benchmark freeze. Each
request includes every eligible original text, the target board date and cutoff;
reference answers, family labels and source-qualification labels are withheld.

Two synthetic controls precede the company batch. The positive control correctly
identified the actual date but returned an ID-keyed source inventory instead of
the requested array. Strict validation stopped the initial run after one call.
The raw result was retained. A documented representation-only conversion and
regression test were added; the identical control response was reused without
another API request. The negative planning-only control then passed, permitting
22 company audits with two workers and no automatic retries.

There are 24 unique paid responses total: two controls and 22 company audits.
The second run has 24 records, one reused; do not add the duplicate retained
control again. Unique usage is 127,982 input and 9,491 output tokens.

Fifteen company audits pass strict structure and all verbatim-quote checks; seven
fail structure or quote checks, with nine unmatched quotations. Five reasoning
texts have wording flags such as inferring non-execution from future disclosure
duties; flags can overlap quote failures. These are triage flags, not automatic
factual judgments. A proposal does not establish a transaction date, but neither
does a future disclosure duty prove that no trade occurred.

All 22 remain **pending**. No new source qualifications or reference answers are
automatically adopted. Model agreement on insufficiency, controls and matching
quotes do not certify absence. The full raw audit, per-source roles, mismatched
quotes, provenance and a read-only original-text review page are retained under
`reserved-absence-audit-20261102`, `reserved-absence-audit-v2-20261102` and
`reserved-absence-followup-20261102`. The existing V6 bank remains current.

The root test directory passes 207 tests. Added checks cover complete source
inventory, fabricated quotes, representation-only normalization, answer-free
auditor inputs and illegal dates inside abstention responses. No further paid
retry is performed to chase a desired negative verdict.

## Negative citation/rationale review v7 (November 2)

V7 adopts the 22 full-context Qwen audits as explicitly model-origin silver
references after assistant review of the output scope, nine quotation repairs
and conservative rationale. It does **not** claim the assistant personally read
all 25 source texts in full, independent human review or certified factual truth.
The review ledger separates the full-text model reviewer from the assistant's
quotation/scope/rationale work. Future results must disclose that Qwen also
helped construct these references, especially when Qwen is the compared model.

The nine repairs are an inspected, source-specific whitelist: original page
markers, punctuation, omitted characters, an invented heading/leading word and
field wording. Exact source spans, hashes, original model quotations and repair
reasons are retained; raw responses and source texts stay unchanged. Unlisted
near-matches are rejected rather than fuzzily treated as verbatim quotations.
Source maps with matching redundant IDs are normalized; contradictory IDs or
unclear roles are rejected.

All 22 adopted explanations are restricted to inability to establish the actual
first-purchase **date** of the target scheme in the supplied archive at its
cutoff. They do not infer real-world non-execution, perfect filing compliance or
absence of all previous purchases. In particular, the earlier 2022 scheme in
002885 does not answer its 2024 scheme. Original model reasons remain in the
review ledger alongside the adopted rationale, including overstatements missed
by the earlier wording heuristic.

The 91 cards now have source-checked **AI silver** annotations, with 91 separate
provenance records and zero pending source annotations under this declared
standard. Human-reviewed/gold and formally ready counts remain zero. This
improves reference traceability, not a measured model score. No new API calls
or method outputs are produced in V7. The comparison protocol still must be
implemented and frozen; file/readiness checks cannot certify annotation truth.
The V7 readiness inventory reports no question-integrity errors, but keeps
`exploratory_run_ready=false` because no matched method protocol is declared.
The root test directory passes 210 tests; source-specific quotation repair
rejects unreviewed similar text and contradictory source inventories.

The `repurchase_stage` public enum was registered before reference generation,
using the established three disclosure-stage labels. Original pilot source/code
snapshots remain available. The initial template-construction root suite passed
189 tests; the V5 count is 200. These are software counts, not labels or model
evaluation scores.

## Reproduction and next work

```powershell
python scripts/build_reserved_source_questions.py --out workspace/new-source-questions
python scripts/check_benchmark_freeze.py --questions workspace/new-source-questions/questions-source-candidates.jsonl --out workspace/new-bank-readiness
```

Both commands are offline. The paid drafting runner additionally requires an
explicit `--live`; prefer inspecting the retained failure records to rerunning.

Next: review the remaining candidates' scheme scope and references, supplement missing
original sources for correction/termination/evidence joins, and record explicit
source exclusions. More independent, qualified schemes are needed to approach
the original size target. Freeze qualified questions, reference versions and the
matched protocol before calling any compared method on the reserved set.
