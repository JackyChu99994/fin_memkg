# Expanded candidate corpus and reference review

Collection date: 2026-10-30. This expansion follows the owner's request for a
larger evaluation. It replaces the earlier three-company expansion target;
it does not change or overwrite the completed BYD development experiments.

## Size actually acquired

| Partition | Distinct companies | Original PDFs | Extracted documents |
| --- | ---: | ---: | ---: |
| Development | 10 | 47 | 47 |
| Reserved test | 30 | 149 | 149 |
| Total | 40 | 196 | 196 |

The corpus contains 679 PDF pages, 196 unique PDF hashes, and 196 unique full-text
hashes. There were no extraction failures and no company overlap between the
two partitions. Thirty-eight companies have five documents each; one has four
and one has two. Missing coverage is retained rather than replaced by favorable
results. The files are under
`data/experiments/lifecycle-expanded40-20261030/` and are ignored by Git.

These are **forty company-level candidate groups**, not yet forty verified
independent schemes or 196 independent test cases. Later disclosures must be
checked against the initial scheme. The group counts will not be relabeled as
verified cases merely because a model generates an answer.

## Selection fixed before inference

The official CNINFO historical query returned 1,530 metadata rows for the
calendar-2024 repurchase-report search. All 51 requested page responses are saved.
An integrity audit found 15 overlapping rows: there are 1,515 unique announcement
IDs, while reported totals varied between 1,529 and 1,530. Exhaustive search
coverage is therefore not established. `collection-deviations.json` records this
protocol deviation. Selection is a frozen sample of the observed search pool,
not sampling from a proven complete universe. Assignments are retained without
reference to future effectiveness results.
Initial report titles are filtered for repurchase reports, excluding explicit
amendments, summaries, English versions, restricted-share forfeiture reports,
and known development companies. One earliest candidate report per company is
retained before ranking companies by SHA-256 of the fixed seed and security code.
The first forty ranked companies are selected, with ranks 1-10 assigned to
development and 11-40 assigned to reserved test. PDF contents and model answers
did not determine that assignment.

For each company, download the initial report plus the first four subsequent
title-matching progress/result disclosures through 2025-03-31. This is a
candidate retrieval rule, not proof of a common scheme. Full-source review must
verify scheme identity and actual original approval year. A report published in
2024 can describe an earlier scheme; such cases must be explicitly adjudicated.
No replacements after effectiveness inference are permitted.

Known-company exclusions include BYD and every company previously used in the
forty-excerpt or historical-pilot development material. The corpus is a fixed
sample from the search results, not a representative sample of all listed firms.
It currently covers repurchase matters, not all financial-event families. The
forty-company pool is not a random sample of all financial events.

## Provenance and integrity

Original PDFs come from `static.cninfo.com.cn`. Query responses retain official
announcement identifiers, titles, dates, company codes, and original URLs.
Full texts include page markers. PDF and text hashes are recorded per document.
`integrity-manifest.json` hashes 448 input/provenance files and checks group
separation and duplicate hashes. This guarantees local file consistency, not
semantic correctness of inferred state or first-publication timestamps.

Date-only filings will be conservatively admitted the following calendar day
at 00:00 Shanghai time. Underlying transaction or board-meeting dates must not
be substituted for public availability. No future returns or inherited return
labels are used for collection, splitting, reference drafting, or state scoring.

## Reference drafting and remaining gate

The separate reference job reads the initial report and each current filing.
It has no access to evaluated-method predictions, method scores, or market
outcomes. It drafts scheme identity, original approval year, purpose,
repurchase stage, share-cancellation stage, and explicit abandonment information.
Source quotations are checked against the provided texts. Mismatches and
uncertainty are retained for adjudication; a quote match is not entailment proof.

Qwen Plus generates these drafts. Because the evaluated systems also use Qwen,
the drafts are not independent human ground truth. All new records remain
`ai_draft_pending_user_review`. The owner's earlier approval of forty news
excerpts does not approve these documents. A browser review page accompanies
the drafts with source links, field values, evidence, and validation flags.

The completed batch produced 196 drafts. Eighty-seven have matched quotation
spans and 109 require source-span adjudication. Matching a quote does not establish
correct scheme identity or state entailment; all 196 remain unreviewed.
The initial batch made 196 calls, including one API timeout. That item received
one explicitly recorded retry with an identical prompt hash and the same model.
The initial failure is preserved. There are 197 attempts in total and no remaining
failed documents in the merged draft file. Provider-reported usage is 1,174,474
input and 140,086 output tokens; the timed-out attempt has unknown usage and may
still be billable. No effectiveness-evaluation calls are included in this job.

Use `references-ai-draft-final.jsonl` and `reference-review.html` as the current
merged drafts and read-only review index. The initial reference file, initial
HTML index, per-item call records, retry records, and both summaries remain
separate and unchanged. `integrity-final.json` records the final artifact hashes.
Nineteen draft development cutoffs were prepared with an explicit 28-item
exclusion audit, but were not evaluated. These filtered drafts are not a
representative performance sample and are not the reserved test set.

The reserved test partition has not been used for effectiveness inference.
Do not tune the memory system to its draft labels. Only reviewed, frozen,
source-grounded references with confirmed scheme identities can support a
formal held-out comparison. Report any exclusion counts and reasons before
inference. Keep company/whole-scheme separation for uncertainty estimates;
multiple dates within a scheme do not create independent events.

## Commands

Run from the module directory, using a new output directory for a new collection:

```powershell
../../.venv/Scripts/python.exe -m experiments.expand_lifecycle --out data/experiments/expanded-new --observed-search-pool
```

The explicit observed-pool flag records incomplete search coverage if official
pagination overlaps. Without it the current collector stops for inspection.
Text extraction requires `pypdf` and uses `--extract-only` on a downloaded,
not-yet-extracted collection. Existing corpora and review forms are not overwritten.
The bundled runtime supplied that dependency for this collection.
Reference drafting is a separate paid-model step, not an accuracy evaluation:

```powershell
../../.venv/Scripts/python.exe -m experiments.draft_expanded_references --corpus data/experiments/expanded-new/corpus.jsonl --out data/experiments/expanded-references-new
```

Collection and reference scripts record source hashes and per-record failures.
The isolated software suite currently passes 87 tests; these checks are not
eighty-seven real evaluation cases.

## Review and evaluation entry points

The generated `reference-review.html` provides a read-only index with original
source links and flags. For corrections and explicit per-record review, use:

```powershell
../../.venv/Scripts/python.exe -m streamlit run experiments/review_expanded.py -- --corpus data/experiments/lifecycle-expanded40-20261030/corpus.jsonl --references data/experiments/lifecycle-expanded40-references-20261030/references-ai-draft-final.jsonl --save data/experiments/lifecycle-expanded40-reviewed/references.jsonl
```

The editor preserves original drafts and requires a reviewer identifier, a source
check confirmation, and valid supporting spans before saving a reviewed record.
Unknown scheme identity can be retained explicitly for exclusion; it is not
automatically changed to a correct answer.

`experiments.prepare_expanded_episodes` prepares dated questions and an exclusion
audit. It refuses unreviewed references for the reserved test partition.
`experiments.run_expanded_comparison` freezes the inputs and source hashes before
same-model calls, counts failures in denominators, and reports per-group and
macro-group accuracy in addition to cutoff-level accuracy. Draft overrides are
limited to development. Actual formal test inference has not run.
