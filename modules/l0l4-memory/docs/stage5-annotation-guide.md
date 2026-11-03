# News annotation protocol

## Scope and unit

One unit is the exact `text` stored in a corpus record. The provider may return a
search excerpt rather than a full article. Label only that text, including its
headline. If you open a source and decide that more context is necessary, create
a new corpus version with that additional text and rebind its annotations to the
new SHA-256. Do not silently label facts that are absent from the supplied input.

`stock_code` describes the search used to retrieve the item. It is not proof that
every statement concerns that company. Several records may report the same
underlying event. Group related stories when constructing train/test splits or
estimating uncertainty. Do not randomly distribute copies across partitions.

## Label fields

Every event needs `source`, `source_type`, `relation`, `target`, `target_type`, and
`status`. Entity types are the existing module's Company, Industry, Product, and
Event categories; serialize their existing Chinese schema values. Relations are
the existing six labels: positive event, negative event, supplier, customer,
competitor, and industry membership. Preserve direction: supplier A to customer B
is different from supplier B to customer A.

Use an entity name explicitly supported by the text. An event target may be a
short, consistent description of an explicitly reported event, such as a share
repurchase. Record its supporting span and any canonical-name decision in
`notes`. Do not create a numeric entity for an amount or percentage. Do not infer
a customer, supplier, or competitor solely from general financial knowledge.

Positive or negative event labels describe the stated economic implication,
not a prediction of realized share returns. A proposal, expectation, completed
transaction, and cancellation are different facts. A proposal does not become
completed merely because a headline sounds confident. When the distinction is
material but the schema is too coarse, record it in the notes and retain it for
error analysis. Do not manufacture a status beyond the text.

Mixed financial disclosures can support more than one event. For example, a
fall in domestic market share and an increase in overseas shipments should be
preserved separately if both are explicit. A return direction label requires
additional task definition and is not inferred from these extraction labels.

## Empty labels and ambiguity

Pure price/volume tables, fund-flow rankings, financing balance lists, irrelevant
items, and unsupported investment conjectures receive an empty event list under
the module's L0 policy. This does not mean they lack all financial information;
it means they are outside this extraction task. Do not turn a price decline into
a causal negative event without an explicit reason in the input.

If an excerpt names no identifiable counterparty, do not invent one. An unnamed
subsidiary cannot be given a name absent from the text. Mark ambiguous cases in
notes and have a second reviewer adjudicate them. Record the decision before
viewing model predictions to reduce evaluator bias.

## Review procedure

1. Read the frozen text and check its source URL and date.
2. Annotate independently before inspecting model outputs. AI proposals are
   suggestions, not gold labels; correct or discard them as needed.
3. For each relation, record an evidence span or a concise justification in notes.
4. Enter a reviewer identifier and mark the item reviewed only after checking it.
5. Have a second person independently annotate at least a subset. Compute
   agreement on directed relation sets before adjudication; retain both versions.
6. Resolve disagreements, freeze the final corpus and labels, and save hashes.

The annotation tool's review flag records a user assertion. It does not verify a
person's identity, independence, or the truth of the underlying source. The
report must describe the actual annotation process, not merely the presence of
these flags. Do not call assistant-created labels human annotations.

## Measurement

The scorer reports micro exact-match P/R/F1 for typed entities, directed triples,
and triples with status. A wrong relation is both a false positive and a missed
gold relation. Missing facts in failed responses remain false negatives. A
document with no gold facts and no predictions has undefined per-set F1, not
perfect F1; exact document accuracy captures correct rejection separately.

Report positive/noise composition alongside aggregate metrics. A noise-heavy
collection can make document accuracy appear strong while relation recall is
poor. Also report schema rejections and raw relation precision so validation
cannot hide malformed or invented candidate relations.
