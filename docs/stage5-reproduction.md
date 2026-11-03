# Stage-five reproduction

PPT creation is deferred. See [findings](stage5-final-results.md) and
[delivery scope](stage5-delivery.md) before interpreting any score.

## Install and inspect saved evidence

Extract the local delivery archive first. The public Git checkout alone excludes
the original PDFs and model outputs. Commands below run from the extracted root
using Python 3.11, the version used for this delivery.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts/validate_stage5_delivery.py
.venv\Scripts\python.exe scripts/query_research_kg.py --scheme CANDIDATE_301193 --as-of 2024-06-20
.venv\Scripts\python.exe scripts/query_research_kg.py --scheme CANDIDATE_301193 --as-of 2024-07-26
.venv\Scripts\python.exe -m streamlit run app.py
```

In the application select **Evidence research**. The query script and this page
read local graphs without calling a model. The two example dates should return
STARTED and COMPLETED respectively; these are disclosure-stage facts, not trading
advice. Source availability uses the next calendar day after disclosure.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q tests
Push-Location modules/l0l4-memory
..\..\.venv\Scripts\python.exe -m pytest -q tests
Pop-Location
```

The original stage-five regression runs passed 120 root tests and 99 module tests.
After the 2026-11-01 development identity checks, the root suite passes 130 tests;
see [the subsequent audit](development-identity-audit.md).
After the typed-scoring additions, the root suite passes 152 tests; see
[the scoring contract](typed-disclosure-evaluation.md). Counts describe successive
software snapshots, not independent evaluation examples.
After the two actual typed-task development passes and admission checks, the
latest root run passes 162 tests; the pilot log records an earlier market-test
flake and the bounded follow-up checks. See [the pilot findings](typed-development-pilot.md).
The subsequent source-catalogue/readiness/UI additions pass 178 root tests; see
[the integration notes](source-scheme-catalogue.md).
Reserved reference-construction checks bring the latest root suite to 189 tests;
see [the bank construction record](reserved-question-bank.md). The reference
generation attempt is not a method evaluation, and all new candidates await review.
Saved-study validation is a separate integrity check, not model accuracy evidence.

## Saved study and optional live calls

All paths below are under `modules/l0l4-memory/data/experiments/`:

- `lifecycle-expanded40-20261030`: original 196 PDFs, extracted text and metadata.
- `lifecycle-expanded40-references-20261030`: original AI drafts and failure/retry.
- `source-adjudicated-v3-20261031`: references used in the original inference run.
- `source-adjudicated-v4-20261031`: corrected same-day cumulative references.
- `expanded-study-20261031`: 556 calls, prompts, outputs, frozen inference code,
  original scores, corrected scores, graphs and subsequent admission audits.
- `ga-source-integration-20261031` and `ga-source-verified-20261031`: the first
  free-text integration attempt and the separately verified structured query.
- `stage5-news40-unique` and `stage5-user-reviewed-v1-taskv2-*`: earlier reviewed
  extraction development set and its three scored configurations.

Scores can be inspected without credentials in
`expanded-study-20261031/corrected-reference-scores/summary.json`. The field
`grounded_correct` measures reference-designated source inclusion, not general
semantic entailment. Expanded references remain silver; no new human review is
implied by their filenames or by the older reviewed 40-item set.

To recompute the main corrected metrics without any API call, use a new directory:

```powershell
.venv\Scripts\python.exe scripts/rescore_stage5_saved.py --out workspace/rescore-check
```

The reserved correct counts should be 58, 58, 58, 58 and 57 for full text,
TF-IDF RAG, append memory, current flat state and current graph state respectively.

## Owner reference review

Generate a standalone offline form with all 77 questions and their eligible full
source texts. It starts entirely pending, hides the existing silver answer behind
a disclosure control and does not show model scores. The owner must supply an
identifier, a stage and eligible source IDs before saving a confirmation.

```powershell
.venv\Scripts\python.exe scripts/build_stage5_review.py --out workspace/reference-review.html
```

Open the HTML file in a browser. Save each question, then export the JSON record;
browser storage alone is not a durable handoff. Records can be imported into the
same reference-version form. This records owner self-review and never writes to
the reference corpus or certifies independent double annotation. Corrections and
uncertainties require notes. Do not rerun live inference to hide reference errors.

For explicitly requested new paid calls, copy `.env.example` to `.env` locally,
set the existing Qwen-compatible configuration and never share that file.
`scripts/demo_ga_research.py --help` documents its explicit `--live` switch.
The frozen study uses `qwen-plus`; do not silently replace models or failures.
Later deployment guards differ from the frozen study code. Re-running current
code is a new experiment, not reproduction of identical stochastic responses.

The archive includes a SHA-256 manifest and omits `.env`, virtual environments,
Git internals, logs and model credential caches. Original announcements retain
their publisher URLs; redistribution does not grant ownership of those sources.
