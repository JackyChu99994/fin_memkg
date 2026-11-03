# Evidence and state-update repairs with historical-data audit

Date: 2026-10-30. These changes follow the negative task-two development results.
Old inputs, labels, model outputs, and the v3 reproduction package are preserved.
Six pre-repair source files and their hashes are separately saved under
`data/experiments/before-memory-repair-20261030/`.

## Repairs

1. **Archive before deciding whether extraction succeeded.** `pipeline.commit`
   now writes the source even when the accepted event list is empty. L4 recall
   can retrieve that source without requiring a graph edge.
2. **Use an explicit scope guard.** Metric, year, quarter/year-to-date period,
   year-on-year/quarter-on-quarter basis, geography, and business family are
   compared before invalidation. Unknown or conflicting financial scopes coexist.
   Model-requested cross-scope invalidations are blocked and traced. Positive and
   negative signs alone do not prove that one statement corrects the other.
3. **Avoid collapsing distinct evidence.** Same-sign facts from different periods
   or proposal/execution stages are not automatically reinforced. Local-store
   reinforcement preserves the first and new source references. Neo4j's matching
   reference-list update was changed as well, but no live database integration
   was available to verify that backend.
4. **Add bounded archive context.** The experiment adapter now supports
   `append_memory_archive` and `state_memory_archive`. Both receive the same
   Top-3 archive retrieval as the RAG baseline; graph state is additional
   automatically constructed context. No reviewed reference fact is inserted
   into evaluated memory.
5. **Cap forecast-time price access.** The demonstration agent passes its decision
   date into event-study `as_of`. An incomplete or synthetic event study does not
   produce an action from unavailable future returns. The pipeline refuses to
   analyze an earlier date using a mutable graph with later facts or updates;
   historical work must replay into an isolated dated store.

The scope guard is conservative pattern-based protection, not complete logical
contradiction detection. Contract/project identity can still be ambiguous.
Unknown scope is retained rather than silently deprecated. This does not solve
all event-name normalization or knowledge-extraction errors.

## Validation and its limits

The final isolated offline suite passes 61 tests. Offline tests cover mixed metrics, different comparison bases, different periods,
explicit same-scope corrections, proposal versus execution, preservation of
original evidence, archive recovery after empty extraction, dated recall,
append-only controls, and forecast-time price access. Synthetic fixtures only
establish these mechanisms; they are not real-model accuracy evidence.

A small live development smoke used the existing BYD and CATL questions, one
pass each, with Qwen and a RAG control. It made 21 API calls and four final
answers, with no API/parse failures. All four answers matched the existing
references. The archive-augmented memory supplied three raw sources in each
case, including the previously lost repurchase evidence. Its input/output usage
was 28,954/2,146 provider-reported tokens for the complete smoke, including both
methods and memory construction.

This is a known-case regression, not a new held-out experiment. RAG also answered
both cases correctly, so no memory advantage is established. The live smoke
checks archive recovery; the final historical-replay guard is checked offline.
Results are in `data/experiments/memory-repair-smoke-20261030/`. Do not overwrite
the earlier v3 comparison or combine these different protocols as repeated trials.

## Historical prices actually available on this machine

The large 1,411-stock snapshot described by earlier contributors was not present
in the cloned repository or the explicitly checked legacy directory. A new,
separate candidate cache now contains four stock series and the CSI 300 index:

| Series | Observed rows | First date | Last date |
| --- | ---: | --- | --- |
| 300308 | 299 | 2024-01-02 | 2025-03-31 |
| 300502 | 299 | 2024-01-02 | 2025-03-31 |
| 600519 | 299 | 2024-01-02 | 2025-03-31 |
| 002594 | 299 | 2024-01-02 | 2025-03-31 |
| sh000300 | 299 | 2024-01-02 | 2025-03-31 |

The existing Sina/AkShare adapters supplied these series with per-call time
limits and no synthetic fallback. Checks found unique dates, positive close
prices, and no stock-date gaps relative to this vendor's benchmark calendar.
No independent vendor cross-check is claimed. Stock data uses the collected
forward-adjusted version, not archived point-in-time adjustment factors.
The subset is not published as a full-market snapshot. Files, hashes, and
coverage checks are in `data/experiments/history-candidates-20261030/`.

## News provenance remains a gate

All twelve inherited historical events lacked original URLs. Their publication
times and manually stored future-return labels are not accepted as verified
ground truth. Two primary financial reports were located and saved:

- [Zhongji Innolight 2024 Q3 report](https://static.cninfo.com.cn/finalpage/2024-10-23/1221474464.PDF),
  in the official archive dated 2024-10-23.
- [Eoptolink 2024 Q3 report](https://static.cninfo.com.cn/finalpage/2024-10-25/1221504363.PDF),
  in the official archive dated 2024-10-25.

These reports substantiate financial disclosures. They do not substantiate all
editorial interpretation in the old event narratives or prove the old claimed
morning availability times. An archive directory date is not an exact release
timestamp. Original as-of dates therefore remain unapproved for prediction
evaluation. The source PDFs and their hashes are saved alongside the audit.

## Next experiment

Verify publication availability first, then freeze new cases and T+5 return
definitions before inference. Use the following controlled comparison:

- sparse RAG;
- sparse RAG plus append-only structured memory;
- sparse RAG plus scope-guarded state memory.

Archive retrieval, provider/model, eligible raw inputs, and answer contracts must
match. Include cold-start and separately measured warm-cache costs. Preserve old
development cases for regression and use independently chosen cases for any
effectiveness claim. Historical prices alone do not repair unverifiable news.

The runner accepts these methods explicitly:

```powershell
../../.venv/Scripts/python.exe -m experiments.reviewed_comparison --corpus data/experiments/stage5-news40-unique/corpus.jsonl --labels data/experiments/stage5-news40-unique/annotations-user-reviewed-v1.jsonl --methods tfidf_rag append_memory_archive state_memory_archive --provider qwen --model qwen-plus --repeats 3 --out data/experiments/archive-comparison-new
```

That command reuses development cases. It is for regression until a separate
historical source-and-price benchmark has passed the provenance gate.
