# User confirmation of the forty extraction annotations

On 2026-10-29 the project owner confirmed in chat that the annotations had been
checked and were acceptable. The forty extraction records are now recorded as
AI initial annotation followed by user review. No independent second annotator
or blind review is claimed.

- Reviewed records: 40 of 40.
- Relations: 25 across 16 nonempty records; 24 reviewed empty outputs.
- Frozen reference: `data/experiments/stage5-news40-unique/annotations-user-reviewed-v1.jsonl`.
- Editable reference: `annotations.jsonl` in the same directory.
- Provenance: `annotation-user-reviewed-v1-manifest.json`, including hashes and
  the user confirmation method.
- Initial AI labels are preserved unchanged as `annotations-ai-v1.jsonl`.

The annotation editor now displays 40 / 40 reviewed. The reference passes the
formal review-and-hash gate without `--allow-draft`.

## Rescoring

All six saved extraction runs were rescored against the confirmed reference:
three methods under the legacy contract and three under `event-target-v2`.
The event labels were accepted without edits, so all measurement counts remain
unchanged. Rescoring made zero additional API calls.

Exact directed relation F1 remains zero for all methods in both development
protocols. This result is retained, including the documented event-name mismatch
and genuine model errors. User review establishes reference provenance; it does
not remove task-design problems, small-sample limits, prompt-development bias,
or the need to measure generalization separately.

The rescored runs are stored under
`data/experiments/stage5-user-reviewed-v1-{legacy,taskv2}-{method}-r1/`.
Their paths are indexed in `reviewed-rescore-index.json` beside the reference.
Use `experiments.rescore_extraction` to reproduce this operation without making
model calls. Original prompts, outputs, token usage, and manifests are preserved.

## Separate remaining work

The user's confirmation covers the forty news extraction annotations. Five
episode-level reference answers remain separate AI-initial labels; they are not
automatically promoted to human-reviewed answers. The extraction stage no longer
needs another review of the same forty records unless the task or labels change.

The next technical issue is to settle event naming and matching, preserve the
exact-match diagnostic, and address observed extraction and memory failures.
Repeated live calls alone would not resolve these problems. No graph-memory
performance improvement or completed official RealFin evaluation is claimed.
