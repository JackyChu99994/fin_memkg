# Development identity audit and source-bound task drafts

Date: 2026-11-01. This work touches only the 20 development companies. The 60
reserved companies, old source snapshots and original 556-call study are unchanged.

## Delivered artifacts

The ignored experiment directory `development-identity-audit-v3-20261101` contains
20 assistant-authored scheme audits and 23 source-bound development question
drafts. It includes 158 development source texts: the original 155 plus three
versioned supplements. Eighty-six evidence spans (including identity anchors)
were checked against source offsets and hashes. No model API was called.

References remain `assistant_source_anchored_development_draft`. Human-reviewed
and formal-evaluation-ready counts are both zero. Span integrity is not semantic
entailment or a substitute for independent review. Source-link diagnostics do
not automatically bind all same-company documents to the nominated scheme.

## Findings that change benchmark design

1. Correction is field-specific. The development examples include cumulative
   amount, share-count unit, projected share structure and executive-trading
   disclosure. A change in any one does not imply a new execution stage.
2. A revised report may amend the amount of an existing scheme rather than create
   another scheme. Preserve original approval, amendment date and field scope.
3. A second employee ownership plan receiving previously repurchased shares does
   not establish a second repurchase scheme. The 000157 title lead is retained as
   a negative-attribution development example rather than silently replaced.
4. A sponsor verification opinion is auxiliary. For 301322, the issuer's scheme
   disclosure is already archived and is used as the primary source.
5. A termination board decision may still require shareholder approval (002384).
   Conversely, “no shareholder submission required” must not match “required”.
6. Termination after partial execution and termination without any purchases
   are different. Execution history and scheme lifecycle are separate dimensions.
7. Date-nearest context selection can retrieve a first-purchase announcement from
   another scheme. Exact references in the target disclosure are better leads.

The three first-purchase gaps were filled using official metadata already saved
for 600703, 300415 and 688353. Sources are CNINFO_1218619830, CNINFO_1218368029 and
CNINFO_1221382712, six pages total. They live separately in
`development-source-supplement-20261101`; the 599-document snapshot is unchanged.
These supplements add evidence, not three new independent companies.

## Task composition

- Five completion date/share-total drafts.
- Three multiple-scheme attribution drafts.
- Four field-specific correction drafts and one scheme-amendment draft.
- One conditional-termination gate and one issuer-source/approval-gate draft.
- One negative scheme-attribution draft.
- Three terminated-after-purchase and one terminated-without-purchase drafts.
- Three first-purchase historical-cutoff drafts from the supplemented sources.

These are development diagnostics, not a replacement for the planned larger
reserved evaluation. Do not compare them directly with old three-class scores:
their output fields, scope and task types differ. Full company contexts can
contain legitimate distractor schemes; exact identities still need review.

## Version history and validation

The first audit's helper matched the substring “submission required” inside “no
submission required”. A negation regression check fixed it; v2 preserves the same
20 question/reference drafts with corrected diagnostic gates. V3 adds the three
supplemental originals and first-purchase drafts. V1/v2 remain available as audit
history and must not be used as current references.

Ten focused identity/span tests pass; all 130 root tests pass. These are software
checks, not 130 financial samples. The unchanged memory module's previous 99-test
run remains historical validation and was not rerun for this isolated change.

## Reproduction

From the repository root with Python dependencies available:

```powershell
python scripts/supplement_development_sources.py --out workspace/dev-supplement
python scripts/audit_development_schemes.py --out workspace/dev-audit --supplement workspace/dev-supplement
python -m pytest -q tests/test_repurchase_identity.py
```

Supplement acquisition additionally requires `pypdf`. It was executed using the
bundled PDF runtime; offline auditing itself uses the standard library. For saved
evidence inspection, use the already delivered versioned directories rather than
performing new network requests.

Next gates: owner/independent review of the draft facts, source-scheme links and
approval conditions; development of typed field extraction and scoring; separate
reserved reference construction; and manifest freeze before paid inference.
