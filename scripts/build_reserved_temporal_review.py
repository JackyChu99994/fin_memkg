"""Record positive-reference reviews and source-backed temporal diagnostics.

This is offline annotation work. Selected transitions are diagnostic examples,
not representative sampling or independent human gold. No methods are tuned.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from repurchase_evaluation import build_public_task
from repurchase_identity import validate_span
from reserved_source_templates import cutoff_for, identity
from scripts.extend_reserved_source_review import proof, read_rows, write_rows

VERSION = "source-temporal-v5-20261102"
# Explicitly inspected positive clauses and their original board identities.
HISTORICAL = {
    "300272": ("2022-06-16", "2022-05-14"), "600568": ("2024-04-23", "2024-04-17"),
    "301042": ("2024-03-07", "2024-02-07"), "300200": ("2024-02-02", "2024-01-30"),
    "605080": ("2023-09-25", "2023-09-12"), "600823": ("2023-07-10", "2023-06-04"),
    "002885": ("2024-02-29", "2024-02-18"), "000883": ("2022-10-10", "2022-04-26"),
    "300982": ("2024-01-03", "2023-12-10"), "002129": ("2024-01-30", "2023-10-25"),
    "301063": ("2024-12-25", "2024-10-09"), "600867": ("2024-07-11", "2024-07-08"),
    "688392": ("2024-08-27", "2024-07-18"), "605377": ("2022-08-01", "2022-07-18"),
    "600231": ("2024-07-12", "2024-06-25"), "688028": ("2023-06-05", "2023-05-11"),
    "301300": ("2024-02-29", "2024-02-28"),
}
EPISODES = [
    {"code": "301042", "final_source": "CNINFO_1219995482", "first_shares": 10000,
     "final_shares": 2089634, "completion_clause": "本次回购方案已实施完毕"},
    {"code": "301300", "final_source": "CNINFO_1220159127", "first_shares": 86255,
     "final_shares": 653455, "completion_clause": "公司本次回购股份方案已实施完毕"},
    {"code": "600231", "final_source": "CNINFO_1222128510", "first_shares": 3132800,
     "final_shares": 65052049, "completion_clause": "公司已完成本次股份回购"},
]


def scoped_review(q, docs, evidence, rationale, scope):
    inspected = sorted({p["source_id"] for p in evidence})
    for p in evidence:
        if p["source_id"] not in q["source_ids"] or not validate_span(docs[p["source_id"]], p):
            raise ValueError("Review evidence is invalid or ineligible")
    return {"question_id": q["id"], "review_version": VERSION,
            "review_origin": "AI_assisted_source_semantic_reading", "reference_tier": "source_anchored_silver",
            "human_reviewed": False, "independent_review": False, "method_outputs_inspected": False,
            "inspection_scope": scope,
            "reviewed_sources": [{"source_id": sid, "text_sha256": docs[sid]["text_sha256"]} for sid in inspected],
            "eligible_source_ids": q["source_ids"], "rationale": rationale, "proofs": evidence}


def review_existing(questions, docs):
    reviews, errata = [], []
    for q in questions:
        if q["id"] == "RSV_SOURCE_600823_historical":
            old_scheme, old_proof = q["target_scheme"], q["identity_proof"]
            d = docs[old_proof["source_id"]]
            corrected = proof(d, "分别于2023年6月4日与2023年6月27日召开了第九届董事会第十七次会议与2022年年度股东大会，审议通过了《关于以集中竞价交易方式回购股份方案的议案》")
            q["target_scheme"] = "600823_BOARD_2023-06-04"
            q["identity_proof"] = corrected
            errata.append({"question_id": q["id"], "kind": "scheme_identity_erratum",
                           "old_scheme": old_scheme, "new_scheme": q["target_scheme"],
                           "old_proofs": [old_proof], "new_proofs": [corrected],
                           "reason": "Respectively pairs June 4 with the board and June 27 with shareholders; do not assign the latter to the board.",
                           "reference_answer_unchanged": True, "method_outputs_modified": False})
        if q["benchmark_family"] == "historical":
            expected_day, board = HISTORICAL[q["stock_code"]]
            if q["reference_draft"] != {"first_purchase_date": expected_day} or q["target_scheme"] != q["stock_code"] + "_BOARD_" + board:
                raise ValueError("Inspected historical annotation no longer matches this bank")
            q["source_qualification"] = "source_checked"
            evidence = [q["identity_proof"], *q["reference_proofs"]]
            q["reference_origin"] = "AI_assisted_inspection_of_explicit_transaction_and_scheme_clauses"
            reviews.append(scoped_review(q, docs, evidence,
                "The named issuer's actual first-purchase clause supplies a transaction date and positive share quantity. The original board identity is checked separately; disclosure dates, statistics cutoffs, later schemes and shareholder approval dates are not substituted. This positive, named-source task does not require certifying absence across all other eligible texts.",
                "issuer_header_original_board_and_explicit_positive_transaction_clauses"))
        if q["id"] == "RSV_SOURCE_300200_insufficient":
            assert q["source_ids"] == ["CNINFO_1219044801"]
            q["source_qualification"] = "source_checked"
            q["absence_status"] = "AI_assisted_full_eligible_text_review_target_scheme_scoped"
            q["reference_missing_reason"] = "The sole supplied January 30 scheme proposal was read in full. It gives planned amounts, quantities, implementation windows and past insider trades, but no actual first purchase date for this scheme. This archive-scoped absence neither proves no real-world purchases nor permits using the later February first-purchase announcement."
            evidence = [q["identity_proof"], proof(docs[q["source_ids"][0]], "根据公司和市场的具体情况择机回购股份，确定具体的回购时间、价格和数量等")]
            reviews.append(scoped_review(q, docs, evidence, q["reference_missing_reason"], "full_text_of_all_eligible_sources"))
    assert len(reviews) == 18 and len(errata) == 1
    return reviews, errata


def temporal_tasks(spec, historical, docs):
    first = docs[historical["reference_proofs"][0]["source_id"]]
    final = docs[spec["final_source"]]
    first_root, final_root = identity(first), identity(final)
    if not first_root or not final_root or first_root["date"] != final_root["date"] or cutoff_for(first) >= cutoff_for(final):
        raise ValueError("Temporal pair must have the same original board and ordered disclosures")
    if any(d["stock_code"] != spec["code"] for d in (first, final)):
        raise ValueError("Temporal pair issuer mismatch")
    first_quantity = proof(first, format(spec["first_shares"], ","), ["first_purchase_shares"])
    final_quantity = proof(final, format(spec["final_shares"], ","), ["shares"])
    completed = proof(final, spec["completion_clause"], ["repurchase_stage"])
    if spec["final_shares"] <= spec["first_shares"]:
        raise ValueError("A selected increase diagnostic must have a positive difference")
    episode_id = "RSV_EPISODE_" + spec["code"]
    questions, reviews = [], []
    for idx, d in enumerate((first, final), 1):
        cutoff = cutoff_for(d)
        eligible = sorted([s for s in docs.values() if s["stock_code"] == spec["code"] and cutoff_for(s) <= cutoff], key=lambda s: (s["disclosure_date"], s["id"]))
        answer = {"repurchase_stage": "STARTED" if idx == 1 else "COMPLETED",
                  "first_purchase_date": historical["reference_draft"]["first_purchase_date"],
                  "first_purchase_shares": spec["first_shares"]}
        fields = ["first_purchase_date", "first_purchase_shares"] + (["repurchase_stage"] if idx == 1 else [])
        evidence = [{**historical["reference_proofs"][0], "fields": fields}, first_root["proof"]]
        if idx == 2:
            evidence += [completed, final_root["proof"]]
        q = {"id": episode_id + "_T" + str(idx), "stock_code": spec["code"], "company": first["company"],
             "split": "test_reserved", "split_version": 2, "benchmark_family": "update", "as_of": cutoff,
             "question": f"For the original scheme described in {first['id']}, using only sources available by the cutoff, return the latest explicitly disclosed execution stage and preserve the first actual purchase date and first-purchase share count. Later information is unavailable at earlier cutoffs; account balances and planned quantities are different facts.",
             "target_scheme": historical["target_scheme"], "requested_fields": list(answer),
             "source_ids": [s["id"] for s in eligible], "reference_draft": answer, "reference_proofs": evidence,
             "identity_proof": first_root["proof"], "reference_answerability": "answerable", "reference_missing_reason": "",
             "reference_tier": "source_anchored_silver", "reference_origin": "AI_assisted_source_semantic_reading",
             "reference_version": VERSION, "source_qualification": "source_checked", "human_reviewed": False,
             "formal_evaluation_ready": False, "evidence_policy": "natural_archive_gap", "episode_id": episode_id,
             "construction_scope": "selected_transition_diagnostic_not_representative_sample"}
        build_public_task(q, docs)
        questions.append(q)
        reviews.append(scoped_review(q, docs, evidence,
            "Explicit first purchases establish the early started state. The later same-board completion disclosure establishes completed; first-purchase date and quantity remain historical facts. Both endpoint texts were read in full. Intervening eligible documents remain in the common input universe; selected stage transitions do not establish a general accuracy gain.",
            "full_endpoint_texts_positive_scheme_transaction_and_completion_evidence"))
    last = questions[-1]
    delta = {**deepcopy(last), "id": episode_id + "_DELTA", "benchmark_family": "evidence_trace",
             "question": f"For the same original scheme, subtract the actual first-purchase share count in {first['id']} from the final cumulative actual repurchase count in {final['id']}. Return the increase in repurchased shares, not the remaining repurchase-account balance or a planned amount.",
             "requested_fields": ["shares"], "reference_draft": {"shares": spec["final_shares"] - spec["first_shares"]},
             "reference_proofs": [first_quantity, final_quantity, first_root["proof"], final_root["proof"]],
             "derivation": {"operation": "integer_difference", "final_source": final["id"], "final_shares": spec["final_shares"],
                            "first_source": first["id"], "first_shares": spec["first_shares"],
                            "necessity_status": "two_endpoint_full_texts_inspected_each_operand_not_repeated_by_other_endpoint"}}
    delta["reference_proofs"][0]["fields"] = ["shares"]
    questions.append(delta)
    reviews.append(scoped_review(delta, docs, delta["reference_proofs"],
        "Both endpoint texts were read. The first-purchase quantity is not repeated in the final endpoint and the final total cannot occur in the earlier endpoint. Other eligible sources may repeat an operand, so necessity is established for this named endpoint pair, not for exactly two unique documents in the whole archive. Difference is an integer share count.",
        "full_named_endpoint_texts_and_integer_derivation"))
    episode = {"id": episode_id, "stock_code": spec["code"], "target_scheme": historical["target_scheme"],
               "snapshot_question_ids": [q["id"] for q in questions[:2]], "join_question_id": delta["id"],
               "first_source": first["id"], "final_source": final["id"],
               "stable_fields": ["first_purchase_date", "first_purchase_shares"], "updated_field": "repurchase_stage",
               "independent_sampling_unit": "scheme_episode_not_question", "stratum": "selected_started_to_completed",
               "statistical_efficacy_evidence": False}
    return questions, reviews, episode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new immutable annotation version")
    base = ROOT / "modules/l0l4-memory/data/experiments"
    previous = base / "reserved-source-questions-v4-20261102"
    bank = previous / "questions-source-candidates.jsonl"
    corpus = base / "diverse-announcements-20261031/corpus-split-v2.jsonl"
    docs = {d["id"]: d for d in read_rows(corpus) if d["split_candidate"] == "test_reserved"}
    questions = deepcopy(read_rows(bank))
    for q in questions:
        q["reference_version"] = VERSION
    reviews, errata = review_existing(questions, docs)
    episodes = []
    for spec in EPISODES:
        historical = next(q for q in questions if q["id"] == "RSV_SOURCE_" + spec["code"] + "_historical")
        new_questions, new_reviews, episode = temporal_tasks(spec, historical, docs)
        questions.extend(new_questions)
        reviews.extend(new_reviews)
        episodes.append(episode)
    assert len(questions) == len({q["id"] for q in questions}) == 91
    for q in questions:
        build_public_task(q, docs)
        for p in [q["identity_proof"], *q["reference_proofs"]]:
            assert p["source_id"] in q["source_ids"] and validate_span(docs[p["source_id"]], p)
        assert not q["human_reviewed"] and not q["formal_evaluation_ready"]
    args.out.mkdir(parents=True)
    write_rows(args.out / "questions-source-candidates.jsonl", questions)
    write_rows(args.out / "semantic-review-ledger.jsonl", read_rows(previous / "semantic-review-ledger.jsonl") + reviews)
    write_rows(args.out / "reference-errata.jsonl", read_rows(previous / "reference-errata.jsonl") + errata)
    write_rows(args.out / "temporal-episodes.jsonl", episodes)
    for name in ["insufficiency-review-packets.jsonl", "correction-anchor-scope.jsonl", "source-anomalies.jsonl"]:
        (args.out / name).write_bytes((previous / name).read_bytes())
    summary = {"version": VERSION, "candidate_questions": len(questions),
               "source_checked_silver_questions": sum(q["source_qualification"] == "source_checked" for q in questions),
               "source_pending_questions": sum(q["source_qualification"] == "pending" for q in questions),
               "historical_source_checked": 17, "negative_source_checked": 3, "negative_pending": 22,
               "temporal_episodes": 3, "temporal_questions": 9, "new_identity_errata": 1,
               "family_counts": dict(Counter(q["benchmark_family"] for q in questions)),
               "original_opportunities": 180, "original_unavailable_opportunities": 101,
               "human_reviewed": 0, "formal_evaluation_ready": 0, "model_calls": 0,
               "method_outputs_modified": False, "method_efficacy_established": False,
               "previous_bank_sha256": hashlib.sha256(bank.read_bytes()).hexdigest(),
               "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest()}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (args.out / "source-review-script.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
