# Matched typed-disclosure executor

Status: development infrastructure and one-question end-to-end preflight,
November 2, 2026. No reserved inference or memory-gain conclusion.

## Common input and methods

`matched_disclosure.py` prepares the same public typed task for five methods:
full text, character-bigram TF-IDF RAG, append memory, current flat memory and
graph-assisted retrieval. All methods access the same eligible source universe
and next-day availability cutoff. Public named announcement IDs support direct
lookup in every retriever; fixed Chinese field aliases address English-query /
Chinese-body mismatch. RAG uses 1,200-character chunks, 150-character overlap
and at most 16 selected chunks, with named-source opening chunks available.

Full text supplies complete eligible filings when they fit. Overflow is explicit;
no silent truncation or provider substitution occurs. RAG and memory methods
include original source passages. Machine memory claims are clearly marked
unverified, with original quotations and source IDs. Actual citation validation
uses the sources supplied in that particular prompt, not the entire archive.

The shared evidence ceiling is 48,000 serialized Unicode characters, excluding
the common task/schema/system overhead. Memory notes have an 8,000-character
ceiling (and at most one-third of smaller budgets). Relations also consume the
same evidence ceiling. This is **not a tokenizer-based equal-token experiment**;
actual provider token usage and context sizes must be reported separately.
Methods can use different fractions of their ceiling. Full-text overflow and
build failures must be distinguished from factual errors and reported by method;
future efficacy analysis should also use a predeclared common-fit subset.

## Shared source-only observations

One Qwen extraction pass per source supplies all three memory representations.
The extraction prompt sees one original filing and a fixed public field contract;
it sees no question, reference answer, annotation proof or target answer date.
Fields that depend on question-relative scheme ordering are excluded from
single-document extraction. Other original-board candidates and evidence are
machine claims, not certified unique entities or semantic entailments.

Each observation has a stock/scheme/field key, typed value, source ID, source
availability, identity quote, supporting quote and text hash. Admission checks
schema, source spans and date consistency. When the model identity quotation is
invalid, the existing source-only board parser can supply an identity span only
if its initial-board candidate dates uniquely match the claimed date. This
fallback is recorded explicitly and inherits that parser's limitations; it is
not a manual identity correction or an independent semantic certificate.

Additional development checks reject planned/hypothetical share quantities,
money values absent from quoted yuan amounts and non-execution inferred only
from a future implementation period. These are conservative checks, not a
general entailment judge. Rejections and raw model responses remain visible.

Append memory retains eligible observations. Current flat memory keeps the latest
observation for each scheme/field while retaining all same-day ties rather than
inventing intraday order. Historical fields remain separate from changing
execution fields. Graph retrieval starts from public named sources or the common
lexical top source and traverses source/scheme/observation relations; it never
uses the reference scheme key. The graph then reranks eligible evidence and
supplies relation hints alongside current observations and originals.

Incomplete extraction blocks the affected memory answer slot. It never silently
becomes a RAG answer or an empty-memory success. Full archive extraction can be
performed ahead of answering because each source is extracted independently;
answer-time filtering excludes every later source and observation.

## Runner and reproducibility

`scripts/run_matched_development.py` implements:

- `extract --live`: explicit Qwen source extraction, no retries/fallback.
- `readmit --memory <retained-run>`: offline replay under a new admission version;
  raw responses are unchanged and no API call is made.
- `prepare`: offline construction of all five prompts and failure slots.
- `run --prepared <directory> --live`: answer calls only for prepared slots.

The runner accepts development corpus and development questions only; it cannot
send the 91 reserved cards. Source, question, memory-artifact, prepared-prompt
and code hashes are sealed in manifests. Answer calls reject changes in source
hashes, code, model, provider host or prepared memory. Source snapshots accompany
each phase; older preflight manifests remain immutable.

The full development inventory has 23 questions and 108 distinct eligible sources.
Before shared extraction there are 46 prepared baseline answer slots and 69
blocked memory slots. The two-source preflight unlocks one question's three
memory slots: the latest inventory has 49 prepared and 66 blocked slots out of
115. These are readiness counts, not model scores.

## Observed preflight and cost

The selected plumbing case is `DEV_FIRST_PURCHASE_300415`, using two eligible
development filings. Initial extraction produced ten proposed observations;
all failed the original strict identity admission. Raw outputs included an
ellipsis/undated identity quote, a planned quantity presented as actual shares,
money/share-unit confusion and non-execution inferred from a plan deadline.

On development data, admission was revised as described above and the same two
responses were replayed offline. Four observations were admitted and six rejected.
No second extraction call was used to obtain preferred answers. The original
two failed source records and the revised records remain separate.

All five answer calls then parsed and matched this one question's draft reference.
This only demonstrates an end-to-end path. There is no statistical comparison,
no held-out result, and no demonstrated advantage of memory. In this case append
and current memory have identical notes; state replacement must be evaluated on
the separately designed temporal episodes and broader independent schemes.

There are seven unique paid calls: two extraction and five answer calls. Total
usage is 53,585 input and 1,898 output tokens. Readmission reuses the extraction
responses and must not be billed or counted again. Extraction uses 7,842 input /
1,168 output tokens; answers use 45,743 input / 730 output tokens. Report shared
build cost once and explicitly allocate cold/warm cost per method in a real study.

For this small archive, evidence sizes were 10,972 characters for full text,
13,854 for RAG, 15,511 for append/current and 16,154 for graph retrieval. Chunk
overlap and repeated metadata make RAG longer than full text here. No token or
latency saving is claimed. Tune redundancy on development data before freezing
the reserved protocol; do not tune it on reserved method outcomes.

The root test directory passes 218 tests. Added checks cover reference poisoning,
future exclusion, named-source parity, same-day conflicts, scheme isolation,
blocked memory, explicit overflow, numeric serialization, invented quotes and
planned quantities. The seven live calls are a plumbing preflight, not a substitute
for the full development study. The preflight used an earlier extraction prompt;
formal extraction must use one fixed prompt/version for every source rather
than silently mixing preflight observations into a purported uniform run.

## Next milestone

Complete a uniformly versioned, blind shared extraction for the 108 development
sources, run all 23 development tasks with failures preserved, and review cost,
coverage and semantic errors. Freeze the final prompt/retrieval/admission/scoring
protocol and source/reference hashes before any reserved answer call. The V7
91-card reference bank remains unchanged and is AI silver, not independent human
gold. Its imbalance and three selected temporal episodes remain limitations.
