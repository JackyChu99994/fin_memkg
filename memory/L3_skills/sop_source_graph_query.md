# Source-linked financial event query

Origin: manually consolidated from the fifth-stage source-graph integration.
This is a reusable procedure, not evidence of automatic skill learning.

1. Use `scripts/query_research_kg.py --scheme CANDIDATE_<code> --as-of YYYY-MM-DD`.
   Run with the repository Python environment. This action is read-only and makes
   no network request. Never substitute current facts for an earlier cutoff.
2. The loader checks archived document text against the frozen corpus hashes.
   A failed check is an error, not permission to invent a source or a state.
3. Return the state, its availability bound, supporting original filing URL,
   source quotation, and company-scheme-observation-source graph path.
4. If no observation is admitted, report that absence of admitted evidence.
   Do not infer that an event did not occur in the real world.
5. These are machine-extracted observations. Do not claim human validation,
   investment profitability, or that share cancellation abandons a repurchase plan.

Chronological illustration: family scheme `CANDIDATE_301193` has a first-purchase
disclosure available on 2024-06-18 and an implementation-completion disclosure
available on 2024-07-26. Query earlier and later cutoffs separately; earlier facts
remain in history when the current-state view advances.
