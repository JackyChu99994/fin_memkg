# Historical delayed-entry pilot

Date: 2026-10-30. This is a data-pipeline pilot, not a held-out memory benchmark.

## Publication evidence

Official disclosure notices confirm report disclosure dates for
[Zhongji Innolight](https://disc.static.szse.cn/disc/disk03/finalpage/2024-10-22/682835bd-540c-46ab-a71d-0dfedb49d255.PDF)
and [Eoptolink](https://static.cninfo.com.cn/finalpage/2024-10-25/1221504365.PDF).
The dates are 2024-10-23 and 2024-10-25 respectively. Exact first-release times
are not verified. A directory date, meeting date, or PDF signature date must not
be substituted for first public availability.

The pilot conservatively defers availability to 00:00 Shanghai time on the next
calendar day. This is a declared policy bound, not a claimed publication time.
Entry uses the first benchmark trading session strictly after the disclosure
date, at close. Exit uses the close five benchmark trading intervals later.
This deliberately misses the first session's intraday response and does not
estimate an immediate announcement reaction.

## Frozen outcomes

The script writes the protocol and input hashes before computing outcomes.
No threshold is fitted and no bullish/bearish labels are assigned. The two cases
were already inspected during development; they cannot become held out later.

| Code | Entry close | Exit close | Stock return | CSI 300 return | Arithmetic excess |
| --- | --- | --- | ---: | ---: | ---: |
| 300308 | 2024-10-24 | 2024-10-31 | -8.9614% | -0.9619% | -7.9995 pp |
| 300502 | 2024-10-28 | 2024-11-04 | -3.1571% | -0.4893% | -2.6679 pp |

These are gross descriptive returns from the cached vendor series, not a
risk-adjusted CAR, executable strategy, or causal effect of either report.
Collected stock prices are forward adjusted; historical point-in-time adjustment
factors and independent vendor replication remain unavailable.

`data/experiments/history-delayed-pilot-20261030/inputs.jsonl` contains full-report
text and source metadata only. Future outcomes are separately stored in
`outcomes.DO_NOT_USE_AS_MODEL_INPUT.jsonl`. The full reports contain 14 and 12
pages respectively. Source PDFs, disclosure notices, extracted full text, and
prices are hashed. No inherited narrative, prior thesis, or return label is used.

## Validation

The isolated module suite passes 65 tests. New checks cover weekend entry,
five trading intervals, missing stock sessions, incomplete windows, duplicate
dates, and invalid prices. Missing sessions fail rather than silently shifting
the return horizon. No model calls were made for this pilot.

To rebuild into a new directory from the existing source cache:

```powershell
../../.venv/Scripts/python.exe -m experiments.history_pilot --cache data/experiments/history-candidates-20261030 --out data/experiments/history-delayed-pilot-new
```

## Requirements before comparing memory methods

Each current pilot has only one report, so neither is ready for a state-memory
comparison. Acquire dated primary evidence for earlier disclosures and subsequent
updates. Keep unchanged facts, different-metric facts, and actual corrections as
separate cases. Derive correctness of state updates from source evidence; measure
future returns separately. A profitable or unprofitable announcement does not by
itself determine whether a factual thesis should be invalidated.

Freeze selection rules before collecting new cases, and avoid selecting on known
returns. Use matched raw evidence and retrieval limits for sparse RAG,
append-only memory plus archive, and guarded state memory plus archive. An
independent reference review is still required for new temporal labels; the user's
previous approval covered only the original forty extraction records.
