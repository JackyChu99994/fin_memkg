"""Inspect saved audit failures and inference risks without changing references."""
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.extend_reserved_source_review import read_rows, write_rows
from repurchase_identity import source_span


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--html", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or args.html.exists():
        parser.error("Use new review artifacts")
    base = ROOT / "modules/l0l4-memory/data/experiments"
    corpus = base / "diverse-announcements-20261031/corpus-split-v2.jsonl"
    docs = {d["id"]: d for d in read_rows(corpus)}
    qs = {q["id"]: q for q in read_rows(base / "reserved-source-questions-v6-20261102/questions-source-candidates.jsonl")}
    records = []
    for row in read_rows(args.audit / "audit-results.jsonl"):
        if row["question_id"] not in qs:
            continue
        q = qs[row["question_id"]]
        result = json.loads(row.get("raw", "{}"))
        quotes = []
        for item in result.get("evidence", []):
            try:
                span = source_span(docs[item["source_id"]], re.escape(re.sub(r"\s+", "", item["quote"])))
                quotes.append({**item, "matched": True, "span": span})
            except (KeyError, ValueError, TypeError):
                quotes.append({**item, "matched": False})
        text = json.dumps({"reason": result.get("reason"), "sources": result.get("sources")}, ensure_ascii=False)
        risk = bool(re.search(r"imply|implies|implying|zero executed|has not yet|not yet commenced|confirms no purchase|earliest possible", text, re.I))
        records.append({"question_id": q["id"], "company": q["company"], "audit_status": row["status"],
                        "model_decision": result.get("decision"), "result": result, "quote_checks": quotes,
                        "inference_wording_flag_requires_semantic_review": risk,
                        "source_qualification": "pending", "human_reviewed": False,
                        "source_ids": q["source_ids"], "target_scheme": q["target_scheme"], "as_of": q["as_of"]})
    args.out.mkdir(parents=True)
    write_rows(args.out / "audit-followup.jsonl", records)
    summary = {"company_audits": len(records), "passed_format_and_all_quotes": sum(r["audit_status"] != "failed" for r in records),
               "failed_format_or_quotes": sum(r["audit_status"] == "failed" for r in records),
               "unmatched_quotes": sum(not q["matched"] for r in records for q in r["quote_checks"]),
               "reasoning_wording_flags": sum(r["inference_wording_flag_requires_semantic_review"] for r in records),
               "source_qualification_changed": False, "human_reviewed": 0, "method_comparison_calls": 0,
               "audit_response_sha256": hashlib.sha256((args.audit / "audit-results.jsonl").read_bytes()).hexdigest()}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    body = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>22道负例全文审查记录</title><style>body{max-width:1100px;margin:30px auto;padding:16px;font:16px/1.7 system-ui;color:#17212b}article{border:1px solid #ccd5df;border-radius:8px;padding:20px;margin:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f8;padding:12px;max-height:480px;overflow:auto;font:14px/1.6 system-ui}summary{cursor:pointer}.notice{padding:15px;background:#fff2d8}</style><h1>22道负例：Qwen全文审查与校验记录</h1><p class="notice">这不是人工金标准或模型方法对照。模型读了给定全部原文，但格式、引文通过不代表缺失判断正确。全部22道仍待来源资格核对，没有自动改成已确认。</p><pre>' + escape(json.dumps(summary, ensure_ascii=False, indent=2)) + '</pre>']
    for r in records:
        body.append('<article><h2>' + escape(r["company"] + ' ' + r["question_id"]) + '</h2><p>' + escape(r["target_scheme"] + ' 截止 ' + r["as_of"]) + '</p><p>格式/引文：' + escape(r["audit_status"]) + '；推理措辞标记：' + str(r["inference_wording_flag_requires_semantic_review"]) + '</p><details><summary>模型判断与逐条引文校验</summary><pre>' + escape(json.dumps(r, ensure_ascii=False, indent=2)) + '</pre></details>')
        for sid in r["source_ids"]:
            d = docs[sid]
            body.append('<details><summary>' + escape(d["title"] + ' ' + sid) + '</summary><a target="_blank" rel="noopener noreferrer" href="' + escape(d["source_url"], quote=True) + '">官方PDF</a><pre>' + escape(d["text"]) + '</pre></details>')
        body.append('</article>')
    body.append('</html>')
    args.html.write_text(''.join(body), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
