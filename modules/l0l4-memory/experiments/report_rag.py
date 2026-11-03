"""Generate a concise evidence-based report and CSV from a completed comparison."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    summary = json.loads((args.run / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((args.run / "manifest.json").read_text(encoding="utf-8"))
    records = [json.loads(line) for line in (args.run / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    methods = [method for method in ("full_text", "tfidf_rag", "state_memory", "append_memory_archive", "state_memory_archive") if method in summary["methods"]]
    names = {"full_text": "Full text", "tfidf_rag": "Sparse TF-IDF RAG", "state_memory": "State memory",
             "append_memory_archive": "Append-only memory + archive", "state_memory_archive": "State memory + archive"}
    baseline = summary["methods"]["tfidf_rag"]
    memory_key = "state_memory_archive" if "state_memory_archive" in summary["methods"] else "state_memory"
    memory = summary["methods"][memory_key]
    if memory["majority_accuracy"] > baseline["majority_accuracy"]:
        conclusion = "State memory has higher majority accuracy on this small development set; this is not evidence of general or statistically significant superiority."
    elif memory["majority_accuracy"] < baseline["majority_accuracy"]:
        conclusion = "State memory has lower majority accuracy than sparse RAG on this small development set. No memory benefit is demonstrated."
    else:
        conclusion = "State memory and sparse RAG have the same majority accuracy on this small development set. No accuracy gain is demonstrated."
    lines = ["# Task two repeated RAG comparison results", "", conclusion, "",
        f"Protocol: `{manifest['protocol']}`. Configured model: `{manifest['model']}`. "
        f"Provider response model names: {', '.join(manifest.get('provider_response_models', [])) or 'not returned'}. "
        f"There are {summary['unique_episodes']} unique episodes and {manifest['repeats']} repetitions.", "",
        "References are mechanically derived from the forty user-reviewed extraction annotations. "
        "They are not five newly independent human annotations. This is evidence-sign consistency, not return prediction.", "",
        "## Results", "",
        "| Method | Accuracy by repeat | Mean +/- sample SD | Majority | Direction + required source IDs | Invalid citation IDs |",
        "| --- | --- | --- | --- | --- | --- |"]
    csv_rows = []
    for method in methods:
        row = summary["methods"][method]
        repeat_text = ", ".join(f"{value:.1%}" for value in row["per_repeat_accuracy"])
        sd = row["sample_std_accuracy"]
        sd_text = f"{sd:.1%}" if sd is not None else "N/A"
        lines.append(f"| {names[method]} | {repeat_text} | {row['mean_accuracy']:.1%} +/- {sd_text} | {row['majority_correct']}/{row['majority_total']} | {row['grounded_correct_predictions']}/{row['predictions']} | {row['invalid_citation_ids']} |")
        csv_rows.append({"method": method, **{key: row[key] for key in
            ("predictions", "failures", "mean_accuracy", "sample_std_accuracy", "majority_correct", "majority_total",
             "majority_accuracy", "grounded_correct_predictions", "invalid_citation_ids", "input_tokens_including_build",
             "output_tokens_including_build", "mean_total_tokens_including_build", "live_calls", "mean_latency_seconds_including_build")}})
    lines += ["", "## Cost including memory construction", "",
        "| Method | Input tokens | Output tokens | Mean total tokens / answer | Calls | Mean elapsed seconds / answer |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for method in methods:
        row = summary["methods"][method]
        lines.append(f"| {names[method]} | {row['input_tokens_including_build']:,} | {row['output_tokens_including_build']:,} | {row['mean_total_tokens_including_build']:.1f} | {row['live_calls']} | {row['mean_latency_seconds_including_build']:.2f} |")
    lines += ["", "Cold-start memory construction is included. Cached or amortized long-running-agent cost was not evaluated. "
        "Token counts come from provider responses and are not verified billing amounts.", "", "## Paired majority comparison", ""]
    for pair, values in summary["paired_majority"].items():
        lines.append(f"- {pair}: {values['wins']} wins, {values['losses']} losses, {values['ties']} ties; exact McNemar p={values['exact_mcnemar_p']:.4f}.")
    lines += ["", "Only five unique episode units enter this calculation. Repeated calls do not enlarge the independent sample. "
        "The protocol was developed after prior failure inspection, and source events share market context. "
        "Do not interpret these calculations as proof of generalization.", "", "## Errors", "",
        "| Episode | Repeat | Method | Reference | Prediction | Invalid citations |",
        "| --- | ---: | --- | --- | --- | --- |"]
    errors = [row for row in records if not row["correct"] or row.get("invented_evidence_ids")]
    for row in errors:
        lines.append(f"| {row['id']} | {row['repeat']} | {row['method']} | {row['reference_direction']} | {row.get('prediction', {}).get('direction', row['status'])} | {', '.join(row.get('invented_evidence_ids', [])) or 'none'} |")
    if not errors:
        lines.append("| None observed in these metrics | - | - | - | - | - |")
    memory_rows = [row for row in records if row["method"] == memory_key]
    def graph_context(row):
        evidence = json.loads(row["prompt"])["evidence"]
        return evidence.get("graph", []) if isinstance(evidence, dict) else evidence
    empty_memory = sum(not graph_context(row) for row in memory_rows if row.get("prompt"))
    missing_reference = sum(row.get("required_evidence_recall") == 0 for row in memory_rows)
    lines += ["", "### Failure inspection", "",
        f"State memory supplied an empty final graph in {empty_memory}/{len(memory_rows)} predictions. "
        f"Required reference-source coverage was zero in {missing_reference}/{len(memory_rows)}. "
        "This localizes an important end-to-end bottleneck to loss of relevant facts during memory construction, "
        "rather than an API or JSON parser failure."]
    contradictions = [row for row in records if row.get("prediction", {}).get("direction") != "NEUTRAL"
        and "per instructions this yields NEUTRAL" in row.get("prediction", {}).get("reason", "")]
    if contradictions:
        lines += ["", f"In {len(contradictions)} retained outputs, the direction field differs from the reason's explicit "
            "'yields NEUTRAL' text. The direction-field score is retained; the reason is not used to silently correct it."]
    cross_metric = []
    for row in memory_rows:
        if not row.get("prompt"):
            continue
        for edge in graph_context(row):
            if edge.get("status") == "已被证伪" and "市占率" in edge.get("reason", "") and any(word in edge.get("invalidated_reason", "") for word in ("营收", "收入")):
                cross_metric.append(row["id"])
    if cross_metric:
        lines += ["", "The retained graph context also contains a market-share fact invalidated by a revenue-related reason. "
            "Different financial metrics require separate thesis identities; opposite signs alone do not establish contradiction."]
    lines += ["", "Grounded accuracy can still fail through omitted required evidence even when the table has no direction or invalid-ID error. "
        "Inspect `records.jsonl` for evidence coverage and reasons. Valid citation identifiers alone do not establish entailment.", "",
        "## Evidence and scope", "",
        f"Run directory: `{args.run.as_posix()}`.", "",
        "The directory retains `manifest.json`, `episodes.jsonl`, `records.jsonl`, and `summary.json`. "
        "The adjacent plan froze inputs and reference rules before requests. Old single-repeat protocols are preserved separately "
        "and are not pooled into this comparison.", "",
        "Task two's bounded comparison is complete. These results do not establish improved financial returns, neural-RAG superiority, "
        "two-hop topology benefit, autonomous skill evolution, or completion of the official RealFin forty-task benchmark.", ""]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    csv_path = args.run / "comparison.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(args.out)


if __name__ == "__main__":
    main()
