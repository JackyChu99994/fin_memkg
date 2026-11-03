"""Audit 20 development anchors and draft source-bound tasks without inference."""
import argparse
from collections import Counter
from datetime import date, timedelta
import hashlib
import html
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from repurchase_identity import anchor_gate, approval_candidates, own_number, source_span, validate_span


# References below are assistant-authored development drafts, not human gold.
# Each material answer requires archived-source spans and an eligible cutoff.
CASES = [
    ("600703", "completion", "2023-12-08", "1219054168",
     "For the scheme approved on 2023-12-08, what completion date and total shares were disclosed?",
     {"completion_date": "2024-01-31", "shares": 76654015},
     [("1219054168", r"2023年12月8日.{0,90}审议通过"), ("1219054168", r"2024年1月31日.{0,80}76,654,015股")]),
    ("300406", "completion", "2023-07-21", "1220702464",
     "For the 2023 scheme, what completion date and share total were disclosed? Exclude the 2022 scheme.",
     {"completion_date": "2024-07-19", "shares": 4825100},
     [("1220702464", r"2023年7月21日.{0,100}审议通过"), ("1220702464", r"截至2024年7月19日.{0,180}4,825,100股")]),
    ("300482", "completion", "2023-07-05", "1217282442",
     "For the scheme approved on 2023-07-05, give its reported completion date and share total.",
     {"completion_date": "2023-07-11", "shares": 1121900},
     [("1217282442", r"2023年7月5日.{0,100}审议通过"), ("1217282442", r"截至2023年7月11日.{0,260}1,121,900股")]),
    ("002828", "completion", "2023-04-27", "1216873799",
     "What completion date and share total are disclosed for this scheme, distinct from a price-cap amendment?",
     {"completion_date": "2024-01-10", "shares": 3828600, "shareholder_approval_date": "2023-05-19"},
     [("1216873799", r"2023年4月27日.{0,100}审议通过"), ("1218867659", r"2023年5月19日.{0,100}审议通过"),
      ("1218867659", r"截至2024年1月10日.{0,180}3,828,600股")]),
    ("300381", "completion", "2022-05-17", "1216786477",
     "For the 2022-approved scheme, state the disclosed completion date and cumulative shares.",
     {"completion_date": "2023-05-09", "shares": 10887600},
     [("1216786477", r"2022年5月17日.{0,100}审议通过"), ("1216786477", r"截至2023年5月9日.{0,280}10,887,600股")]),
    ("003010", "multiple_scheme", "2024-02-05", "1219096306",
     "Are the January and February 2024 reports one scheme? Attribute each report to its approval date.",
     {"same_scheme": False, "source_approval_dates": {"CNINFO_1219009876": "2024-01-26", "CNINFO_1219096303": "2024-02-05"}},
     [("1219096306", r"2024年2月5日.{0,100}审议通过"), ("1219009876", r"2024年1月26日.{0,100}审议通过"),
      ("1219096303", r"2024年2月5日.{0,100}审议通过")]),
    ("300919", "correction", "2023-08-24", "1218790673",
     "Which cumulative amount was corrected, from what to what, and did the quoted share count change?",
     {"field": "cumulative_amount_yuan", "before": "187366518.70", "after": "180996040.40", "share_count_changed": False, "shares": 3393300},
     [("1218790673", r"2023年8月24日.{0,100}审议通过"), ("1218836328", r"更正前.{0,350}187,366,518.70元"),
      ("1218836328", r"更正后.{0,350}180,996,040.40元")]),
    ("603688", "correction", "2023-12-14", "1218620097",
     "Does this correction amend projected share structure or report a new repurchase execution stage?",
     {"corrected_field": "projected_share_structure", "new_execution_stage_supported": False, "intraday_order_inferred": False},
     [("1218620097", r"2023年12月14日.{0,100}审议通过"), ("1218630593", r"预计回购后公司股权结构的变动情况"),
      ("1218630593", r"除以上更正内容外，原公告其他内容不变")]),
    ("688211", "correction", "2023-11-16", "1219997371",
     "What unit error is corrected in cumulative repurchased shares? Preserve the original and corrected wording.",
     {"before": "1,182,929万股", "after": "1,182,929股", "corrected_shares": 1182929, "field": "share_count_unit"},
     [("1219997371", r"2023年11月16日.{0,100}审议通过"), ("1220010106", r"累计已回购股数1,182,929万股"),
      ("1220010106", r"累计已回购股数1,182,929股")]),
    ("688249", "correction", "2023-12-22", "1218709128",
     "Which factual dimension is corrected: an executive's trading disclosure or company repurchase execution?",
     {"corrected_field": "executive_trading_disclosure", "new_execution_stage_supported": False},
     [("1218709128", r"2023年12月22日.{0,100}审议通过"),
      ("1218751461", r"方华女士在担任公司高级管理人员期间于2023年8月25日买入公司股票3,000股"),
      ("1218751461", r"除上述更正内容调整外，公告的其他内容保持不变")]),
    ("603337", "scheme_amendment", "2023-02-07", "1217292149",
     "Did the July revision create a new scheme or amend its funding range? Give the before/after range in yuan.",
     {"new_scheme": False, "amendment_date": "2023-07-12", "before_min": 60000000, "before_max": 120000000,
      "after_min": 120000000, "after_max": 240000000},
     [("1217292149", r"2023年2月7日.{0,100}审议通过"), ("1217292149", r"2023年7月12日.{0,320}24,000万元")]),
    ("002384", "termination_gate", "2022-04-25", "1216316816",
     "Does this source establish an unconditional effective termination? Separate board approval, shareholder gate and past purchases.",
     {"board_approved_termination": True, "shareholder_approval_still_required": True, "past_purchases_disclosed": True,
      "effective_termination_established_by_this_source": False},
     [("1216316816", r"2022年4月25日.{0,100}审议通过"),
      ("1216316816", r"2023年4月3日.{0,100}审议通过.{0,40}终止回购"),
      ("1216316816", r"本次终止回购公司股份事项需提交公司股东大会审议"), ("1216316816", r"累计回购公司股份304.87万股")]),
    ("301322", "source_and_approval_gate", "2024-09-04", "1221138414",
     "Which issuer source supports the second scheme, and was shareholder approval still pending at this disclosure?",
     {"primary_issuer_source": "CNINFO_1221138414", "opinion_is_auxiliary": True, "shareholder_approval_pending": True},
     [("1221138414", r"2024年9月4日.{0,130}审议通过"), ("1221138414", r"尚需提交.{0,35}股东大会审议"),
      ("1221138410", r"兴业证券股份有限公司.{0,100}核查意见")]),
    ("688023", "multiple_scheme", "2023-07-28", "1217417498",
     "Attribute the January and second-phase July reports to separate scheme approval dates.",
     {"same_scheme": False, "source_approval_dates": {"CNINFO_1215567109": "2023-01-10", "CNINFO_1217417498": "2023-07-28"}},
     [("1215567109", r"2023年1月10日.{0,100}审议通过"), ("1217417498", r"2023年7月28日.{0,100}审议通过")]),
    ("688455", "multiple_scheme", "2024-06-18", "1220560612",
     "Distinguish the March scheme from the June second scheme and identify the latter's first reported purchase date.",
     {"first_scheme_board_date": "2024-03-04", "second_scheme_board_date": "2024-06-18", "second_first_purchase_date": "2024-07-08"},
     [("1219280503", r"2024年3月4日.{0,100}审议通过"), ("1220560612", r"2024年6月18日.{0,110}审议通过"),
      ("1220560612", r"2024年7月8日.{0,100}首次回购股份200,000股")]),
    ("000157", "negative_scheme_attribution", "2022-07-20", "1214108860",
     "Does 'second phase' in this anchor identify a second repurchase scheme or the receiving employee ownership plan?",
     {"second_phase_modifies": "employee_ownership_plan", "anchor_event": "non_trade_transfer_and_share_disposal",
      "second_repurchase_scheme_established_by_anchor": False},
     [("1214108860", r"2022年7月20日.{0,110}审议通过"),
      ("1218078561", r"第二期核心经营管理层持股计划非交易过户完成暨回购股份处理完成"),
      ("1218078561", r"2023年10月17日.{0,100}非交易过户")]),
    ("300415", "termination_history", "2023-10-30", "1220950049",
     "Does early termination mean no purchases occurred? Give the disclosed share total and board decision date.",
     {"past_purchases_disclosed": True, "shares": 8000167, "termination_board_date": "2024-08-21"},
     [("1220950049", r"2023年10月30日.{0,150}审议通过"), ("1220950049", r"2024年8月21日.{0,130}审议通过"),
      ("1220950049", r"累计回购公司股份8,000,167股")]),
    ("002027", "termination_without_execution", "2022-10-14", "1216690584",
     "Did the company disclose purchases before terminating this scheme, and what is the board decision date?",
     {"past_purchases_disclosed": False, "termination_board_date": "2023-04-27", "shareholder_approval_required_for_termination": False},
     [("1216690584", r"2022年10月14日.{0,100}审议通过"), ("1216690584", r"2023年4月27日.{0,100}审议通过"),
      ("1216690584", r"截至公告披露日，公司尚未回购股份"), ("1216690584", r"无需提交公司股东大会审议")]),
    ("002278", "termination_history", "2022-05-12", "1216696973",
     "Was the scheme terminated after partial execution, or completed to its planned minimum? Cite the disclosed share count and minimum ratio.",
     {"terminated_after_partial_execution": True, "shares": 1420000, "planned_minimum_completion_percent": "28.40"},
     [("1216696973", r"2022年5月12日.{0,100}审议通过"), ("1216696973", r"累计回购公司股份1,420,000股"),
      ("1216696973", r"按照回购股数下限完成28.40%"), ("1216696973", r"2023年4月27日.{0,100}审议通过.{0,40}提前终止")]),
    ("688353", "termination_history", "2024-10-08", "1222880154",
     "For the October 2024 scheme, does the termination erase previous purchases? Give the prior share total and termination board date.",
     {"past_purchases_disclosed": True, "shares": 2239165, "termination_board_date": "2025-03-24"},
     [("1222880154", r"2024年10月8日.{0,100}审议通过"), ("1222880154", r"2025年3月24日.{0,100}审议通过"),
      ("1222880154", r"累计回购公司股份2,239,165股")]),
]


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--supplement", type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new audit version; never overwrite reviewed references")
    base = ROOT / "modules/l0l4-memory/data/experiments/diverse-announcements-20261031"
    source = base / "corpus-split-v2.jsonl"
    all_docs = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    supplemental = []
    if args.supplement:
        supplemental = [json.loads(line) for line in (args.supplement / "corpus.jsonl").read_text(encoding="utf-8").splitlines()]
        assert all(d["split_candidate"] == "development" for d in supplemental)
        assert not {d["id"] for d in supplemental} & {d["id"] for d in all_docs}
        all_docs.extend(supplemental)
    docs = {d["id"]: d for d in all_docs if d["split_candidate"] == "development"}
    queue = {r["stock_code"]: r for r in [json.loads(line) for line in (base / "scheme-review-queue.jsonl").read_text(encoding="utf-8").splitlines()]
             if r["split_candidate"] == "development"}
    assert len(queue) == len(CASES) == 20 and {r[0] for r in CASES} == set(queue)
    audits, questions = [], []
    for code, task, board_date, identity_id, query, reference, patterns in CASES:
        company_docs = [d for d in docs.values() if d["stock_code"] == code]
        anchor = docs[queue[code]["anchor_id"]]
        proof = [source_span(docs["CNINFO_" + ident], pattern) for ident, pattern in patterns]
        assert all(validate_span(docs[p["source_id"]], p) for p in proof)
        year, month, day = map(int, board_date.split("-"))
        identity_pattern = f"{year}年{month}月{day}日" + r".{0,150}审议通过"
        identity_proof = source_span(docs["CNINFO_" + identity_id], identity_pattern)
        candidates = []
        for doc in company_docs:
            mentions = approval_candidates(doc)
            shared = any(m["date"] == board_date and m["kind"] == "scheme_approval_candidate" for m in mentions)
            candidates.append({"source_id": doc["id"], "title": doc["title"], "own_announcement_number": own_number(doc["text"]),
                "approval_mentions": mentions, "relation_diagnostic": "shared_explicit_approval_candidate" if shared else "requires_reference_or_semantic_check",
                "final_scheme_assignment": None})
        cutoff_date = max(date.fromisoformat(docs[p["source_id"]]["disclosure_date"]) for p in proof) + timedelta(days=1)
        cutoff = cutoff_date.isoformat() + "T00:00:00+08:00"
        eligible = [d for d in company_docs if d["disclosure_date"] < cutoff_date.isoformat()]
        assert {p["source_id"] for p in proof} <= {d["id"] for d in eligible}
        audit = {"stock_code": code, "company": queue[code]["company"], "anchor_id": anchor["id"],
            "acquisition_stratum": queue[code]["acquisition_stratum"], "split": "development", "scheme_key_candidate": code + "_BOARD_" + board_date,
            "initial_board_date_candidate": board_date, "identity_proof": identity_proof,
            "anchor_gate": anchor_gate(anchor["title"], anchor["text"]), "task_family_candidate": task,
            "source_diagnostics": candidates, "review_status": "ai_source_audit_pending_human", "human_reviewed": False,
            "final_source_links_confirmed": False, "no_model_api_calls": True}
        audits.append(audit)
        questions.append({"id": "DEV_IDENTITY_" + code, "stock_code": code, "company": queue[code]["company"],
            "split": "development", "task_family": task, "as_of": cutoff, "question": query,
            "target_scheme": audit["scheme_key_candidate"], "source_ids": [d["id"] for d in eligible],
            "reference_draft": reference, "reference_proofs": proof, "reference_tier": "assistant_source_anchored_development_draft",
            "human_reviewed": False, "formal_evaluation_ready": False, "reviewer": "", "review_notes": ""})
    if supplemental:
        for code, ident, board, first_date, shares, purchase_pattern, count_pattern in [
            ("600703", "1218619830", "2023-12-08", "2023-12-14", 711900, r"2023年12月14日.{0,80}首次回购公司股份711,900股", r"711,900股"),
            ("300415", "1218368029", "2023-10-30", "2023-11-16", 300000, r"2023年11月16日，公司首次实施了股份回购", r"首次回购股份数量：300,000股"),
            ("688353", "1221382712", "2024-10-08", "2024-10-14", 92054, r"2024年10月14日.{0,90}首次回购公司股份92,054股", r"92,054股"),
        ]:
            doc = docs["CNINFO_" + ident]
            year, month, day = map(int, board.split("-"))
            patterns = [f"{year}年{month}月{day}日" + r".{0,150}审议通过", purchase_pattern, count_pattern]
            proof = [source_span(doc, pattern) for pattern in patterns]
            cutoff_date = date.fromisoformat(doc["disclosure_date"]) + timedelta(days=1)
            eligible = [d for d in docs.values() if d["stock_code"] == code and d["disclosure_date"] < cutoff_date.isoformat()]
            questions.append({"id": "DEV_FIRST_PURCHASE_" + code, "stock_code": code, "company": queue[code]["company"],
                "split": "development", "task_family": "historical_first_purchase", "as_of": cutoff_date.isoformat() + "T00:00:00+08:00",
                "question": "As of this cutoff, which scheme does this first purchase belong to, and what purchase date and share count were disclosed?",
                "target_scheme": code + "_BOARD_" + board, "source_ids": [d["id"] for d in eligible],
                "reference_draft": {"scheme_board_date": board, "first_purchase_date": first_date, "first_purchase_shares": shares},
                "reference_proofs": proof, "reference_tier": "assistant_source_anchored_development_draft",
                "human_reviewed": False, "formal_evaluation_ready": False, "reviewer": "", "review_notes": ""})
    for question in questions:
        assert all(validate_span(docs[p["source_id"]], p) for p in question["reference_proofs"])
        assert {p["source_id"] for p in question["reference_proofs"]} <= set(question["source_ids"])
        assert all(docs[ident]["disclosure_date"] < question["as_of"][:10] for ident in question["source_ids"])
    args.out.mkdir(parents=True)
    write_rows(args.out / "scheme-audit.jsonl", audits)
    write_rows(args.out / "development-questions-draft.jsonl", questions)
    # Keep all development originals together, including explicitly different-scheme distractors.
    write_rows(args.out / "development-source-corpus.jsonl", list(docs.values()))
    total_spans = sum(len(q["reference_proofs"]) for q in questions) + len(audits)
    summary = {"development_companies": len(audits), "development_documents": len(docs), "draft_questions": len(questions),
        "source_span_checks_passed": total_spans, "reserved_company_documents_used": 0, "model_api_calls": 0,
        "human_reviewed": 0, "formal_evaluation_ready_questions": 0,
        "gates": dict(Counter(a["anchor_gate"] for a in audits)), "task_families": dict(Counter(q["task_family"] for q in questions)),
        "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "status": "development_audit_and_drafts_not_heldout_results"}
    summary["supplemental_documents"] = len(supplemental)
    if args.supplement:
        summary["supplement_sha256"] = hashlib.sha256((args.supplement / "corpus.jsonl").read_bytes()).hexdigest()
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    parts = ['<!doctype html><meta charset="utf-8"><title>Development identity review</title><style>body{font:16px/1.7 system-ui;max-width:1050px;margin:30px auto;padding:15px}details{border:1px solid #ccd6df;padding:14px;margin:14px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f8;padding:12px}summary{cursor:pointer}</style><h1>Development scheme and task review</h1><p>20 development companies only. AI source-bound drafts; no human gold or held-out performance claim. Check field scope, scheme identity and approval gates. Original corpus and acquisition splits remain unchanged.</p>']
    for question in questions:
        audit = next(a for a in audits if a['stock_code'] == question['stock_code'])
        parts.append('<details><summary>' + html.escape(audit['stock_code'] + ' ' + audit['company'] + ' | ' + audit['task_family_candidate']) + '</summary><p>' + html.escape(question['question']) + '</p><p>As of: ' + question['as_of'] + '</p><p>Gate: ' + audit['anchor_gate'] + '</p><pre>' + html.escape(json.dumps(question['reference_draft'], ensure_ascii=False, indent=2)) + '</pre>')
        for span in question['reference_proofs']:
            doc = docs[span['source_id']]
            parts.append('<p><a target="_blank" rel="noopener noreferrer" href="' + html.escape(doc['source_url'], quote=True) + '">' + span['source_id'] + '</a></p><pre>' + html.escape(span['quote']) + '</pre>')
        parts.append('<details><summary>Full eligible context documents</summary>')
        for ident in question['source_ids']:
            doc = docs[ident]
            parts.append('<details><summary>' + html.escape(doc['disclosure_date'] + ' ' + doc['title']) + '</summary><pre>' + html.escape(doc['text']) + '</pre></details>')
        parts.append('</details></details>')
    (args.out / "review.html").write_text(''.join(parts), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
