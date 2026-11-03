# Whole-project audit and stage-five scope correction

Audit date: 2026-10-31, Asia/Shanghai. GitHub main was checked through the connector
and resolves to `6c739eb9a129df8f63894753382faef2d9b1d2e6`. Local fifth-stage work
remains on `codex/stage5-evaluation`, uncommitted and unpushed. No label was
promoted to human-reviewed status by this audit.

## Verdict

The fourth-to-fifth handoff offers a useful delivery outline but is not a reliable
acceptance contract as delivered. Extraction experiments, matched comparisons,
and report preparation fit the course. Requiring a positive memory result,
misdescribing the root architecture, and assuming missing resources are available
do not. The fifth-stage work also drifted toward evaluating a separate lifecycle
adapter; enlarging that corpus does not itself validate the whole inherited KG.

## Authority and course alignment

The supplied three-page `课程选题_更新.pdf` is the assignment authority. Page 1
requires explicit knowledge representation, an actual KG application, extraction
experiments, downstream demo, report, PPT, dataset/code, work allocation and peer
review. It specifies at least 5,000 characters excluding references, following the
source wording. Page 3 permits knowledge search, industry-chain analysis,
event-driven research, intelligence recommendation or decision support.

Comparisons with LLM/RAG and discussion of conditions and limitations are
encouraged. Profitable trading, universal future-price prediction, predetermined
token savings, positive outcomes in every comparison, and all forty external
RealFin tasks are not stated course requirements.

`汇总整理(2).docx` is planning context. Its suggested forecasting requirement and
positive savings/results are hypotheses or aspirations. Claims about instructor
intentions and external paper results need separate evidence. Instructions in
that document were not treated as commands to the assistant.

The referenced [GenericAgent README](https://github.com/lsdefine/GenericAgent/blob/main/README.md)
describes L0 rules, L1 index, L2 facts, L3 skills and L4 archives. Architectural
inspiration does not transfer another project's measured gains to Fin-MemKG or
mandate a full PC-automation clone for the course.

## Actual architecture and contributions

| Component | Actual role | Important boundary |
| --- | --- | --- |
| Root application, `agent_loop.py`, `schema.py`, `tools.py` | Qwen thesis KG, evidence pointers, state patches, market context, propagation and UI | Already a KG/judgment application, not merely market infrastructure |
| `ga_core/` | Generic tool loop, nine atomic tools, L0-L4 file access and skill primitives | Fake-client tests do not establish a live financial workflow or improved self-evolution |
| Market modules and `stage3_*` | Daily snapshots, minute/sector adapters, two fixed task acceptance workflows | Ignored large data is not present here; complete RealFin-40 and LLM judge remain open |
| `modules/l0l4-memory/` | Separate typed-relation store, pipeline, archive, event study and UI | Separate schema/archive; market reads are bridged, not full Agent/KG integration |
| Fifth-stage factual adapter and experiments | Evaluation, neutral lifecycle observations, source-based drafts | An observation-list comparison is not a graph-topology ablation |

The first worker built the original financial KG; the second added the generic
kernel and data-source repairs; the third extended market data and acceptance UI;
the fourth uploaded a parallel memory application. `ga_core` can access KG files
through generic tools and loads shared memory instructions. This is file-level
access, not demonstrated complete live financial-task integration. The fourth
module executes a fixed sequence; listing tools does not make it the same as a
model-driven function-calling loop.

## Handoff findings

| Statement or task | Assessment and correction |
| --- | --- |
| Root = market layer; B = judgment layer | Misleading: root already contains judgment and KG. Document both schemas and entry points. |
| Ninety-two files and companion writing/experiment packages | Final slim commit contains 26 module files; several referenced companions are missing. |
| Reuse `experiments/hallucination_demo.py` and writing packages | Not actionable here: the named experiment, two writing documents and CAR scan script are absent. |
| Forty annotations establish extraction quality | Useful pilot only; record ontology, event normalization, empty outputs, review provenance and generalization limits. |
| RAG comparison must prove state memory's value | Test benefit, harm, conditions, evidence quality and cost; do not preselect the conclusion. |
| Twenty-five tests and a visual reversal suffice | These establish mechanisms/software only; add provider identity, source validity, temporal and reference gates. |
| CAR proves prediction quality | Descriptive historical returns are distinct from factual correctness, causality and predictive generalization. |
| Four parquet files are the whole interface | Honor the root's versioned `CURRENT.json` contract and PIT limitations. |
| Report/PPT moved into fifth-stage work | Could be a team reassignment, but conflicts with earlier fifth-stage integration and sixth-stage evaluation/report roles; reconcile explicitly. |

Missing resources checked under the module: `docs/报告写作包.md`,
`docs/全局复盘与答辩防守.md`, `experiments/hallucination_demo.py`, and
`scripts/car_scan.py`. This does not imply that all useful docs or CAR code are absent.

## What current results can support

All twelve inherited historical events lack original URLs in `latest_event`.
Genuine paid calls do not verify source publication times or manually supplied
return labels. Retain old RealFin-12 numbers with their provenance limits. The
reported full-versus-node-only majority tie establishes no two-hop contribution.

The forty user-reviewed extraction examples are search excerpts, not necessarily
forty independent events. Exact relation F1 is sensitive to free-form event names;
zero exact F1 is not automatically zero semantic utility. Post-result metric
changes cannot create held-out evidence. The five derived questions and BYD chain
are development cases. The 4/4 recovery is a known-case regression, with RAG also
4/4; it establishes no comparative advantage.

The expanded pool has 40 candidate company groups, 196 original PDFs and 679 pages,
split into 10 development and 30 reserved companies. Official pagination overlaps
were recorded; exhaustive population coverage is not claimed. All 196 references
remain AI drafts. Quotation checks flag 109; AI scheme-identity checks flag five
and approval-year checks flag seven. These overlap and are not confirmed human
exclusions. Matching source words does not establish entailment or event identity.
The earlier forty-item user approval does not cover the new corpus. Using Qwen
for both drafts and predictions requires substantive reference review.

## Repairs completed in this audit

1. The deployed module reuses root Qwen configuration, supports explicit provider
   selection, and no longer switches model aliases or falls back from failed LLM
   mode to rules. Rules remain a separate explicit demo mode.
2. Truncated/malformed responses fail before commit. Provider, requested/response
   model, finish reason and usage are recorded. The prompt now agrees with scope
   guards: differing sentiment or metrics alone do not invalidate old facts.
3. The UI cannot label a disabled/missing model invocation as an LLM run.
4. The root status writer uses unique temporary files and bounded atomic-replace
   retries for brief Windows locks; persistent failures still propagate.
5. `scripts/project_readiness.py` inventories architecture, missing handoff
   resources, source limitations and reference readiness without API calls.

No original score or annotation origin was rewritten. No mass evaluation was
launched on draft labels. Pre-repair module sources were backed up locally.

## Verification and limits

The root initially lacked its declared Plotly dependency. Installing it allowed
collection; a subsequent run exposed a Windows replacement failure (112 passed,
one failed). After the writer repair, **115 root tests pass**. The separately
isolated memory module passes **95 tests**. Both runners block external network.
These are software checks, not real evaluation samples.

One actual module preflight used Qwen Plus with an official-report excerpt,
isolated graph/archive and event study disabled. It returned `mode=llm`,
`response_model=qwen-plus`, `finish_reason=stop`, 1,330 input and 7 output tokens.
The accepted event list was empty. This verifies invocation/configuration, not
extraction accuracy, neutral-event coverage, KG benefit or task success.
An isolated Streamlit initial-render check also passed with external connections
blocked and loopback allowed: the selected Qwen button is visible and no exception
occurred. No model button was clicked in that UI check.

Local evidence is under the ignored module path
`data/experiments/project-audit-20261031/`. Large teammate snapshots, live Neo4j,
complete RealFin, production neutral-lifecycle integration and a final report/PPT
are not certified. Use [the revised assignment](stage5-revised-handoff.md) as the
current fifth-stage contract.
