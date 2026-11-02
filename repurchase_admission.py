"""Reference-free typed-claim admission; preserves raw model output.

Passing guards means a machine claim can be inspected, not that it is true.
"""
from decimal import InvalidOperation
import math
import re
from repurchase_evaluation import normalize_date, normalize_field


def project_machine_claim(public_task, prediction):
    issues, warnings = [], []
    if not isinstance(prediction, dict):
        return {"status": "quarantined", "issues": ["response_not_object"], "facts": []}
    if prediction.get("question_id") != public_task["question_id"]:
        issues.append("question_id_mismatch")
    if prediction.get("status") != "answered":
        return {"status": "no_admitted_answer", "issues": issues, "facts": [], "raw_prediction": prediction}
    answer = prediction.get("answer")
    if not isinstance(answer, dict):
        answer = {}
        issues.append("answer_not_object")
    if set(answer) != set(public_task["requested_fields"]):
        issues.append("answer_field_set_mismatch")
    for key in set(answer) & set(public_task["requested_fields"]):
        try:
            if key in {"before", "after"}:
                value = answer[key]
                if isinstance(value, bool) or not isinstance(value, (str, int, float)) or (isinstance(value, float) and not math.isfinite(value)):
                    raise ValueError("Correction values must be finite scalars")
            else:
                normalize_field(key, answer[key])
        except (ValueError, InvalidOperation):
            issues.append("invalid_field:" + key)
    docs = {d["id"]: d for d in public_task["documents"]}
    citations = prediction.get("evidence_ids")
    if not isinstance(citations, list) or not citations or not all(isinstance(i, str) for i in citations):
        issues.append("invalid_citations")
        citations = []
    for ident in citations:
        if ident not in docs or docs[ident]["disclosure_date"] >= public_task["as_of"][:10]:
            issues.append("unsupplied_or_future_citation")
    primary = answer.get("primary_issuer_source")
    if primary is not None:
        if not isinstance(primary, str) or primary not in docs:
            issues.append("primary_source_not_supplied")
        elif re.search(r"核查意见|法律意见", docs[primary]["title"]):
            issues.append("auxiliary_opinion_cannot_be_primary_issuer_source")
    scheme = prediction.get("target_scheme")
    prefix = public_task["target_scheme_prefix"]
    if not isinstance(scheme, str) or not scheme.startswith(prefix):
        issues.append("invalid_scheme_prefix")
    else:
        try:
            normalized_day = normalize_date(scheme[len(prefix):])
            if scheme != prefix + normalized_day:
                issues.append("noncanonical_scheme_identifier")
        except ValueError:
            issues.append("invalid_scheme_date")
    associations = answer.get("source_approval_dates")
    scheme_nodes = []
    if isinstance(associations, dict):
        if set(associations) != set(public_task.get("requested_source_ids", [])):
            issues.append("comparison_source_set_mismatch")
        for source, day in associations.items():
            try:
                normalized = normalize_date(day)
                scheme_nodes.append({"source_id": source, "scheme_id": prefix + normalized,
                                     "original_board_date_claim": normalized})
            except ValueError:
                issues.append("invalid_comparison_date")
        if scheme_nodes and scheme != prefix + max(n["original_board_date_claim"] for n in scheme_nodes):
            warnings.append("model_target_selection_disagrees_with_comparison_mapping; preserve both mapped schemes")
    elif isinstance(scheme, str) and not issues:
        scheme_nodes = [{"scheme_id": scheme}]
    return {"status": "quarantined" if issues else "machine_claim_pending_semantic_review", "issues": issues,
            "warnings": warnings, "raw_prediction": prediction, "scheme_nodes": scheme_nodes if not issues else [],
            "facts": [] if issues else [{"field": key, "claimed_value": value, "evidence_ids": citations} for key, value in answer.items()],
            "human_verified": False, "semantic_entailment_verified": False, "original_scores_unchanged": True}
