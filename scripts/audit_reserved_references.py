"""Apply source-backed annotation errata without rebuilding or qualifying a bank.

This offline audit changes references only. It never changes compared methods,
claims human review, or treats cue searches as a proof of absent evidence.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from repurchase_identity import compact_with_offsets, source_span, validate_span
from reserved_source_templates import first_purchase


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path, records):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


COMPLETION_ERRATA = {
    "300454": "公司回购股份方案已实施完毕",
    "603777": "公司已完成回购",
    "002611": "回购股份实施完成",
    "688349": "公司已完成本次回购",
}


def audit(questions, documents):
    updated, errata, negatives = deepcopy(questions), [], []
    for q in updated:
        old = deepcopy(q)
        if q["id"] == "RSV_SOURCE_300200_historical":
            d = documents[q["reference_proofs"][0]["source_id"]]
            actual = first_purchase(d)
            assert actual and actual[0] == "2024-02-02"
            q["reference_draft"]["first_purchase_date"] = actual[0]
            q["reference_proofs"] = [{**actual[1], "fields": ["first_purchase_date"]}]
        if q["benchmark_family"] == "stage" and q["stock_code"] in COMPLETION_ERRATA:
            d = documents[q["reference_proofs"][0]["source_id"]]
            proof = source_span(d, re.escape(COMPLETION_ERRATA[q["stock_code"]]))
            assert proof
            q["reference_draft"]["repurchase_stage"] = "COMPLETED"
            q["reference_proofs"] = [{**proof, "fields": ["repurchase_stage"]}]
        if old["reference_draft"] != q["reference_draft"]:
            errata.append({"question_id": q["id"], "kind": "source_backed_reference_erratum",
                           "old_answer": old["reference_draft"], "new_answer": q["reference_draft"],
                           "old_proofs": old["reference_proofs"], "new_proofs": q["reference_proofs"],
                           "review_origin": "AI_assisted_source_inspection_not_independent_human_gold"})
        if q["benchmark_family"] == "insufficient":
            q["reference_missing_reason"] = (
                "Candidate insufficiency concerns the target original scheme only. "
                "An earlier scheme's first-purchase date does not answer this question. "
                "All eligible sources require semantic review; unmatched date patterns do not prove absence."
            )
            cues = []
            for sid in q["source_ids"]:
                d = documents[sid]
                compact, _ = compact_with_offsets(d["text"])
                windows = []
                for match in re.finditer("首次|尚未|未实施|第二次|第二期", compact):
                    fragment = compact[max(0, match.start()-85):match.end()+140]
                    p = source_span(d, re.escape(fragment))
                    assert p and validate_span(d, p)
                    windows.append(p)
                dates = list(dict.fromkeys(re.findall(r"\d{4}年\d{1,2}月\d{1,2}日", compact)))
                cues.append({"source_id": sid, "title": d["title"], "disclosure_date": d["disclosure_date"],
                             "calendar_mentions": dates, "cue_windows": windows,
                             "scope_status": "requires_target_scheme_semantic_review"})
            negatives.append({"question_id": q["id"], "target_scheme": q["target_scheme"],
                              "as_of": q["as_of"], "eligible_sources": cues,
                              "absence_certified": False, "human_reviewed": False})
        q["reference_version"] = "source-audit-v3-20261101"
        q["source_qualification"] = "pending"
        q["human_reviewed"] = False
        q["formal_evaluation_ready"] = False
        for p in [q["identity_proof"], *q["reference_proofs"]]:
            assert p["source_id"] in q["source_ids"] and validate_span(documents[p["source_id"]], p)
    return updated, errata, negatives


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new output directory; earlier references must be retained")
    base = ROOT / "modules/l0l4-memory/data/experiments"
    original = base / "reserved-source-questions-v2-20261101/questions-source-candidates.jsonl"
    corpus = base / "diverse-announcements-20261031/corpus-split-v2.jsonl"
    documents = {d["id"]: d for d in rows(corpus) if d["split_candidate"] == "test_reserved"}
    updated, errata, negatives = audit(rows(original), documents)
    assert len(updated) == 79 and len(errata) == 5 and len(negatives) == 25
    args.out.mkdir(parents=True)
    write_rows(args.out / "questions-source-candidates.jsonl", updated)
    write_rows(args.out / "reference-errata.jsonl", errata)
    write_rows(args.out / "insufficiency-review-packets.jsonl", negatives)

    # Title strata are acquisition leads, not confirmed event categories.
    selected = json.loads((corpus.parent / "selected-companies.json").read_text(encoding="utf-8"))
    exclusions = {"603280": "equipment_financing_lease_buyback_guarantee_not_issuer_share_repurchase",
                  "688639": "generic_share_repurchase_policy_not_specific_scheme_amendment",
                  "605377": "generic_share_repurchase_policy_not_specific_scheme_amendment"}
    explicit = {"301042": "repurchase_window_wording_correction",
                "600568": "projected_share_structure_correction",
                "688016": "funding_source_wording_correction"}
    anchor_rows = []
    for item in selected:
        a = item["anchor"]
        sid = "CNINFO_" + a["announcementId"]
        if item["acquisition_stratum"] != "correction" or sid not in documents:
            continue
        code = a["secCode"]
        anchor_rows.append({"stock_code": code, "source_id": sid, "title": documents[sid]["title"],
                            "anchor_scope": exclusions.get(code, explicit.get(code, "paired_original_and_semantic_review_required")),
                            "exclude_anchor_from_scheme_update_pool": code in exclusions,
                            "exclude_company_or_other_documents": False, "human_reviewed": False})
    assert len(anchor_rows) == 15
    write_rows(args.out / "correction-anchor-scope.jsonl", anchor_rows)
    conflict_doc = documents["CNINFO_1223041731"]
    conflict = {"source_id": conflict_doc["id"], "kind": "source_internal_currency_unit_conflict",
                "proofs": [source_span(conflict_doc, re.escape(t)) for t in
                           ["不低于人民币8,000万元", "不低于人民币8,000元"]],
                "pdf_visual_check": "both_units_present_on_original_pdf_pages_1_and_2",
                "single_budget_reference_allowed": False,
                "effect_on_existing_stage_question": "no_amount_field_requested_no_stage_change",
                "human_reviewed": False}
    assert all(p and validate_span(conflict_doc, p) for p in conflict["proofs"])
    write_rows(args.out / "source-anomalies.jsonl", [conflict])
    summary = {"candidate_questions": len(updated), "answer_errata": len(errata),
               "insufficient_packets": len(negatives), "correction_anchors": len(anchor_rows),
               "excluded_anchors_not_companies": len(exclusions), "source_unit_conflicts": 1,
               "stage_class_counts": dict(Counter(q["reference_draft"]["repurchase_stage"] for q in updated if q["benchmark_family"] == "stage")),
               "formal_evaluation_ready": 0, "human_reviewed": 0, "model_calls": 0,
               "method_outputs_modified": False,
               "original_bank_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
               "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest()}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    for name in ["scripts/audit_reserved_references.py", "reserved_source_templates.py"]:
        target = args.out / "sources" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
