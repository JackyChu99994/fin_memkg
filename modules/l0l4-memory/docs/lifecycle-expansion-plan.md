# Prospective lifecycle expansion plan

Superseded in scope by the owner's subsequent request to expand: see
[the forty-company collection](expanded-corpus.md). This original three-company
plan is retained as a historical record; no results are silently reassigned to it.

Frozen selection plan: 2026-10-30, before collecting or scoring the additional
chains below. The BYD chain is development material and is excluded from any
new-chain effectiveness comparison.

## Fixed collection rules

- Company order: 300308, 300502, 600519. These are the three non-BYD companies
  in the existing historical price subset; no selection uses realized returns.
- Search official CNINFO disclosures for each company's first newly approved
  ordinary-share repurchase scheme disclosed during calendar 2024. Exclude
  employee restricted-share forfeiture repurchases and later amendments of a
  pre-2024 scheme. Record the reason when no eligible scheme exists.
- Use that scheme's initial approved report and its first two subsequent
  scheme-specific execution/progress/result filings, through 2025-03-31.
  If fewer than three eligible filings exist, retain the available cutoffs and
  mark coverage incomplete. Do not replace a company after seeing model scores.
- Verify identity and dates from original filings and official metadata. Keep
  full texts and hashes. Record amendment/correction links without pretending
  an ordinary progress update contradicts the historical plan.
- Conservatively admit date-only filings the following calendar day at 00:00
  Shanghai time. Exclude later filings at each cutoff. Never backdate public
  availability to the underlying execution or board-meeting date.

Collection is prospective under fixed rules. It does not alone make a verified
held-out benchmark. Record all exclusions before inference; source review and
reference construction must not use model answers or future stock returns.

## Frozen measurement rules

Use Qwen Plus, temperature zero, Top-3 character-bigram TF-IDF retrieval, and one
initial diagnostic pass. Compare sparse RAG, append-only factual observations
plus the same archive retrieval, and current-state factual observations plus
the same archive retrieval. Rotate method order. Freeze code hashes, inputs,
reference drafts, and scoring rules before calls; never silently repair a failed
answer. Preserve rejected observations and count failures in denominators.

Reuse the explicit repurchase/cancellation state definitions from the current
development adapter. This is disclosure-state reconstruction, not a return
prediction task. Do not force an employee-incentive repurchase into a planned
share-cancellation label. A changed event identity or a new output schema must
be documented as a new protocol before inference, not patched after scoring.

Prepare references with source spans and label them AI drafts until reviewed.
Any unreviewed initial execution is development-only. The owner's previous
forty-item approval is not approval of these new temporal labels.

Report exact two-field accuracy, evidence-grounded accuracy, invalid admissions,
validation/API failures, eligible/selected document IDs, and provider usage
including cold-start memory construction. Keep per-company results: at most
three independent chains are available, regardless of the number of cutoffs.
Do not infer significance or general superiority from these small counts.

Evaluate source-grounding and admission errors before adding more repetitions.
If a baseline already solves all cases, report the ceiling and costs; do not
select harder or favorable cases after seeing outcomes to manufacture a gain.

## Completion criteria

Collection is complete when each listed company has a hashed source chain or a
documented exclusion. A reviewed evaluation requires confirmed references and
preserved frozen run artifacts. Software regression success and known-chain
improvement alone do not satisfy this criterion.
