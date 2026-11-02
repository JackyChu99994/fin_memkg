# Diverse original-announcement acquisition

Collection date: 2026-10-31. This is a source candidate delivery, not a scored
benchmark or a new human reference set. Existing study results are unchanged.

## Acquired sources

- 80 new companies, excluding the previous 40-company corpus and known pilot codes.
- 599 original CNINFO PDFs, 599 extracted full texts and 2,861 pages.
- 599 unique PDF hashes; PDF and text hashes verified, no missing extracted anchors.
- Zero recorded company/download errors and zero text extraction failures.
- Zero model calls, reviewed documents or evaluation-ready new questions.

Company acquisition strata are **title-based leads**, not verified event labels:
22 completion, 20 correction/revision, 20 multiple-scheme and 18 termination.
The initially planned 20 termination-company leads were not available in the
eligible observed search pool; two remaining slots came from completion leads.
Do not infer complete market coverage or that every lead belongs to one scheme.

## Source and sampling boundaries

Official CNINFO announcement searches cover anchor disclosures in 2023-2025.
Seven recorded search terms are capped at 12 pages each. Saved responses contain
1,743 metadata rows before cross-query deduplication; the frozen title-qualified,
new-company pool contains 1,028 unique announcement IDs. Several searches hit
the page cap; this is a purposive observed challenge pool, not exhaustive or
random market sampling. Check the raw audit rather than treating reported totals
as downloaded/qualified sources.

For each selected company, search repurchase context in 2022-2025, preserve the
chosen anchor and select nearby title-qualified reports, proposals, first buys,
progress and updates, up to nine PDFs. Proximity is only an acquisition heuristic.
Missing predecessors, different schemes and documents outside that window still
require semantic checking. Title filters exclude restricted-share incentive
cancellations, legal opinions and other obvious mismatches but cannot certify
scheme identity. Original metadata, source URLs and raw query pages are retained.

## Versioned company splits

The first provisional global-hash split had no termination lead in development.
Before any annotation or model call, split v2 switched to hash ordering within
each acquisition stratum and round-robin development allocation. Company/source
selection was unchanged. Original selection and corpus are retained with hashes.

| Candidate stratum | Development | Reserved |
| --- | ---: | ---: |
| Completion | 5 | 17 |
| Correction/revision | 5 | 15 |
| Multiple scheme | 5 | 15 |
| Termination | 5 | 13 |
| Total | 20 | 60 |

Use **`corpus-split-v2.jsonl` and `split-v2.json`** for subsequent work.
`corpus.jsonl`, `selected-companies.json` and the company snapshots preserve the
provisional acquisition-time split. Do not silently mix these versions.
Reserved sources should be annotated independently of method predictions and
must not be used to tune extraction, retrieval or prompts.

## Local artifacts and next gate

Files are under the ignored module directory
`data/experiments/diverse-announcements-20261031/`:

- `protocol.json`, `search-audit.json`, `searches/`: acquisition protocol and queries.
- `candidate-pool.json`, `selected-companies.json`: frozen leads and selection.
- `companies/`: original PDFs, text, official metadata and context snapshots.
- `corpus.jsonl`, `corpus-split-v2.jsonl`, `split-v2.json`: versioned source corpus.
- `scheme-review-queue.jsonl`: 80 blank company/scheme review records.
- `summary.json`, `integrity-validation.json`: counts, source integrity and limits.

Next: qualify scheme identities and source sufficiency on development companies;
record missing sources and acquire them without silently replacing difficult
cases. Build task-specific references under the
[expanded protocol](expanded-benchmark-protocol.md). Freeze questions, reference
version and all inputs before evaluating reserved companies. Do not describe 599
documents as 599 questions or as independent labeled events.

## Reproduction

Source collection uses standard-library HTTP plus `pypdf` for extraction; the
delivery was extracted with the bundled PDF runtime. A fresh collection uses:

```powershell
python scripts/collect_diverse_announcements.py --out workspace/new-source-collection --target 80
python scripts/finalize_diverse_collection.py --collection workspace/new-source-collection
```

Use `--resume` only to continue that same saved acquisition. It preserves completed
company snapshots and does not conceal failures or repair missing files. Re-querying
the live service need not reproduce identical response pages. The delivered raw
snapshot is the reproducible acquisition evidence; it requires no API/model key.
