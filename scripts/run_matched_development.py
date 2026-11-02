"""Extract, prepare and run a matched development-only disclosure preflight.

Preparation is offline. Each extraction and answer live step requires --live;
reserved companies cannot be sent by this development runner.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ga_core.llm import load_config
from matched_disclosure import METHODS, EXTRACTION_SYSTEM, canonical, extraction_payload, admit_observations, prepare_prompt
from repurchase_evaluation import SCHEMA_VERSION, score_response
from scripts.extend_reserved_source_review import read_rows, write_rows


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def hashes():
    return {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in
            ["matched_disclosure.py", "repurchase_evaluation.py", "repurchase_identity.py", "repurchase_catalogue.py", "ga_core/llm.py", "scripts/run_matched_development.py"]}


def call(config, system, user, max_tokens):
    from openai import OpenAI
    started = time.perf_counter()
    row = {"status": "failed", "requested_model": config.model, "system": system, "user": user, "usage": {}}
    try:
        with OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=120, max_retries=0) as client:
            response = client.chat.completions.create(model=config.model, temperature=0, max_tokens=max_tokens,
                response_format={"type": "json_object"}, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        choice = response.choices[0]
        row.update(response_id=response.id, response_model=response.model, finish_reason=choice.finish_reason, raw=choice.message.content)
        if response.usage:
            row["usage"] = {"input_tokens": response.usage.prompt_tokens, "output_tokens": response.usage.completion_tokens}
        if response.model != config.model or choice.finish_reason != "stop":
            raise ValueError("Model mismatch or incomplete response")
        row.update(status="parsed", result=json.loads(row["raw"]))
    except Exception as exc:
        row["error_type"] = type(exc).__name__
    row["elapsed_seconds"] = round(time.perf_counter()-started, 3)
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=["extract", "readmit", "prepare", "run"])
    p.add_argument("--corpus", type=Path, required=True)
    p.add_argument("--questions", type=Path)
    p.add_argument("--question-id", action="append", default=[])
    p.add_argument("--source-id", action="append", default=[])
    p.add_argument("--memory", type=Path)
    p.add_argument("--prepared", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--budget", type=int, default=48000)
    p.add_argument("--top-k", type=int, default=16)
    p.add_argument("--live", action="store_true")
    a = p.parse_args()
    if a.out.exists():
        p.error("Use a new output directory")
    docs = {d["id"]: d for d in read_rows(a.corpus)}
    if any(d.get("split_candidate") != "development" for d in docs.values()):
        p.error("This runner accepts development corpus only")
    config = load_config()
    if a.operation in {"extract", "run"} and (not a.live or not config.ready):
        p.error("Explicit --live and existing Qwen configuration required")
    if a.operation in {"prepare", "run"} and not a.questions:
        p.error("Questions required")
    questions = read_rows(a.questions) if a.questions else []
    if any(q.get("split") != "development" for q in questions):
        p.error("Development questions only")
    if a.question_id:
        questions = [q for q in questions if q["id"] in a.question_id]
        if {q["id"] for q in questions} != set(a.question_id):
            p.error("Unknown question selection")
    a.out.mkdir(parents=True)
    (a.out / "calls").mkdir()
    for name in hashes():
        dest = a.out / "sources" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT/name).read_bytes())
    if a.operation in {"extract", "readmit"}:
        if a.operation == "readmit" and not a.memory:
            p.error("Retained extraction directory required for offline readmission")
        retained = {r["source_id"]: r for r in read_rows(a.memory / "extraction-records.jsonl")} if a.operation == "readmit" else {}
        selected = sorted(retained if a.operation == "readmit" else a.source_id or docs)
        if set(selected)-set(docs):
            p.error("Unknown source ID")
        write(a.out / "plan.json", {"scope": "blind_single_document_extraction_not_answer_evaluation", "model": config.model, "endpoint_host": urlsplit(config.base_url).hostname,
              "temperature": 0, "max_output_tokens": 5000, "automatic_retries": 0, "source_ids": selected,
              "source_hashes": hashes(), "source_text_sha256": {s: docs[s]["text_sha256"] for s in selected},
              "no_questions_or_reference_answers_in_prompt": True, "offline_readmission": a.operation == "readmit",
              "retained_extraction": str(a.memory.resolve()) if retained else None})
        observations, records = [], []
        for source in selected:
            d = docs[source]
            if retained:
                row = deepcopy(retained[source])
                if row["source_text_sha256"] != d["text_sha256"] or row["requested_model"] != config.model:
                    p.error("Retained extraction source changed")
                row["reused_response_no_new_call"] = True
                row["original_admission_status"] = row["status"]
                row["status"] = "parsed" if row.get("finish_reason") == "stop" and "result" in row else "failed"
            else:
                row = call(config, EXTRACTION_SYSTEM, canonical(extraction_payload(d)), 5000)
            row.update(source_id=source, source_text_sha256=d["text_sha256"])
            if row["status"] == "parsed":
                try:
                    accepted, rejected = admit_observations(d, row["result"])
                    row.update(status="ok" if accepted or not row["result"]["observations"] else "all_observations_rejected",
                               accepted=len(accepted), rejected=rejected)
                    observations.extend(accepted)
                except (ValueError, TypeError):
                    row["status"] = "extraction_schema_failure"
            records.append(row)
            write(a.out / "calls" / (source + ".json"), row)
            print(canonical({k: row.get(k) for k in ["source_id", "status", "accepted"]}), flush=True)
        write_rows(a.out / "observations.jsonl", observations)
        write_rows(a.out / "extraction-records.jsonl", records)
        write(a.out / "summary.json", {"calls": len(records), "sources": len(selected), "accepted_observations": len(observations),
              "statuses": dict(Counter(r["status"] for r in records)), "usage": {k: sum(r["usage"].get(k, 0) for r in records) for k in ["input_tokens", "output_tokens"]},
              "semantic_entailment_certified": False, "new_model_calls": 0 if retained else len(records)})
        return
    if a.operation == "prepare":
        observations, statuses, extraction_model, memory_hashes = [], {}, None, {}
        if a.memory:
            mp = json.loads((a.memory / "plan.json").read_text(encoding="utf-8"))
            extraction_model = mp["model"]
            memory_hashes = {n: hashlib.sha256((a.memory/n).read_bytes()).hexdigest() for n in ["plan.json", "observations.jsonl", "extraction-records.jsonl"]}
            for source, digest in mp["source_text_sha256"].items():
                if source not in docs or docs[source]["text_sha256"] != digest:
                    p.error("Memory/source snapshot mismatch")
            observations = read_rows(a.memory / "observations.jsonl")
            statuses = {r["source_id"]: r["status"] for r in read_rows(a.memory / "extraction-records.jsonl")}
        records = []
        for index, q in enumerate(questions):
            # Rotate answer order deterministically, independent of reference values.
            for method in METHODS[index % 5:] + METHODS[:index % 5]:
                prompt = prepare_prompt(q, docs, observations, statuses, method, budget=a.budget, top_k=a.top_k)
                records.append({"question_id": q["id"], **prompt})
        write_rows(a.out / "prompts.jsonl", records)
        plan = {"scope": "development_only_matched_preparation_not_held_out_results", "model": config.model, "endpoint_host": urlsplit(config.base_url).hostname, "extraction_model": extraction_model,
                "schema_version": SCHEMA_VERSION, "temperature": 0, "methods": list(METHODS), "max_output_tokens": 2400,
                "retrieval_parameters": {"type": "char_bigram_tfidf", "chunk_size": 1200, "overlap": 150, "top_k": a.top_k,
                                         "exact_public_source_id_lookup": True, "shared_field_aliases": True},
                "context_budget_policy": {"evidence_serialized_unicode_characters": a.budget, "common_task_overhead_excluded": True,
                                          "memory_notes_ceiling": min(8000, a.budget//3), "not_a_token_budget": True,
                                          "full_text_overflow": "failed_no_silent_truncation"},
                "memory_build_policy": "shared_question_blind_single_source_observations; current per scheme/field; same-day ties retained",
                "failure_policy": "no_retry_no_fallback_preserve_failures; incomplete_memory_no_answer_call; missing_answer_counts_wrong",
                "code_hashes": hashes(), "questions_sha256": hashlib.sha256(a.questions.read_bytes()).hexdigest(),
                "corpus_sha256": hashlib.sha256(a.corpus.read_bytes()).hexdigest(),
                "prompts_sha256": hashlib.sha256((a.out / "prompts.jsonl").read_bytes()).hexdigest(),
                "question_ids": [q["id"] for q in questions], "statuses": dict(Counter(r["status"] for r in records)),
                "memory_path": str(a.memory.resolve()) if a.memory else None, "memory_artifact_hashes": memory_hashes, "held_out_run_permitted": False}
        write(a.out / "plan.json", plan)
        print(canonical({"questions": len(questions), "planned_answers": len(records), "statuses": plan["statuses"], "model_calls": 0}))
        return
    if not a.prepared:
        p.error("Prepared manifest required")
    plan = json.loads((a.prepared / "plan.json").read_text(encoding="utf-8"))
    if plan["code_hashes"] != hashes() or plan["model"] != config.model or plan["endpoint_host"] != urlsplit(config.base_url).hostname or plan["extraction_model"] not in {None, config.model}:
        p.error("Code or model changed since preparation")
    for path, key in [(a.questions, "questions_sha256"), (a.corpus, "corpus_sha256"), (a.prepared / "prompts.jsonl", "prompts_sha256")]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != plan[key]:
            p.error("Prepared input hash mismatch")
    for name, digest in plan["memory_artifact_hashes"].items():
        if hashlib.sha256((Path(plan["memory_path"])/name).read_bytes()).hexdigest() != digest:
            p.error("Prepared memory artifact changed")
    by_q = {q["id"]: q for q in questions}
    if set(plan["question_ids"]) != set(by_q):
        p.error("Prepared question selection mismatch")
    records = []
    write(a.out / "plan.json", {**plan, "scope": "development_end_to_end_diagnostic_not_generalization_evidence"})
    for prompt in read_rows(a.prepared / "prompts.jsonl"):
        q = by_q[prompt["question_id"]]
        row = {"question_id": q["id"], "method": prompt["method"], "status": prompt["status"], "usage": {}, "supplied_source_ids": prompt.get("supplied_source_ids", [])}
        if prompt["status"] == "prepared":
            row.update(call(config, prompt["system"], prompt["user"], 2400))
        selected_q = deepcopy(q)
        selected_q["source_ids"] = row["supplied_source_ids"]
        row["score"] = score_response(selected_q, row.get("result"), docs)
        records.append(row)
        write(a.out / "calls" / (q["id"] + "_" + prompt["method"] + ".json"), row)
        print(canonical({"question_id": q["id"], "method": prompt["method"], "status": row["status"]}), flush=True)
    write_rows(a.out / "records.jsonl", records)
    write(a.out / "summary.json", {"questions": len(questions), "answer_slots": len(records),
          "actual_answer_calls": sum("raw" in r or "error_type" in r for r in records),
          "statuses": dict(Counter(r["status"] for r in records)),
          "exact_answer_counts_for_development_debugging_only": {m: sum(r["score"]["exact_answer_correct"] for r in records if r["method"] == m) for m in METHODS},
          "answer_usage": {k: sum(r["usage"].get(k, 0) for r in records) for k in ["input_tokens", "output_tokens"]},
          "shared_extraction_cost_excluded_from_answer_usage_report_separately": True, "memory_gain_established": False})


if __name__ == "__main__":
    main()
