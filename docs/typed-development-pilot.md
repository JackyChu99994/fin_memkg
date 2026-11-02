# Real Qwen typed-task development pilot

Date: 2026-11-01. Two full-context development passes, 23 calls each, used the
existing root Qwen configuration (`qwen-plus`, temperature zero). These are not
RAG/memory comparisons or independent held-out results. References are unchanged
assistant source-anchored development drafts, not independently reviewed gold.

## Frozen passes and findings

| Pass | Prompt/scoring snapshot | Calls | Parsed JSON | Schema valid | Strict draft matches | Field matches |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Initial pilot | typed-disclosure-v2 | 23 | 23 | 0 | 0 | 62/69 |
| Clarified development regression | typed-disclosure-v3 | 23 | 23 | 22 | 19 | 65/69 |

The initial public format used `CODE_BOARD_YYYY-MM-DD` without explicitly saying
to replace CODE with the actual stock code. Every response copied CODE literally.
That is an interface-design failure, not evidence that every factual answer was
wrong. The initial raw responses, prompts, scores and frozen source remain.
Seventeen initial responses had the reference board-date suffix despite their
invalid prefix; this diagnostic does not repair them into passing answers.

V3 supplies only the known stock-code prefix, clarifies original board versus
disclosure/shareholder/amendment dates, specifies flat fields and exact source-ID
format, and explicitly names which report IDs the comparison query asks about.
It never supplies their answer dates or reference values. It also normalizes a
quoted table-column label without erasing the wrong original unit. That narrow
scoring change affects two initial field slots: rescoring BOTH original outputs
offline with common v3 yields 64/69 versus 65/69. Strict matches remain 0 versus
19. Therefore the table is not a clean estimate of factual capability improvement.

The second pass has four strict nonmatches:

1. 003010 and 688023 correctly map both scheme approval dates, but choose the
   earlier common target identifier instead of the protocol's later-scheme target.
   These are metadata-selection failures, not incorrect two-scheme mappings.
2. 300919 provides the correct amounts under a nested category object instead of
   the declared flat `field`, `before` and `after` slots. Strict schema fails;
   presence of correct numbers in another shape is recorded, not silently fixed.
3. 301322 names the sponsor opinion as the primary issuer source, despite also
   stating that an opinion is auxiliary. This is a substantive source-role error.

Do not describe all four as financial reasoning failures, and do not describe
19/23 as validated population accuracy. The development set was used for debugging.
The old 58-question reserved results and 556-call study are unchanged.

## Calls, costs and preservation

Both passes together made 46 physical calls. Reported usage is 670,397 input
tokens and 6,926 output tokens. All 46 parsed responses report `qwen-plus` and
stop completion. No automatic retry, model switch or rule substitution occurred.
Provider credentials never enter manifests, source snapshots or archives.
No monetary price is inferred from token counts.

Every pass saves its pre-call plan, source/input hashes, raw responses, provider
response IDs/models, finish reason, usage, scores and scoring-ready exports.
API failures or malformed outputs remain failures; they are not dropped.
There was one planned second regression after interface corrections, not a hidden
retry of selected failed questions. No third live run was used to chase a full score.

## Reference-free admission hardening

`repurchase_admission.py` consumes only the PUBLIC task and model response. It
does not read reference answers. On the second pass it quarantines two records:
the nested field-shape error and the auxiliary opinion incorrectly designated
as primary issuer evidence. It retains 21 records only as machine claims pending
semantic review, never as human-verified facts.

For comparison tasks it derives both scheme/source links from the supplied
mapping instead of making the graph depend solely on one model-selected target.
The two target-selection disagreements remain warnings. Raw target identifiers
and original 19/23 scores are not overwritten. This is a post-pilot engineering
guard, not independent evidence of improved accuracy. The projection is an
inspection artifact; it does not write these claims into the existing app graph.

## Validation and artifacts

Twenty-six focused typed-evaluation cases and six admission cases pass. The last
whole-root run passes 162 tests. An earlier whole-root run had a transient existing
market-cache test failure (zero returned rows). The isolated case and 30 bounded
mocked repetitions passed, followed by the whole-root pass. Its root cause was
not reproduced or claimed fixed; no market implementation changed in this phase.

All new files are under the ignored module experiment directory:

- `typed-qwen-development-pilot-20261101`: initial pass and frozen code.
- `typed-development-contract-v3-20261101`: clarified public prompt pack.
- `typed-qwen-development-pilot-v2-20261101`: the second pass and frozen code.
- `typed-pilot-review-20261101`: original/common-v3 scores, error classification,
  admission projections, raw-response input hashes and admission source snapshot.

Offline review uses `python scripts/review_typed_pilot.py --out workspace/new-review`.
The live runner requires an explicit `--live`, a fresh directory and exact prepared
prompt matches. Prefer inspecting saved outputs to repeating paid calls.

Next: complete reference/source-role review and decide which metadata should be
derived deterministically; then build separately qualified reserved tasks and
freeze a matched RAG/memory protocol. Do not tune on the 60 reserved companies.
