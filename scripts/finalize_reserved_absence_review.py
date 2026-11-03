"""Record assistant-reviewed citation repairs to Qwen full-context silver audits.

The source reviewer was Qwen; the assistant checks audit scope, exact quotation
repairs and conservative rationale. This is not independent human validation.
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
from repurchase_identity import source_span, validate_span
from repurchase_evaluation import build_public_task
from scripts.extend_reserved_source_review import read_rows, write_rows

VERSION = "source-silver-v7-20261102"
# Explicit offline inspection decisions, not fuzzy matching or global cleanup.
QUOTE_REPAIRS = {
    "公司于2023年5月24日召开第七届董事会第八次会议审议通过了《关于回购公司股份方案的议案》":
        ("CNINFO_1216896892", "公司于2023年5月24日召开第七届董事会第八次会议审议通过了《关于回购公司股份方案的[Page3]议案》", "preserve_original_page_marker"),
    "（一）首次回购股份事实发生的次一交易日予以披露;":
        ("CNINFO_1219140670", "（一）首次回购股份事实发生的次一交易日予以披露；", "restore_original_punctuation"),
    "公司在回购期限内根据市场情况择机做出回购决策并予以实施.":
        ("CNINFO_1218578369", "公司在回购期限内根据市场情况择机做出回购决策并予以实施。", "restore_original_punctuation"),
    "公司拟使用自有资金以集中竞价交易方式回购公司股份，用作员工持股计划或股权激励。":
        ("CNINFO_1212146746", "拟使用自有资金以集中竞价交易方式回购公司股份，用作员工持股计划或股权激励。", "remove_fabricated_leading_word"),
    "公司董事会将在回购期限内根据市场情况择机作出回购决策并予以实施.":
        ("CNINFO_1212146746", "公司董事会将在回购期限内根据市场情况择机作出回购决策并予以实施。", "restore_original_punctuation"),
    "5、回购期间的信息披露安排1、在首次回购股份事实发生的次日予以披露；":
        ("CNINFO_1215526653", "在首次回购股份事实发生的次日予以披露；", "remove_invented_section_heading"),
    "（5）本次回购方案不代表公司将在二级市场回购公司股份的承诺，公司在回购期限内根据市场情况择机做出回购决策并予以实施。":
        ("CNINFO_1215526653", "（5）本次回购方案不代表公司将在二级市场回购公司股份的承诺，公司将在回购期限内根据市场情况择机做出回购决策并予以实施。", "restore_omitted_character"),
    "回购股份实施期限：自董事会审议通过本次回购股份方案之日起6个月内。":
        ("CNINFO_1220559926", "回购股份期限：自董事会审议通过本次回购股份方案之日起6个月内。", "restore_original_field_wording"),
    "公司将根据董事会决议，在回购期限内根据市场情况择机作出回购决策并予以实施。":
        ("CNINFO_1214065177", "公司将根据董事会决议，在回购期限内根据市场情况择机作出回购决策并予[Page3]3以实施。", "preserve_original_page_marker"),
}


def checked_quote(item, documents):
    d = documents[item["source_id"]]
    compact = re.sub(r"\s+", "", item["quote"])
    repair = None
    try:
        span = source_span(d, re.escape(compact))
    except ValueError:
        if compact not in QUOTE_REPAIRS:
            raise ValueError("Unreviewed quotation mismatch")
        expected_id, replacement, kind = QUOTE_REPAIRS[compact]
        if d["id"] != expected_id:
            raise ValueError("Quotation repair issuer/source mismatch")
        span = source_span(d, re.escape(replacement))
        repair = {"source_id": d["id"], "original_model_quote": item["quote"], "replacement_source_span": span,
                  "reason": kind, "raw_response_unchanged": True}
    assert validate_span(d, span)
    return span, repair


def checked_inventory(result, expected_ids):
    sources = result["sources"]
    if isinstance(sources, dict):
        rows = []
        for key, value in sources.items():
            if value.get("source_id", key) != key:
                raise ValueError("Contradictory source map ID")
            rows.append({**value, "source_id": key})
        sources = rows
    if len(sources) != len(expected_ids) or {s["source_id"] for s in sources} != set(expected_ids):
        raise ValueError("Incomplete audited source set")
    if any(s["role"] not in {"target_scheme", "prior_scheme", "unrelated"} for s in sources):
        raise ValueError("Unclear source identity requires further review")
    return sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new immutable review version")
    base = ROOT / "modules/l0l4-memory/data/experiments"
    previous = base / "reserved-source-questions-v6-20261102"
    audit = base / "reserved-absence-audit-v2-20261102"
    bank = previous / "questions-source-candidates.jsonl"
    plan = json.loads((audit / "plan.json").read_text(encoding="utf-8"))
    assert plan["bank_sha256"] == hashlib.sha256(bank.read_bytes()).hexdigest()
    corpus = base / "diverse-announcements-20261031/corpus-split-v2.jsonl"
    assert plan["corpus_sha256"] == hashlib.sha256(corpus.read_bytes()).hexdigest()
    docs = {d["id"]: d for d in read_rows(corpus)}
    questions = deepcopy(read_rows(bank))
    responses = {r["question_id"]: r for r in read_rows(audit / "audit-results.jsonl")}
    repairs, reviews = [], []
    for q in questions:
        q["reference_version"] = VERSION
        if q["source_qualification"] != "pending":
            continue
        record = responses[q["id"]]
        result = json.loads(record["raw"])
        if result["decision"] != "insufficient" or result["first_purchase_date"] is not None or result["conflicts"]:
            raise ValueError("Substantive audit conflict cannot be promoted")
        sent = json.loads(record["user"])
        if {d["id"] for d in sent["documents"]} != set(q["source_ids"]) or sent["cutoff"] != q["as_of"] or sent["target_original_board_date"] != q["target_scheme"].rsplit("_", 1)[1]:
            raise ValueError("Audit prompt does not match reference scope")
        for d in sent["documents"]:
            assert d["text"] == docs[d["id"]]["text"]
        inventory = checked_inventory(result, q["source_ids"])
        evidence = []
        for item in result["evidence"]:
            if item["source_id"] not in q["source_ids"]:
                raise ValueError("Ineligible quotation")
            span, repair = checked_quote(item, docs)
            evidence.append({**span, "fields": []})
            if repair:
                repairs.append({"question_id": q["id"], **repair})
        reason = ("A full-context Qwen source audit, followed by assistant review of source scope, verbatim quotations and rationale, "
                  f"did not establish an actual first-purchase date for target {q['target_scheme']} in the supplied archive before {q['as_of']}. "
                  "Planned implementation and disclosure duties do not supply that date and do not prove no real-world purchase. "
                  "Transactions or dates belonging to an earlier scheme do not answer the target-scheme question.")
        q.update(source_qualification="source_checked", reference_origin="Qwen_full_context_audit_with_assistant_quote_and_reasoning_review",
                 reference_missing_reason=reason, reference_proofs=evidence,
                 absence_status="AI_silver_archive_scoped_date_not_established_not_independent_human_certification")
        reviews.append({"question_id": q["id"], "review_version": VERSION, "reference_tier": "source_anchored_silver",
                        "review_origin": q["reference_origin"], "human_reviewed": False, "independent_review": False,
                        "full_text_reviewer": record["response_model"], "assistant_full_text_read_all_sources": False,
                        "assistant_scope": "audit_output_source_scope_and_verbatim_repairs_not_claimed_full_text_manual_review",
                        "method_outputs_inspected": False, "reviewed_sources": [{"source_id": s, "text_sha256": docs[s]["text_sha256"]} for s in q["source_ids"]],
                        "source_roles_from_model_audit": inventory, "proofs": evidence,
                        "original_model_reason": result["reason"], "adopted_reason": reason,
                        "reasoning_change": "Restrict all claims to target-scheme date availability; remove implicit no-execution or reporting-compliance assumptions.",
                        "raw_response_sha256": hashlib.sha256(record["raw"].encode()).hexdigest()})
    assert len(questions) == 91 and len(reviews) == 22 and len(repairs) == 9
    for q in questions:
        build_public_task(q, docs)
        for p in [q["identity_proof"], *q["reference_proofs"]]:
            assert p["source_id"] in q["source_ids"] and validate_span(docs[p["source_id"]], p)
        assert not q["human_reviewed"] and not q["formal_evaluation_ready"]
    args.out.mkdir(parents=True)
    write_rows(args.out / "questions-source-candidates.jsonl", questions)
    write_rows(args.out / "semantic-review-ledger.jsonl", read_rows(previous / "semantic-review-ledger.jsonl") + reviews)
    write_rows(args.out / "audit-quotation-repairs.jsonl", repairs)
    for name in ["reference-errata.jsonl", "temporal-episodes.jsonl", "insufficiency-review-packets.jsonl", "correction-anchor-scope.jsonl", "source-anomalies.jsonl"]:
        (args.out / name).write_bytes((previous / name).read_bytes())
    summary = {"question_cards": 91, "source_checked_AI_silver": 91, "pending": 0,
               "new_negative_reviews": 22, "quotation_repairs": 9, "reasoning_restricted_to_date_availability": 22,
               "human_reviewed": 0, "independent_human_gold": 0, "formal_evaluation_ready": 0,
               "new_model_calls": 0, "method_comparison_calls": 0, "raw_outputs_modified": False,
               "family_counts": dict(Counter(q["benchmark_family"] for q in questions)),
               "limitations": ["22 negative references rely on Qwen full-text audits with assistant quotation/reasoning review, not independent manual source review", "No general memory gain has been established", "Three selected temporal episodes are not nine independent samples"],
               "previous_bank_sha256": hashlib.sha256(bank.read_bytes()).hexdigest()}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (args.out / "source-review-script.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
