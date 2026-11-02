"""Version three explicit correction questions and two scoped silver reviews.

Annotations come from AI-assisted reading of the frozen original texts, not
method predictions. No external models or evaluated-method changes are made.
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
from repurchase_evaluation import build_public_task, normalize_field
from repurchase_identity import source_span, validate_span
from reserved_source_templates import cutoff_for, identity

VERSION = "source-review-v4-20261102"


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def proof(document, fragment, fields=()):
    result = source_span(document, re.escape(fragment))
    if not result or not validate_span(document, result):
        raise ValueError("Review evidence absent from frozen source: " + document["id"])
    return {**result, "fields": list(fields)}


def review_record(question, docs, decisions, rationale, evidence):
    for p in evidence:
        if p["source_id"] not in question["source_ids"] or not validate_span(docs[p["source_id"]], p):
            raise ValueError("Review used an ineligible source")
    return {"question_id": question["id"], "review_version": VERSION,
            "review_origin": "AI_assisted_frozen_source_semantic_reading",
            "reference_tier": "source_anchored_silver", "human_reviewed": False,
            "independent_review": False, "method_outputs_inspected": False,
            "reviewed_sources": [{"source_id": sid, "text_sha256": docs[sid]["text_sha256"]}
                                 for sid in question["source_ids"]],
            "scope_decisions": decisions, "rationale": rationale, "proofs": evidence,
            "qualification": "source_checked_for_declared_archive_and_task_only"}


CORRECTIONS = [
    {"code": "301042", "original": "CNINFO_1219121270", "correction": "CNINFO_1219357430",
     "reference_notice": "2024-004", "answer": {"corrected_field": "other", "new_execution_stage_supported": False},
     "scope": "prohibited_repurchase_windows_wording",
     "fragment": "更正前：2.公司不得在下列期间回购公司股份：",
     "tail": "其他内容不变",
     "query": "Which registered field category is corrected by {correction}, linked to original scheme announcement {original}? Does THIS correction itself establish a new execution stage? Distinguish what this source establishes from all real-world events."},
    {"code": "600568", "original": "CNINFO_1219653255", "correction": "CNINFO_1219746867",
     "reference_notice": "2024-024", "answer": {"corrected_field": "projected_share_structure", "new_execution_stage_supported": False},
     "scope": "projected_share_structure_table_not_actual_purchases",
     "fragment": "原公告中“（八）预计回购后公司股权结构的变动情况”的数据有错误，现就上述事项做出更正如下：",
     "tail": "中其他内容不变",
     "query": "Which registered field category does {correction} correct in original scheme announcement {original}? Does THIS correction itself establish a new execution stage? Distinguish what this source establishes from all real-world events."},
    {"code": "688016", "original": "CNINFO_1221560423", "correction": "CNINFO_1221561533",
     "reference_notice": "2024-066", "answer": {"corrected_field": "other", "before": "自有资金和/或股票回购专项贷款", "after": "自有资金和/或自筹资金", "new_execution_stage_supported": False},
     "scope": "second_scheme_funding_source_wording_not_actual_purchases",
     "fragment": "更正前：重要内容提示：",
     "tail": "其他内容不变",
     "query": "For the second scheme identified by original announcement {original}, what funding-source wording does {correction} replace? Return corrected_field, before and after using the exact table-cell phrases (omit the leading 公司), and whether THIS correction establishes a new execution stage."},
]


def correction_question(spec, docs):
    original, correction = docs[spec["original"]], docs[spec["correction"]]
    if original["stock_code"] != spec["code"] or correction["stock_code"] != spec["code"]:
        raise ValueError("Issuer mismatch")
    root = identity(original)
    if not root:
        raise ValueError("Original scheme identity unresolved")
    # The issuer's own correction explicitly cites the original notice number.
    linked = proof(correction, spec["reference_notice"])
    original_notice = proof(original, spec["reference_notice"])
    evidence = [proof(correction, spec["fragment"], spec["answer"]),
                proof(correction, spec["tail"], ["new_execution_stage_supported"]), linked, original_notice]
    if "before" in spec["answer"]:
        evidence += [proof(correction, spec["answer"]["before"], ["before"]),
                     proof(correction, spec["answer"]["after"], ["after"])]
    cutoff = cutoff_for(correction)
    eligible = sorted([d for d in docs.values() if d["stock_code"] == spec["code"] and cutoff_for(d) <= cutoff],
                      key=lambda d: (d["disclosure_date"], d["id"]))
    question = {"id": "RSV_REVIEW_" + spec["code"] + "_correction", "stock_code": spec["code"],
                "company": original["company"], "split": "test_reserved", "split_version": 2,
                "benchmark_family": "update", "as_of": cutoff,
                "question": spec["query"].format(**spec), "target_scheme": spec["code"] + "_BOARD_" + root["date"],
                "requested_fields": list(spec["answer"]), "source_ids": [d["id"] for d in eligible],
                "reference_draft": spec["answer"], "reference_proofs": evidence,
                "identity_proof": root["proof"], "reference_answerability": "answerable",
                "reference_missing_reason": "", "reference_tier": "source_anchored_silver",
                "reference_origin": "AI_assisted_frozen_source_semantic_reading", "reference_version": VERSION,
                "source_qualification": "source_checked", "human_reviewed": False,
                "formal_evaluation_ready": False, "evidence_policy": "natural_archive_gap",
                "construction_scope": "supplemental_source_review_outside_original_180_opportunities",
                "source_semantics": spec["scope"]}
    for key, value in spec["answer"].items():
        normalize_field(key, value, value)
    build_public_task(question, docs)
    review = review_record(question, docs,
                          [{"source_id": original["id"], "role": "original_scheme_board_and_notice"},
                           {"source_id": correction["id"], "role": spec["scope"]}],
                          "The issuer explicitly links the correction to the original announcement. The full correction changes wording or projections, not a newly reported actual purchase event. Other archived documents do not redefine what THIS named correction establishes.",
                          [root["proof"], *evidence])
    return question, review


def negative_reviews(questions, docs):
    reviews = []
    for q in questions:
        if q["id"] == "RSV_SOURCE_603708_insufficient":
            decisions = [{"source_id": sid, "role": "earlier_2024_02_05_scheme"} for sid in q["source_ids"] if sid != "CNINFO_1221203223"]
            decisions.append({"source_id": "CNINFO_1221203223", "role": "target_2024_09_11_second_scheme_proposal"})
            rationale = "All four eligible texts were inspected. June/July progress and August completion concern the February 5 scheme. Its February 6 first purchase is not the second scheme's first purchase. The September second-scheme proposal describes future implementation, not a dated actual transaction. Within this supplied archive only, the target scheme's first-purchase date cannot be established."
            evidence = [q["identity_proof"], proof(docs["CNINFO_1220788844"], "2024年2月6日公司首次实施回购股份"),
                        proof(docs["CNINFO_1221203223"], "在回购期限内择机回购股份，包括回购的时间、价格和数量等")]
        elif q["id"] == "RSV_SOURCE_600231_insufficient":
            decisions = [{"source_id": "CNINFO_1219250183", "role": "shareholder_pledge_repo_transfer_termination_not_issuer_share_buyback"},
                         {"source_id": "CNINFO_1220456566", "role": "target_issuer_share_repurchase_proposal"}]
            rationale = "Both eligible texts were inspected. The March text concerns a shareholder's pledged-share default disposal/transfer and is unrelated to the issuer's June 25 share-buyback scheme. The June proposal gives future implementation, estimates and shareholder trades, but no target-scheme first actual purchase date. The abstention is archive-scoped, not a claim of no real-world execution."
            evidence = [q["identity_proof"], proof(docs["CNINFO_1219250183"], "宏运资本因未按照协议约定完成股票质押回购交易"),
                        proof(docs["CNINFO_1220456566"], "在回购期限内择机回购股份，包括回购的时间、价格和数量等")]
        else:
            continue
        q["source_qualification"] = "source_checked"
        q["reference_missing_reason"] = rationale
        q["absence_status"] = "AI_assisted_full_eligible_text_review_target_scheme_scoped"
        reviews.append(review_record(q, docs, decisions, rationale, evidence))
    return reviews


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new version; prior annotations are immutable")
    base = ROOT / "modules/l0l4-memory/data/experiments"
    previous = base / "reserved-source-questions-v3-20261101"
    original_bank = previous / "questions-source-candidates.jsonl"
    corpus = base / "diverse-announcements-20261031/corpus-split-v2.jsonl"
    docs = {d["id"]: d for d in read_rows(corpus) if d["split_candidate"] == "test_reserved"}
    questions = deepcopy(read_rows(original_bank))
    for q in questions:
        q["reference_version"] = VERSION
    reviews = negative_reviews(questions, docs)
    for spec in CORRECTIONS:
        question, review = correction_question(spec, docs)
        questions.append(question)
        reviews.append(review)
    for q in questions:
        build_public_task(q, docs)
        for p in [q["identity_proof"], *q["reference_proofs"]]:
            assert p["source_id"] in q["source_ids"] and validate_span(docs[p["source_id"]], p)
        assert q["human_reviewed"] is False and q["formal_evaluation_ready"] is False
    assert len(questions) == len({q["id"] for q in questions}) == 82 and len(reviews) == 5
    args.out.mkdir(parents=True)
    write_rows(args.out / "questions-source-candidates.jsonl", questions)
    write_rows(args.out / "semantic-review-ledger.jsonl", reviews)
    for name in ["reference-errata.jsonl", "insufficiency-review-packets.jsonl", "correction-anchor-scope.jsonl", "source-anomalies.jsonl"]:
        (args.out / name).write_bytes((previous / name).read_bytes())
    summary = {"version": VERSION, "candidate_questions": len(questions), "original_opportunities": 180,
               "original_candidates": 79, "supplemental_correction_questions": 3,
               "original_unavailable_opportunities": 101,
               "family_counts": dict(Counter(q["benchmark_family"] for q in questions)),
               "source_checked_silver_questions": sum(q["source_qualification"] == "source_checked" for q in questions),
               "source_pending_questions": sum(q["source_qualification"] == "pending" for q in questions),
               "negative_source_checked": 2, "negative_pending": 23, "human_reviewed": 0,
               "formal_evaluation_ready": 0, "model_calls": 0, "method_outputs_modified": False,
               "limitations": ["AI assisted single-review silver, not independent human gold", "No new compared-method outputs", "Update questions are named-source comprehension, not yet a temporal-memory gain test", "Evidence-trace family still has only one question"],
               "previous_bank_sha256": hashlib.sha256(original_bank.read_bytes()).hexdigest(),
               "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest()}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (args.out / "source-review-script.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
