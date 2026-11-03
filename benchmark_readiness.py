"""Integrity and declared-protocol checks, not certification of reference truth."""
from collections import Counter
from repurchase_identity import validate_span
from repurchase_evaluation import build_public_task

FAMILIES = {"stage", "historical", "multi_scheme", "update", "evidence_trace", "insufficient"}
METHODS = {"full_text", "tfidf_rag", "append_memory", "current_flat", "graph_assisted_retrieval"}


def check_readiness(documents, assignments, questions, protocol=None):
    docs = {d["id"]: d for d in documents}
    reserved_codes = {code for code, split in assignments.items() if split == "test_reserved"}
    errors = []
    ids = [q.get("id") for q in questions]
    if not all(isinstance(ident, str) and ident for ident in ids) or len(set(ids)) != len(ids):
        errors.append("missing_or_duplicate_question_ids")
    families = Counter(q.get("benchmark_family", "unassigned") for q in questions)
    for q in questions:
        ident = str(q.get("id", "unknown"))
        if q.get("stock_code") not in reserved_codes or q.get("split") != "test_reserved":
            errors.append(ident + ":not_reserved_company")
        if q.get("source_qualification") != "source_checked":
            errors.append(ident + ":source_identity_or_sufficiency_pending")
        if q.get("reference_tier") not in {"source_anchored_silver", "owner_reviewed", "independent_human_gold"}:
            errors.append(ident + ":reference_tier_not_declared")
        if q.get("reference_answerability") == "insufficient":
            if q.get("evidence_policy") not in {"natural_archive_gap", "synthetic_removed_sources"}:
                errors.append(ident + ":missing_evidence_policy_not_declared")
            if not q.get("reference_missing_reason"):
                errors.append(ident + ":missing_reference_insufficiency_reason")
        elif not q.get("reference_proofs"):
            errors.append(ident + ":answer_has_no_source_proof")
        if q.get("benchmark_family") == "insufficient" and q.get("reference_answerability") != "insufficient":
            errors.append(ident + ":insufficient_family_has_no_insufficient_reference")
        try:
            for source in q["source_ids"]:
                if docs[source]["stock_code"] != q["stock_code"]:
                    raise ValueError("Wrong company source")
            build_public_task(q, docs)
            for proof in q.get("reference_proofs", []):
                if proof["source_id"] not in q["source_ids"] or not validate_span(docs[proof["source_id"]], proof):
                    raise ValueError("Invalid proof")
        except (KeyError, TypeError, ValueError):
            errors.append(ident + ":input_schema_cutoff_or_source_integrity_failure")
    required_protocol = {"model", "temperature", "methods", "retrieval_parameters", "context_budget_policy", "scoring_version", "reference_version",
                         "prompt_version", "source_version", "memory_build_policy", "failure_policy"}
    protocol_ready = isinstance(protocol, dict) and required_protocol <= set(protocol)
    if protocol_ready:
        protocol_ready = (set(protocol["methods"]) == METHODS and bool(protocol["model"])
                          and all(bool(protocol[key]) for key in required_protocol - {"methods", "temperature"}))
    missing_families = sorted(FAMILIES - set(families))
    ready = bool(questions) and not errors and not missing_families and bool(protocol_ready)
    human_gold_declared = bool(questions) and all(q.get("reference_tier") == "independent_human_gold"
        and q.get("human_reviewed") is True and len(set(q.get("independent_reviewers", []))) >= 2 for q in questions)
    return {"reserved_companies_available": len(reserved_codes), "questions": len(questions),
            "question_companies": len({q.get("stock_code") for q in questions}), "family_counts": dict(families),
            "missing_families": missing_families, "question_errors": errors, "method_protocol_declared": bool(protocol_ready),
            "exploratory_run_ready": ready, "declared_independent_human_gold_ready": ready and human_gold_declared,
            "review_authenticity_automatically_certified": False, "model_calls": 0,
            "note": "Qualified silver references may support a declared exploratory comparison; human gold is a separate claim"}
