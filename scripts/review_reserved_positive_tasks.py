"""Apply an inspected inventory of positive-source reviews, without method calls.

This script records annotation decisions; it is not a general semantic classifier.
It preserves previous versions and never promotes uninspected question families.
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
from repurchase_evaluation import build_public_task
from repurchase_identity import compact_with_offsets, validate_span
from reserved_source_templates import identity
from scripts.build_reserved_temporal_review import scoped_review
from scripts.extend_reserved_source_review import proof, read_rows, write_rows

VERSION = "source-positive-v6-20261102"
STAGE_CODES = set("300454 688737 603629 002759 002625 688257 301047 002947 688560 000785 002565 688016 688282 002970 603777 601222 002611 300891 300014 002550 688349 600884 002812".split())
SEPARATION = {
    "300454": ("CNINFO_1216022859", "公司本次回购股份方案已实施完毕"),
    "002625": ("CNINFO_1221853607", "公司上述股份回购方案已实施完成"),
    "301047": ("CNINFO_1220558979", "公司本次回购已实施完毕"),
    "688560": ("CNINFO_1218594588", "公司完成股份回购"),
    "002565": ("CNINFO_1223527901", "公司本次回购股份方案已实施完成"),
    "688282": ("CNINFO_1220881348", "公司完成本次股份回购"),
    "002970": ("CNINFO_1216357724", "公司决定提前终止回购公司股份事项"),
    "300014": ("CNINFO_1218013171", "公司上述回购股份方案已实施完毕"),
    "002550": ("CNINFO_1216469958", "本次回购方案实施完毕"),
    "002812": ("CNINFO_1216781843", "公司本次回购方案已实施完毕"),
}
IDENTITIES = {
    "301047": ("2024-02-02", "分别于2024年2月2日、2024年2月19日召开第二届董事会第八次会议和2024年第一次临时股东大会，审议通过了《关于回购公司股份方案的议案》", "The later date belongs to shareholders, not the original board."),
    "000785": ("2024-11-20", "于2024年11月20日、2024年12月6日分别召开公司第十一届董事会第十四次会议、第十届监事会第十四次会议以及2024年第四次临时股东大会，审议通过了《关于公司以集中竞价交易方式回购部分社会公众股份方案（第四期）的议案》", "November 20 is the board date; December 6 is the shareholder meeting date."),
    "002611": ("2021-08-31", "2021年8月31日召开的第四届董事会第十次（临时）会议和2021年9月22日召开的2021年第二次临时股东大会审议通过了《关于回购部分社会公众股份方案的议案》", "August 31 belongs to the board; September 22 belongs to shareholders."),
    "002812": ("2024-02-02", "分别于2024年2月2日、2024年2月18日召开第五届董事会第十九次会议、第五届董事会第二十次会议，审议通过了《关于回购公司股份的议案》和《关于变更回购股份用途为注销的议案》", "February 2 establishes the original scheme; February 18 changes its purpose, rather than starting a new scheme."),
}


def issuer_proof(document, code):
    text, _ = compact_with_offsets(document["text"])
    match = re.search(r"(?:证券|股票)代码[：:]" + re.escape(code), text[:500])
    if not match or document["stock_code"] != code:
        raise ValueError("Inspected source issuer header mismatch")
    return proof(document, match.group())


def identity_erratum(question, document, board, fragment, reason):
    if document["id"] not in question["source_ids"] or document["disclosure_date"] >= question["as_of"][:10]:
        raise ValueError("Identity correction source is not eligible")
    year, month, day = map(int, board.split("-"))
    compact = re.sub(r"\s+", "", fragment)
    if f"{year}年{month}月{day}日" not in compact or "董事会" not in compact:
        raise ValueError("Explicit original-board date required in correction evidence")
    evidence = proof(document, fragment)
    issuer_proof(document, question["stock_code"])
    old = {"target_scheme": question["target_scheme"], "identity_proof": deepcopy(question["identity_proof"]),
           "question": question["question"], "reference_proofs": deepcopy(question["reference_proofs"])}
    question["target_scheme"] = question["stock_code"] + "_BOARD_" + board
    question["identity_proof"] = evidence
    return {"question_id": question["id"], "kind": "scheme_identity_erratum", "old_scheme": old["target_scheme"],
            "new_scheme": question["target_scheme"], "old_question": old["question"], "old_proofs": [old["identity_proof"], *old["reference_proofs"]],
            "new_proofs": [evidence], "reason": reason, "reference_answer_unchanged": True,
            "method_outputs_modified": False}


def record_review(q, docs, evidence, rationale, scope):
    result = scoped_review(q, docs, evidence, rationale, scope)
    result["review_version"] = VERSION
    return result


def apply_reviews(questions, docs):
    by_id = {q["id"]: q for q in questions}
    errata, reviews = [], []
    for code, (board, fragment, reason) in IDENTITIES.items():
        q = by_id["RSV_SOURCE_" + code + "_stage"]
        errata.append(identity_erratum(q, docs[q["identity_proof"]["source_id"]], board, fragment, reason))

    # The new stability scheme cites termination of an older, different scheme.
    q = by_id["RSV_SOURCE_301063_update"]
    d = docs["CNINFO_1221354626"]
    row = identity_erratum(q, d, "2024-02-07", "2024年2月7日召开了第三届董事会第十九次会议，审议通过了《关于回购公司股份方案的议案》",
                           "The February scheme is terminated. A same-day October stability-scheme approval is a different scheme and cannot be its original identity.")
    q["question"] = "What termination board decision date does CNINFO_1221354626 disclose for the original scheme it terminates? Do not assign this termination to the different stability scheme approved on the same board-meeting day."
    q["reference_proofs"] = [proof(d, "2024年10月9日召开了第三届董事会第二十四次会议，审议通过了《关于终止回购公司股份方案的议案》", q["reference_draft"])]
    row.update(new_question=q["question"], public_question_retargeted=True, new_proofs=[q["identity_proof"], *q["reference_proofs"]])
    errata.append(row)

    for q in questions:
        if q["source_qualification"] != "pending":
            continue
        family, code = q["benchmark_family"], q["stock_code"]
        evidence = [q["identity_proof"], *q["reference_proofs"]]
        rationale, scope = None, "issuer_and_explicit_positive_task_clauses"
        if family == "stage" and code in STAGE_CODES:
            evidence.append(issuer_proof(docs[q["identity_proof"]["source_id"]], code))
            rationale = "The named issuer's original board and actual execution evidence were inspected. Explicit completion is distinguished from a forecast or regulatory obligation. Under the predeclared coarse three-label task, actual purchases in a termination report remain STARTED execution history; this does not mean the scheme remains active. No budget, meeting amendment or unrelated scheme is substituted."
            q["stage_label_scope"] = "coarse_execution_history_not_complete_active_or_terminated_state"
        elif family == "multi_scheme" and code in SEPARATION:
            sid, clause = SEPARATION[code]
            d = docs[sid]
            if sid not in q["source_ids"]:
                raise ValueError("Separation evidence absent from supplied source universe")
            dates = q["reference_draft"]["source_approval_dates"]
            old_board, new_board = min(dates.values()), max(dates.values())
            if not d["disclosure_date"] < new_board:
                raise ValueError("Old scheme must end before the new scheme board decision")
            old_root = by_id["RSV_SOURCE_301047_stage"]["identity_proof"] if code == "301047" else identity(d)["proof"]
            root_date = "2024-02-02" if code == "301047" else identity(d)["date"]
            if root_date != old_board:
                raise ValueError("Old completion or termination belongs to a different scheme")
            supplementary = [proof(d, clause, ["same_scheme"]), old_root]
            q["reference_proofs"].extend(supplementary)
            evidence = [q["identity_proof"], *q["reference_proofs"]]
            for source in dates:
                evidence.append(issuer_proof(docs[source], code))
            q["scheme_separation_basis"] = {"ended_old_scheme_source": sid, "old_board": old_board, "new_board": new_board,
                                             "not_only_different_dates": True}
            rationale = "Two issuer scheme reports have independently checked original board dates. An eligible old-scheme completion or termination source binds to the older original board and predates the later fresh scheme approval. Thus the distinction is supported by scheme closure and fresh authorization, not merely two different dates or a purpose/budget amendment."
        elif family == "update" and code in {"300829", "002129", "301063"}:
            evidence.append(issuer_proof(docs[q["identity_proof"]["source_id"]], code))
            rationale = "The issuer's original scheme identity and explicit termination board decision were inspected separately. For 300829 the source also explicitly states no shareholder submission is required. For 301063 the terminated February scheme is separated from the new October stability scheme. No new execution stage is inferred from board approval alone."
        elif q["id"] == "RSV_SOURCE_002812_evidence_trace":
            values = [1469800, 7238804]
            assert q["reference_draft"] == {"shares": sum(values)}
            for p, expected in zip(q["reference_proofs"], values):
                assert format(expected, ",") in re.sub(r"\s+", "", p["quote"])
                d = docs[p["source_id"]]
                evidence += [identity(d)["proof"], issuer_proof(d, code), proof(d, "公司本次回购方案已实施完毕")]
            q["reference_proofs"] = evidence
            rationale = "The two named issuer outcome sources explicitly report 1,469,800 and 7,238,804 actual repurchased shares for different original boards. Both completion clauses and scheme identities were inspected. Their sum is 8,708,604 shares; neither a planned budget nor remaining account balance is used. This is positive-operand review, not general semantic-necessity certification."
        if rationale is None:
            continue
        q["source_qualification"] = "source_checked"
        q["reference_origin"] = "AI_assisted_source_semantic_reading"
        reviews.append(record_review(q, docs, evidence, rationale, scope))
    if len(reviews) != 37 or len(errata) != 5:
        raise ValueError("Inspected review inventory does not match frozen input")
    return reviews, errata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new review version; earlier references must remain intact")
    base = ROOT / "modules/l0l4-memory/data/experiments"
    previous = base / "reserved-source-questions-v5-20261102"
    bank = previous / "questions-source-candidates.jsonl"
    corpus = base / "diverse-announcements-20261031/corpus-split-v2.jsonl"
    docs = {d["id"]: d for d in read_rows(corpus) if d["split_candidate"] == "test_reserved"}
    questions = deepcopy(read_rows(bank))
    reviews, errata = apply_reviews(questions, docs)
    for q in questions:
        q["reference_version"] = VERSION
        build_public_task(q, docs)
        for p in [q["identity_proof"], *q["reference_proofs"]]:
            assert p["source_id"] in q["source_ids"] and validate_span(docs[p["source_id"]], p)
        assert not q["human_reviewed"] and not q["formal_evaluation_ready"]
    args.out.mkdir(parents=True)
    write_rows(args.out / "questions-source-candidates.jsonl", questions)
    write_rows(args.out / "semantic-review-ledger.jsonl", read_rows(previous / "semantic-review-ledger.jsonl") + reviews)
    write_rows(args.out / "reference-errata.jsonl", read_rows(previous / "reference-errata.jsonl") + errata)
    write_rows(args.out / "pending-question-inventory.jsonl", [{"question_id": q["id"], "company": q["company"],
        "source_ids": q["source_ids"], "target_scheme": q["target_scheme"], "as_of": q["as_of"],
        "status": "full_eligible_source_semantic_review_needed"} for q in questions if q["source_qualification"] == "pending"])
    for name in ["temporal-episodes.jsonl", "insufficiency-review-packets.jsonl", "correction-anchor-scope.jsonl", "source-anomalies.jsonl"]:
        (args.out / name).write_bytes((previous / name).read_bytes())
    summary = {"version": VERSION, "question_cards": len(questions),
               "source_checked_silver": sum(q["source_qualification"] == "source_checked" for q in questions),
               "pending": sum(q["source_qualification"] == "pending" for q in questions),
               "new_reviewed": len(reviews), "new_identity_errata": len(errata),
               "pending_families": dict(Counter(q["benchmark_family"] for q in questions if q["source_qualification"] == "pending")),
               "source_checked_families": dict(Counter(q["benchmark_family"] for q in questions if q["source_qualification"] == "source_checked")),
               "human_reviewed": 0, "formal_evaluation_ready": 0, "model_calls": 0, "method_outputs_modified": False,
               "original_opportunities": 180, "original_unavailable_opportunities": 101,
               "previous_bank_sha256": hashlib.sha256(bank.read_bytes()).hexdigest(),
               "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest()}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (args.out / "source-review-script.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
