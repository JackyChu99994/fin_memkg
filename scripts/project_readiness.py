"""Read-only whole-project evidence inventory; never scores drafts or calls LLMs.

Run from any directory. Generated JSON belongs in ignored experiment storage.
Missing optional RealFin coverage is reported separately from course requirements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules" / "l0l4-memory"


def rows(path):
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix == ".json" else [json.loads(line) for line in text.splitlines() if line.strip()]


def inventory():
    promised = ["modules/l0l4-memory/docs/报告写作包.md",
                "modules/l0l4-memory/docs/全局复盘与答辩防守.md",
                "modules/l0l4-memory/experiments/hallucination_demo.py",
                "modules/l0l4-memory/scripts/car_scan.py"]
    legacy = rows(ROOT / "memory/L4_archive/real_fin_events_12.json")
    corpus_path = MODULE / "data/experiments/lifecycle-expanded40-20261030/corpus.jsonl"
    reference_path = MODULE / "data/experiments/lifecycle-expanded40-references-20261030/references-ai-draft-final.jsonl"
    corpus, references = rows(corpus_path), rows(reference_path)
    partitions = {name: {"companies": sorted({row["stock_code"] for row in corpus if row["split"] == name}),
                         "documents": sum(row["split"] == name for row in corpus)}
                  for name in ("development", "test_reserved")}
    reviewed = [row for row in references if row.get("review_status") == "reviewed" and row.get("reviewer", "").strip()]
    overlap = sorted(set(partitions["development"]["companies"]) & set(partitions["test_reserved"]["companies"]))
    qualification = []
    for row in references:
        draft = row.get("adjudicated") or row.get("draft") or {}
        flags = []
        if row.get("review_status") != "reviewed" or not row.get("reviewer", "").strip():
            flags.append("reference_not_reviewed")
        if row.get("validation_errors"):
            flags.append("source_spans_require_adjudication")
        if draft.get("scheme_relation") != "SAME_SCHEME":
            flags.append("scheme_identity_not_confirmed_same")
        if draft.get("initial_approval_year") != 2024:
            flags.append("original_approval_not_confirmed_2024")
        qualification.append({"id": row["id"], "stock_code": row["stock_code"], "split": row["split"], "flags": flags,
                              "formal_reference_ready": not flags})
    return {"schema": "whole-project-readiness-v1", "root": str(ROOT),
        "scope": "Repository plus local artifacts; a file's presence is not proof of correctness",
        "architecture": {
            "root_workbench": {"exists": (ROOT / "agent_loop.py").exists(), "role": "Qwen thesis KG, state updates, propagation, UI and market-data workspace"},
            "ga_core": {"exists": (ROOT / "ga_core/loop.py").exists(), "role": "generic tool loop with file-level L0-L4 access; live financial-task integration not established by fake-client tests"},
            "module_b": {"exists": (MODULE / "pipeline.py").exists(), "role": "parallel typed-relation KG application, separate store and archive; snapshot reader bridges market data"},
            "factual_adapter": {"exists": (MODULE / "factual_memory.py").exists(), "role": "experimental lifecycle observations; not an ablation of graph topology"}},
        "handoff_missing_resources": [path for path in promised if not (ROOT / path).exists()],
        "legacy_real12": {"events": len(legacy), "events_without_original_url": sum(not (row.get("latest_event", {}).get("url") or row.get("latest_event", {}).get("source_url")) for row in legacy),
                          "status": "Inherited source times and future-return labels are not independently verified by this inventory"},
        "expanded_corpus": {"documents": len(corpus), "candidate_companies": len({row["stock_code"] for row in corpus}),
            "pdf_pages": sum(row.get("pages", 0) for row in corpus), "partitions": partitions,
            "cross_partition_companies": overlap, "reference_drafts": len(references), "reviewed_references": len(reviewed),
            "formal_reference_ready": sum(row["formal_reference_ready"] for row in qualification), "qualification": qualification},
        "course_scope": {"required": ["explicit KG and actual downstream use", "extraction experiments", "demo", "report of at least 5000 characters excluding references", "PPT, dataset/code, team work and peer review"],
            "not_mandated": ["state memory must outperform RAG", "profitable stock-return prediction", "complete official RealFin-40", "token saving of a predetermined percentage"]},
        "cautions": ["Neither software tests nor repeated cutoffs count as independent real events",
                     "Matched quotation text is not proof that a state follows from the quotation",
                     "No external call, production-store mutation, or reviewed-label promotion is performed"],
        "input_hashes": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in (corpus_path, reference_path) if path.exists()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = inventory()
    if args.out:
        if args.out.exists():
            parser.error("Use a new output file")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"architecture_components": len(result["architecture"]),
        "missing_handoff_resources": len(result["handoff_missing_resources"]),
        "candidate_companies": result["expanded_corpus"]["candidate_companies"],
        "documents": result["expanded_corpus"]["documents"],
        "reviewed_references": result["expanded_corpus"]["reviewed_references"],
        "formal_reference_ready": result["expanded_corpus"]["formal_reference_ready"]}))


if __name__ == "__main__":
    main()
