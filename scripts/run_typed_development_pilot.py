"""Explicit paid, full-context development pilot; no retries or held-out claims."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ga_core.llm import load_config
from repurchase_evaluation import SCHEMA_VERSION, score_response, serialize_prompt


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def dump(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error("Use --live for this explicit paid development run")
    if args.out.exists():
        parser.error("Use a new run directory; responses cannot be overwritten")
    questions = read_rows(args.audit / "development-questions-draft.jsonl")
    documents = {d["id"]: d for d in read_rows(args.audit / "development-source-corpus.jsonl")}
    prompts = {p["question_id"]: p for p in read_rows(args.prepared / "public-prompts.jsonl")}
    assert len(questions) == len(prompts) == 23
    assert all(q["split"] == "development" for q in questions)
    assert all(d["split_candidate"] == "development" for d in documents.values())
    for question in questions:
        system, user = serialize_prompt(question, documents)
        assert system == prompts[question["id"]]["system"] and user == prompts[question["id"]]["user"]
    config = load_config()
    if not config.ready:
        parser.error("Existing root Qwen configuration is missing; no call made")
    args.out.mkdir(parents=True)
    (args.out / "sources").mkdir()
    source_hashes = {}
    for path in (Path(__file__), ROOT / "repurchase_evaluation.py", ROOT / "ga_core/llm.py"):
        data = path.read_bytes()
        relative = path.relative_to(ROOT).as_posix()
        source_hashes[relative] = hashlib.sha256(data).hexdigest()
        target = args.out / "sources" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "scope": "full_context_development_pilot_not_RAG_memory_comparison",
        "schema_version": SCHEMA_VERSION, "provider": "qwen", "requested_model": config.model,
        "endpoint_host": urlsplit(config.base_url).hostname, "temperature": 0, "max_output_tokens": 2000,
        "workers": 3, "maximum_calls": len(questions), "automatic_retries": 0, "model_fallback": False,
        "reference_tier": "assistant_source_anchored_development_draft", "independent_test": False,
        "question_ids": [q["id"] for q in questions], "source_hashes": source_hashes,
        "input_hashes": {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (args.audit / "development-questions-draft.jsonl", args.audit / "development-source-corpus.jsonl", args.prepared / "public-prompts.jsonl")}}
    dump(args.out / "plan.json", manifest)
    def work(question):
        from openai import OpenAI
        prompt = prompts[question["id"]]
        started = time.perf_counter()
        record = {"question_id": question["id"], "requested_model": config.model, "status": "failed", "usage": {},
                  "prompt_sha256": hashlib.sha256((prompt["system"] + "\n" + prompt["user"]).encode()).hexdigest()}
        prediction = {"question_id": question["id"], "status": "failed"}
        try:
            with OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=90, max_retries=0) as client:
                response = client.chat.completions.create(model=config.model, temperature=0, max_tokens=2000,
                    messages=[{"role": "system", "content": prompt["system"]}, {"role": "user", "content": prompt["user"]}])
            choice = response.choices[0]
            record.update(response_id=response.id, response_model=response.model, finish_reason=choice.finish_reason,
                          raw=choice.message.content or "")
            if response.usage:
                record["usage"] = {"input_tokens": response.usage.prompt_tokens, "output_tokens": response.usage.completion_tokens}
            if choice.finish_reason != "stop":
                raise ValueError("Non-stop finish reason; no substitute response")
            payload = json.loads(record["raw"].strip())
            if not isinstance(payload, dict):
                raise ValueError("Response is not a JSON object")
            record["prediction"] = payload
            record["score"] = score_response(question, payload, documents)
            record["status"] = "parsed"
            if payload.get("question_id") == question["id"]:
                prediction = payload
            else:
                record["export_policy"] = "Mismatched model question ID retained raw; scoring export marks requested question failed"
        except Exception as exc:
            record["error_type"] = type(exc).__name__
            record["score"] = score_response(question, None, documents)
        record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        record["task_family"] = question["task_family"]
        record["stock_code"] = question["stock_code"]
        return record, prediction
    by_id, predictions = {}, {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(work, question) for question in questions]
        for future in as_completed(futures):
            record, prediction = future.result()
            by_id[record["question_id"]] = record
            predictions[record["question_id"]] = prediction
            ordered = [by_id[q["id"]] for q in questions if q["id"] in by_id]
            write_rows(args.out / "records.jsonl", ordered)
            write_rows(args.out / "predictions.jsonl", [predictions[r["question_id"]] for r in ordered])
            print(record["question_id"], record["status"], "schema", record["score"]["schema_valid"],
                  "draft_exact", record["score"]["exact_answer_correct"], flush=True)
    rows = [by_id[q["id"]] for q in questions]
    summary = {"actual_calls": len(rows), "parsed_responses": sum(r["status"] == "parsed" for r in rows),
        "failed_responses": sum(r["status"] != "parsed" for r in rows),
        "schema_valid": sum(r["score"]["schema_valid"] for r in rows),
        "draft_exact_correct": sum(r["score"]["exact_answer_correct"] for r in rows),
        "fields_correct": sum(r["score"]["fields_correct"] for r in rows), "fields_total": sum(r["score"]["fields_total"] for r in rows),
        "scheme_correct": sum(r["score"]["scheme_correct"] for r in rows),
        "validation_issues": dict(Counter(issue for r in rows for issue in r["score"]["validation_issues"])),
        "reported_usage": {key: sum(r["usage"].get(key, 0) for r in rows) for key in ("input_tokens", "output_tokens")},
        "response_models": sorted({r.get("response_model", "unreported") for r in rows}),
        "scope": manifest["scope"], "reference_tier": manifest["reference_tier"], "independent_test": False,
        "no_memory_advantage_claim": True}
    dump(args.out / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
