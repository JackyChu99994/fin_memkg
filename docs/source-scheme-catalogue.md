# Source-bound development scheme catalogue

Date: 2026-11-01. This is a read-only integration and provenance feature, not a
new model evaluation. No new model call or reference promotion occurred.

## Source-driven identities

`repurchase_catalogue.py` derives candidates from original development sources,
without question answers or the model's chosen common target identifier. A
candidate ID includes a source anchor, rather than assuming company plus board
date uniquely identifies an event. Same-company/same-day roots remain separate
unless a unique cited proposal number, matching explicit original board date and
compatible phase support a candidate alias. Aliases remain reviewable, not truth.

Initial approvals are kept separate from amendments and termination decisions.
A dated deadline cannot jump across a sentence or another date to become a board
approval. Amendments, opinions and employee-plan disposal do not create initial
scheme roots. Ambiguous/missing dates remain unresolved, not guessed.

For historical use, filter all documents by next-day availability FIRST, then
build candidates and aliases. Future sources cannot introduce historical links
or canonical anchor IDs. An all-source catalogue is a snapshot, not permission
to reuse all its associations at an earlier cutoff.

The development snapshot contains 158 documents, 43 source-bound candidate
groups and 174 candidate links, with five citation-supported alias candidates.
Four primary documents lack a unique qualifying date under the conservative
parser. These are not certified counts of 43 distinct real-world schemes.

## Actual comparison cases

The two saved comparison responses already mapped both source dates correctly,
although their common target selected the earlier scheme. Rebuilding catalogues
from each public question's eligible sources resolves all four source/date claims
to their own source-bound candidates:

- 003010: CNINFO_1219009876 / 2024-01-26 and CNINFO_1219096303 / 2024-02-05.
- 688023: CNINFO_1215567109 / 2023-01-10 and CNINFO_1217417498 / 2023-07-28.

Both links can therefore be inspected independently of the chosen common target.
Raw model outputs and original 19/23 strict scores are unchanged. These known
development cases are regression evidence only, not a measured accuracy gain.

## Original application integration

Start the root application and select **Evidence research**, then the new
**Development scheme links** tab. Choose a company and evidence cutoff to see
source-bound candidates, graph links, original PDFs, approval quotations,
unresolved files and alias rules. Download the exact candidate snapshot if needed.

The prior **Historical study** tab remains available. The new view only reads
development sources; it makes no API call and writes no verified facts to either
the legacy thesis graph or the historical state graph. Candidate/uncertainty labels
are visible in the interface.

## Reserved readiness

`scripts/check_benchmark_freeze.py` verifies the source snapshot and inventories
the separately reserved pool. Its initial snapshot reports 60 reserved companies and
444 source documents, **zero qualified new questions** and no fixed five-method
protocol. It prepares 60 blank reference-review queues; it does not certify that
the dataset is ready or create a freeze manifest.

The [subsequent bank-construction snapshot](reserved-question-bank.md) provides
79 unqualified source-bound candidates; qualified new questions remain zero.

Exploratory readiness with qualified, declared silver references is distinct from
an independently reviewed human-gold claim. The checker validates declarations,
field/proof integrity, cutoff/source scope and protocol completeness; it cannot
authenticate human review or prove semantic correctness. It does not require a
positive memory outcome. Family coverage, prompt/source/reference/scoring versions,
retrieval/context parameters, blind memory construction and failure rules must be
declared before any reserved comparison.

## Local outputs and checks

- `development-scheme-catalogue-20261101`: catalogue, two case bindings, unresolved
  sources, source code snapshot and counts.
- `reserved-freeze-readiness-20261101`: readiness report and 60 blank queues.

Both directories are under the ignored module experiment data path. The two
source comparison cases use no reference values to resolve their scheme links.
The complete source corpus hash is retained for reproducibility.

Nine focused catalogue tests, six readiness tests and the original/new UI tests
pass. The root suite passes 178 tests. Software checks do not establish candidate
identity truth, financial accuracy or held-out performance.

```powershell
python scripts/build_development_catalogue.py --out workspace/new-catalogue
python scripts/check_benchmark_freeze.py --out workspace/new-readiness
python -m streamlit run app.py
```

Next: construct and qualify the reserved source-bound question/reference records
under the fixed task design, preserve exclusions and shortages, and freeze all
inputs before the matched five-method run. Do not count source files as questions
or relabel the new AI drafts as independently human annotated.
