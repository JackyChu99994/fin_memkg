# Expanded benchmark design: sources, time and scheme identity

Status: design specification, 2026-10-31. No new test labels, source collection or
model runs are certified by this document. Freeze an instantiated manifest before
inference; this document alone is not a preregistration of a completed dataset.

## Research question and sampling

Test whether structured temporal memory improves factual financial disclosure
research relative to strong retrieval, and under which task/cost conditions.
Neither superiority nor a positive outcome is an acceptance condition.

The planning target is 80 new companies and approximately 240 questions, subject
to source qualification and review capacity. This is an acquisition target, not
a statistical power calculation or sufficient-sample guarantee. Report realized
company, scheme, document and question counts separately.

All 40 companies from the inspected corpus, previous development companies and
other manually inspected examples must be excluded from the new independent
test pool. Existing cases remain useful for development and regression only.
Keep every scheme of a company in one split. Use a recorded seed/hash ranking
for company-level allocation, targeting 20 development and 60 reserved companies.
Preserve the complete candidate list, acquisition window, deduplication rules,
rejections and shortages. Strata are selected from source properties before any
method prediction, not from which method failed. Do not claim population-random
or market-wide sampling from this purposive challenge set.

## Task families

Target approximately 40 questions per family; show all shortages and overlaps.
Do not manufacture three questions for each company solely to meet a total.

| Family | Required information | Output and principal check |
| --- | --- | --- |
| Ordinary stage recognition | Qualified same-scheme announcement(s) | Disclosed execution stage + supporting IDs |
| Historical cutoff | At least two different disclosure times | State as of cutoff; no future-source use |
| Multiple schemes | Same company has distinct scheme approvals | Correct scheme attribution; no cross-scheme merge |
| Update, termination or correction | Explicit subsequent disclosure and its predecessor | Relation between statements; retain what was true historically |
| Evidence trace | Multiple independently necessary source facts | Required source set and semantic relations; alternative valid sets allowed |
| Insufficient evidence | Document collection genuinely lacks the requested fact | Calibrated abstention with missing-information reason |

Do not call a two-source question multi-hop merely because it has two citations.
Specify the necessary joins, such as company -> scheme -> observation -> source,
and verify that all necessary facts are present. Include single-source controls.
Source titles containing "cancellation" do not establish repurchase execution
completion. A planned end date is not actual completion. Termination is distinct
from completion. Changed factual statements are not automatically contradictions.

Stage questions must cover no-execution-disclosed, started and completed in the
reserved pool. Termination/correction questions require explicit additional
fields or task-specific labels; do not squeeze them into the old three classes.
The lifecycle ontology and output validation must be fixed on development data.

## Reference construction and review

For each question preserve: company and scheme IDs, query and cutoff, eligible
corpus IDs and hashes, required source spans, answer, acceptable alternative
evidence sets, and status. Record scheme approval date and how each follow-up
was linked. Use next-day availability for date-only sources consistently; retain
all same-day eligible disclosures. Synthetic distractors or truncated evidence
sets must be separately tagged; never misrepresent them as naturally missing.

AI drafts, programmatic source adjudication, owner self-review and independent
double annotation are distinct tiers. No tier is promoted by file naming. A
reviewer should form an answer before viewing the draft and without method
predictions. Record disagreements, adjudication and uncertainty. Unresolved
questions remain visible but outside the primary scored set. Do not silently
filter errors after seeing model results. Reference errata require a versioned
ledger and offline rescoring of all methods without regenerating responses.

## Matched comparison

Use one declared Qwen model/version/configuration, identical underlying eligible
sources, fixed prompts and no silent provider fallback. Include full text where
it fits, tuned lexical RAG, append memory + retrieval, current flat memory +
retrieval, and graph-assisted retrieval. Tune retrieval and context budgets on
development companies only. Record overflow/truncation rather than silently
giving baselines less evidence. Preserve the old graph-format variant as a
separate ablation; graph-assisted retrieval is a different implementation.

Share blind source extraction between memory variants to isolate representation.
Never inject reference answers, proof spans or future documents into construction
or retrieval. Graph-assisted retrieval may use scheme/time/source relations to
select evidence, but any performance claim must be against a strong RAG under
declared budgets. Add a flat-state control to distinguish state maintenance from
graph relations. Validate the full input manifest before live calls.

Run offline protocol/schema checks, then a small development pilot for cost and
failure diagnostics, then freeze the reserved run. Do not treat pilot regression
as held-out accuracy. Additional independent runs may estimate model variability
if resources permit, without tuning on reserved results.

## Metrics and acceptance

- Task-specific factual correctness and macro averages by task/class/company.
- Scheme attribution errors and future-source violations.
- Citation validity, sufficiency and relation/path correctness, allowing valid
  alternative evidence sets rather than exact designated-source matching alone.
- Abstention accuracy and answer coverage, reported together.
- Input/output tokens, elapsed time and failures; count construction once per
  method deployment and show amortized cost over 1, 5 and 20 real queries.
- Paired company-level uncertainty and discordant outcomes. Question count and
  software-test count must not be interpreted as independent company samples.

Do not claim a graph benefit from artificial path metrics alone; factual quality
and practical evidence access matter. Do not hide lifecycle-class shortages in
aggregate scores. The project is acceptable with a reproducible negative or mixed
result, an operational source graph and transparent extraction/error analysis.

## Acquisition gap check

Run `scripts/plan_stage6_benchmark.py --out workspace/benchmark-inventory` to
inventory existing title leads without a model or network call. These are not
new labels. Existing scheme-identity exceptions are development cases, not fresh
evidence. New original-source acquisition and human review remain outstanding.
