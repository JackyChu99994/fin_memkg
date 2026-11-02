# Stage five evaluation

Final 2026-10-31 delivery: see the root
[results](../../../docs/stage5-final-results.md) and
[reproduction guide](../../../docs/stage5-reproduction.md). The completed module
suite passes 99 tests; the earlier counts and pilots below are historical.
The expanded study uses silver references, not newly human-reviewed gold.

This directory adds extraction evaluation, an annotation editor, and a same-model
memory comparison to module B. It does not replace the existing demonstration UI.
All commands below run from `modules/l0l4-memory`, using the repository environment.

## Current evidence

- The isolated module suite passes 87 tests, including 62 added tests for
  measurement, snapshots, evidence preservation, scoped updates, and historical
  return windows. This is software validation, not model accuracy.
- The [historical delayed-entry pilot](../docs/historical-pilot.md) separates
  full-report inputs from realized returns. Its two known cases are not ready
  for a state-memory comparison and are not held out.
- The [lifecycle audit](../docs/lifecycle-development.md) records a four-filing
  source chain, two development diagnostics, and a factual-memory admission
  prototype. New temporal references remain AI drafts; no benefit is established.
  A subsequent 32-call known-chain regression passes 4/4 grounded answers for
  each method after admission repairs; state-memory token cost remains about
  2.14 times the RAG baseline. Independent-chain collection rules are frozen in
  [the expansion plan](../docs/lifecycle-expansion-plan.md).
- A [larger candidate corpus](../docs/expanded-corpus.md) contains 40 companies,
  196 full-text original filings, and 679 PDF pages. Ten companies are assigned
  to development and thirty reserved for test. Original scheme identities and
  new temporal references remain unreviewed; no large-test accuracy is claimed.
  All 196 AI reference drafts are saved with a read-only review index and an
  explicit source-review editor. Quotation checks flag 109 drafts for
  adjudication; none are automatically treated as human ground truth.
- Forty news records were collected on 2026-10-29 from five stock-code searches.
  Exact text hashes and source URLs are unique. Different URLs can still describe
  the same event; this is not a claim of forty independent events.
- Provider news content is often a search excerpt. It is not verified full article
  text or independently verified financial ground truth.
- The user has confirmed all forty extraction annotations. A reviewed reference
  is frozen as `annotations-user-reviewed-v1.jsonl`; saved outputs were rescored
  with zero new API calls. See [the confirmation record](../docs/stage5-user-review-status.md).
  Episode-answer review and broader performance validation remain separate.
  A subsequent
  two-call `qwen-plus` preflight on 2026-10-29 passed JSON connectivity and one
  news extraction. It used 997 input and 153 output tokens and was not graded.
  No live-model gain is claimed.
- All forty AI initial annotations are now complete, with 25 relations and 24
  explained empty outputs. Development extraction and memory comparisons have
  initially run against unreviewed references, with extraction outputs subsequently
  rescored after user confirmation; see [the run status](../docs/stage5-ai-annotation-status.md).
- The eight synthetic development cases expose weak rule extraction; its relation
  F1 is zero in the recorded development run. This is not a live-model result.

## Environment

From the repository root:

```powershell
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -r modules/l0l4-memory/requirements.txt pytest pyarrow
cd modules/l0l4-memory
$env:PYTHONUTF8 = "1"
```

Use `../../.venv/Scripts/python.exe` for the commands below. Raw texts, credentials,
annotations, and run outputs stay in ignored local directories. Do not commit them
by accident. Keep source attribution when sharing a dataset with the course team.

## News collection and human annotation

The delivered local collection is `data/experiments/stage5-news40-unique/`.
To collect another independent version:

```powershell
../../.venv/Scripts/python.exe -m experiments.collect_corpus --out data/experiments/news40-new
../../.venv/Scripts/python.exe -m streamlit run experiments/annotate.py --server.address 127.0.0.1 --server.port 8502
```

Select the delivered directory in the annotation sidebar. Enter a reviewer name,
read each excerpt and its source, edit the events JSON, and confirm review. AI
proposals, when present, are separate fields and are never used as gold labels.
The editor validates the schema but cannot certify a person's annotation quality.

Follow [the annotation guide](../docs/stage5-annotation-guide.md). Empty `events`
means no supported relation. It must be deliberately reviewed. At least a second
reviewer should independently annotate a subset and adjudicate disagreements.
The scorer requires a reviewer and matching document hash for every record.

## Extraction experiments

Configure one provider locally in either the repository `.env` or the module
`.env`. Qwen uses `QWEN_API_KEY`, `QWEN_MODEL`, and `QWEN_BASE_URL`; DeepSeek uses
the corresponding `DEEPSEEK_*` variables. Environment variables take precedence.
Never paste secrets into a report, chat, or tracked file.

```powershell
$corpus = "data/experiments/stage5-news40-unique/corpus.jsonl"
$labels = "data/experiments/stage5-news40-unique/annotations.jsonl"
../../.venv/Scripts/python.exe -m experiments.eval_extraction --corpus $corpus --labels $labels --method plain --provider qwen --out data/experiments/extract-plain-r1
../../.venv/Scripts/python.exe -m experiments.eval_extraction --corpus $corpus --labels $labels --method l0 --provider qwen --out data/experiments/extract-l0-r1
../../.venv/Scripts/python.exe -m experiments.eval_extraction --corpus $corpus --labels $labels --method l0_l1 --provider qwen --out data/experiments/extract-l0-l1-r1
```

Repeat each method three times with new output directory names. `plain` shares
the JSON schema with the other methods but omits the L0 block; `l0` adds rules;
`l0_l1` also adds the existing dictionary router. All methods use the same
provider/model, temperature zero, and output cap. No retry or model substitution
is hidden in these experiments. API and parse failures remain failures.

Micro P/R/F1 counts exact typed entities, directed triples, and triples with
state. Rejected candidates are reported separately and also included in raw
relation precision. Undefined empty denominators remain `null`. Failure cases
contribute missing gold facts and zero document accuracy. These metrics do not
measure every numeric hallucination or factual correctness beyond the labels.

## Memory comparison

Task two's completed repeated comparison is documented in
[the results](../docs/stage5-rag-results.md) and [protocol](../docs/stage5-rag-protocol.md).
Its references are mechanically derived from user-reviewed facts; no independent
episode annotation is claimed. Reproduce it using:

```powershell
../../.venv/Scripts/python.exe -m experiments.reviewed_comparison --corpus data/experiments/stage5-news40-unique/corpus.jsonl --labels data/experiments/stage5-news40-unique/annotations-user-reviewed-v1.jsonl --provider qwen --model qwen-plus --repeats 3 --top-k 3 --out data/experiments/comparison-new
../../.venv/Scripts/python.exe -m experiments.report_rag --run data/experiments/comparison-new --out docs/comparison-new.md
```

The older draft-episode entry point below remains available for development.

Create episodes with the format produced by the development generator. Each has
an `id`, timezone-aware `as_of`, `query`, raw chronological `documents`, and a
separate `gold` answer. Review real episodes independently. Never put an answer,
future return, or adjudication note into document text.

Five original unlabelled real-source episode drafts are available at
`data/experiments/stage5-news40-unique/episodes-draft.jsonl`. Completed AI-initial
versions are in `episodes-ai-v1.jsonl`; they still need user review.
A reviewer must decide whether each group
supports a meaningful question, set its direction and evidence IDs, and record
review before evaluation. Grouping news by a search code does not guarantee
contradictions or even company-specific evidence. To prepare another draft:

```powershell
../../.venv/Scripts/python.exe -m experiments.prepare_episodes --corpus data/experiments/stage5-news40-unique/corpus.jsonl --out data/experiments/episodes-new.jsonl
```

```powershell
../../.venv/Scripts/python.exe -m experiments.eval_memory --episodes data/experiments/reviewed-episodes.jsonl --provider qwen --repeats 3 --top-k 3 --out data/experiments/memory-r1
```

Methods are full text, character-bigram TF-IDF cosine Top-3 RAG, and chronological
L0/L1 extraction into the module's actual L2 state machine. The RAG baseline uses
sparse lexical vectors; it is not neural embedding RAG. State memory pays for
every extraction call and its final answer. All methods receive the same eligible
raw documents before their own transformations. Gold fields are excluded from
prompts. Future documents are removed before retrieval or memory building.

The task measures consistency with current documentary evidence. It does not
measure T+5 investment performance, causal graph benefit, or the full RealFin
forty-task benchmark. The module's automatic opposite-polarity invalidation is a
method limitation: opposite opinions do not necessarily describe the same thesis.

## Reproduce the development checks

```powershell
../../.venv/Scripts/python.exe -m experiments.offline_check
../../.venv/Scripts/python.exe -m experiments.make_development_data --out data/experiments/development-new
../../.venv/Scripts/python.exe -m experiments.eval_extraction --corpus data/experiments/development-new/corpus.jsonl --labels data/experiments/development-new/annotations.jsonl --method heuristic_reference --allow-draft --out data/experiments/development-check-new
```

`--allow-draft` marks the result `development_only`; it never establishes human
review. `heuristic_reference` is always `RULE_MECHANISM_SIMULATION`. Synthetic
episodes with live models must still be described as synthetic experiments.

Each completed run writes immutable `records.jsonl`, `summary.json`, and
`manifest.json` to a new directory. Manifests include input and code hashes,
provider/model settings, call status, actual token usage when supplied by the
provider, and a base Git commit plus dirty-checkout status. Prompts and responses
are local evidence and should be reviewed before sharing.

## Handoff

The report draft is [stage5-report.md](../docs/stage5-report.md). Submission
readiness and remaining decisions are in [stage5-handoff.md](../docs/stage5-handoff.md).
