"""Complete the development study, freeze the protocol, then run reserved once.

Each paid phase requires --live. Every source call and answer slot is retained;
source extraction is shared, question blind, and never repaired on reserved data.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ga_core.llm import load_config
from matched_disclosure import METHODS, EXTRACTION_SYSTEM, canonical, extraction_payload, admit_observations, prepare_prompt
from repurchase_evaluation import PUBLIC_INSTRUCTIONS, SCHEMA_VERSION, score_response
from benchmark_readiness import check_readiness
from scripts.extend_reserved_source_review import read_rows, write_rows
from scripts.run_matched_development import call, write, hashes as base_hashes

BASE = ROOT / "modules/l0l4-memory/data/experiments"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_hashes():
    return {**base_hashes(), **{n: sha(ROOT/n) for n in
            ["scripts/complete_stage5_study.py", "benchmark_readiness.py"]}}


def cohort(partition):
    if partition == "development":
        qpath = BASE / "development-identity-audit-v3-20261101/development-questions-draft.jsonl"
        cpath = BASE / "development-identity-audit-v3-20261101/development-source-corpus.jsonl"
    else:
        qpath = BASE / "reserved-source-questions-v7-20261102/questions-source-candidates.jsonl"
        cpath = BASE / "diverse-announcements-20261031/corpus-split-v2.jsonl"
    questions = read_rows(qpath)
    ids = {s for q in questions for s in q["source_ids"]}
    docs = {d["id"]: d for d in read_rows(cpath) if d["id"] in ids}
    if set(docs) != ids or any(d["split_candidate"] != partition for d in docs.values()):
        raise ValueError("Cohort source/split mismatch")
    if any(q["split"] != partition for q in questions):
        raise ValueError("Question split mismatch")
    return questions, docs, qpath, cpath


def protocol(config):
    return {"model": config.model, "endpoint_host": urlsplit(config.base_url).hostname, "temperature": 0,
            "methods": list(METHODS), "retrieval_parameters": {"type": "character_bigram_tfidf", "top_k": 16, "chunk_size": 1200, "overlap": 150,
                "exact_public_source_ids": True, "shared_chinese_field_aliases": True},
            "context_budget_policy": {"serialized_evidence_unicode_characters": 48000, "common_task_overhead_excluded": True,
                "memory_notes_ceiling": 8000, "full_text_overflow": "failed_no_truncation", "not_equal_token_budget": True},
            "scoring_version": sha(ROOT / "repurchase_evaluation.py"),
            "reference_version": sha(BASE / "reserved-source-questions-v7-20261102/questions-source-candidates.jsonl"),
            "source_version": sha(BASE / "diverse-announcements-20261031/corpus-split-v2.jsonl"),
            "prompt_version": hashlib.sha256((EXTRACTION_SYSTEM + PUBLIC_INSTRUCTIONS).encode()).hexdigest(),
            "memory_build_policy": "single-source blind shared extraction; latest scheme/field with same-day ties retained; no gold injected",
            "failure_policy": "zero retries/fallback; raw failures retained; all-rejected source blocks memory slots; missing slots score incorrect",
            "code_hashes": code_hashes(), "max_extraction_output_tokens": 5000, "max_answer_output_tokens": 2400,
            "workers": 4, "repeats": 1, "sampling": "purposive_AI_silver_challenge_set_not_population_random",
            "reference_caveat": "22 negative references use full-context Qwen audits and assistant quotation/rationale review, not independent human gold"}


def execute(out, partition, config, frozen=None):
    questions, docs, qpath, cpath = cohort(partition)
    out.mkdir(parents=True)
    (out / "source-calls").mkdir()
    (out / "answer-calls").mkdir()
    for name in code_hashes():
        dest = out / "sources" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT/name).read_bytes())
    plan = {"partition": partition, "created_at": datetime.now(timezone.utc).isoformat(),
            "protocol": protocol(config), "questions_sha256": sha(qpath), "source_corpus_sha256": sha(cpath),
            "question_ids": [q["id"] for q in questions], "source_ids": sorted(docs),
            "source_text_sha256": {sid: d["text_sha256"] for sid, d in docs.items()},
            "frozen_manifest_sha256": sha(frozen) if frozen else None,
            "maximum_paid_calls": len(docs) + len(questions)*len(METHODS), "uses_preflight_extractions": False}
    write(out / "plan.json", plan)

    def extract(sid):
        d = docs[sid]
        row = call(config, EXTRACTION_SYSTEM, canonical(extraction_payload(d)), 5000)
        row.update(source_id=sid, source_text_sha256=d["text_sha256"])
        accepted, rejected = [], []
        if row["status"] == "parsed":
            try:
                accepted, rejected = admit_observations(d, row["result"])
                row["status"] = "ok" if accepted or not row["result"]["observations"] else "all_observations_rejected"
            except (ValueError, TypeError):
                row["status"] = "extraction_schema_failure"
        row.update(accepted=len(accepted), rejected=rejected)
        write(out / "source-calls" / (sid + ".json"), row)
        print(canonical({"phase": "extract", "partition": partition, "source_id": sid, "status": row["status"], "accepted": len(accepted)}), flush=True)
        return row, accepted

    with ThreadPoolExecutor(max_workers=4) as pool:
        extracted = list(pool.map(extract, sorted(docs)))
    source_records = [r for r, _ in extracted]
    observations = [o for _, rows in extracted for o in rows]
    write_rows(out / "extraction-records.jsonl", source_records)
    write_rows(out / "observations.jsonl", observations)
    statuses = {r["source_id"]: r["status"] for r in source_records}
    prompts = []
    for i, q in enumerate(questions):
        for method in METHODS[i % 5:] + METHODS[:i % 5]:
            prompts.append({"question_id": q["id"], **prepare_prompt(q, docs, observations, statuses, method)})
    write_rows(out / "prompts.jsonl", prompts)
    by_q = {q["id"]: q for q in questions}

    def answer(prompt):
        q = by_q[prompt["question_id"]]
        row = {"question_id": q["id"], "stock_code": q["stock_code"], "target_scheme_reference_for_scoring_only": q["target_scheme"],
               "method": prompt["method"], "status": prompt["status"], "usage": {},
               "supplied_source_ids": prompt.get("supplied_source_ids", []), "evidence_characters": prompt.get("evidence_characters", 0),
               "memory_observations": prompt.get("machine_observations", 0), "extraction_failures": prompt.get("extraction_failures", [])}
        if prompt["status"] == "prepared":
            row.update(call(config, prompt["system"], prompt["user"], 2400))
            row["api_attempted"] = True
        else:
            row["api_attempted"] = False
        actual = deepcopy(q)
        actual["source_ids"] = row["supplied_source_ids"]
        row["score"] = score_response(actual, row.get("result"), docs)
        write(out / "answer-calls" / (q["id"] + "_" + prompt["method"] + ".json"), row)
        print(canonical({"phase": "answer", "partition": partition, "question_id": q["id"], "method": prompt["method"], "status": row["status"]}), flush=True)
        return row

    with ThreadPoolExecutor(max_workers=4) as pool:
        answers = list(pool.map(answer, prompts))
    write_rows(out / "records.jsonl", answers)
    summary = {"partition": partition, "questions": len(questions), "companies": len({q["stock_code"] for q in questions}),
               "unique_sources": len(docs), "answer_slots": len(answers), "source_calls": len(source_records),
               "answer_calls": sum(r["api_attempted"] for r in answers),
               "extraction_statuses": dict(Counter(r["status"] for r in source_records)), "accepted_observations": len(observations),
               "quarantined_observations": sum(len(r["rejected"]) for r in source_records),
               "answer_statuses": dict(Counter(r["status"] for r in answers)),
               "methods": {m: {"questions": len(questions), "correct": sum(r["score"]["exact_answer_correct"] for r in answers if r["method"] == m),
                   "schema_valid": sum(r["score"]["schema_valid"] for r in answers if r["method"] == m),
                   "answer_calls": sum(r["api_attempted"] for r in answers if r["method"] == m),
                   "answer_input_tokens": sum(r["usage"].get("input_tokens", 0) for r in answers if r["method"] == m),
                   "answer_output_tokens": sum(r["usage"].get("output_tokens", 0) for r in answers if r["method"] == m)} for m in METHODS},
               "usage": {phase: {key: sum(r["usage"].get(key, 0) for r in rows) for key in ["input_tokens", "output_tokens"]}
                         for phase, rows in [("shared_extraction", source_records), ("answers", answers)]},
               "reference_tier": "AI_silver_not_independent_human_gold", "retries": 0, "protocol_hashes_unchanged": code_hashes() == plan["protocol"]["code_hashes"]}
    write(out / "summary.json", summary)
    print(canonical(summary), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=["development", "freeze", "reserved"])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--development", type=Path)
    p.add_argument("--freeze", type=Path)
    p.add_argument("--live", action="store_true")
    a = p.parse_args()
    if a.out.exists():
        p.error("New immutable output directory required")
    cfg = load_config()
    if not cfg.ready:
        p.error("Existing Qwen configuration unavailable")
    if a.phase == "freeze":
        if not a.development:
            p.error("Completed development study required")
        ds = json.loads((a.development / "summary.json").read_text(encoding="utf-8"))
        dp = json.loads((a.development / "plan.json").read_text(encoding="utf-8"))
        if ds["questions"] != 23 or ds["answer_slots"] != 115 or not ds["protocol_hashes_unchanged"] or dp["protocol"] != protocol(cfg):
            p.error("Development incomplete or code/config changed; cannot freeze")
        qs, docs, qpath, cpath = cohort("test_reserved")
        assignments = {d["stock_code"]: "test_reserved" for d in docs.values()}
        ready = check_readiness(list(docs.values()), assignments, qs, protocol(cfg))
        if not ready["exploratory_run_ready"]:
            p.error("Reserved references/protocol fail readiness")
        a.out.mkdir(parents=True)
        frozen = {"created_at": datetime.now(timezone.utc).isoformat(), "protocol": protocol(cfg),
                  "reference_sha256": sha(qpath), "corpus_sha256": sha(cpath), "development_summary_sha256": sha(a.development / "summary.json"),
                  "questions": len(qs), "companies": len(assignments), "eligible_sources": len(docs),
                  "maximum_paid_calls": len(docs) + len(qs)*5, "readiness": ready,
                  "scope": "one_shot_purposive_AI_silver_exploration_not_human_gold_or_population_sample"}
        write(a.out / "freeze.json", frozen)
        print(canonical({"freeze_created": True, "questions": len(qs), "maximum_paid_calls": frozen["maximum_paid_calls"]}))
        return
    if not a.live:
        p.error("--live required for paid phases")
    if a.phase == "reserved":
        if not a.freeze:
            p.error("Frozen protocol required")
        frozen = json.loads(a.freeze.read_text(encoding="utf-8"))
        _, _, qp, cp = cohort("test_reserved")
        if frozen["protocol"] != protocol(cfg) or frozen["reference_sha256"] != sha(qp) or frozen["corpus_sha256"] != sha(cp):
            p.error("Frozen code/config/reference/source changed")
        execute(a.out, "test_reserved", cfg, a.freeze)
    else:
        execute(a.out, "development", cfg)


if __name__ == "__main__":
    main()
