"""Source-anchored silver references. No human-review status is invented.

Main task is explicit repurchase execution stage. Conditional share cancellation
is retained as an auxiliary draft, not silently treated as an adjudicated label.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date, timedelta
from difflib import SequenceMatcher
import json
from pathlib import Path
import re

from experiments.common import manifest, read_jsonl, write_jsonl

EXCLUDE_INITIAL_YEARS = {"688121": "Initial approval on 2023-12-29, outside frozen 2024 approval cohort"}
EXCLUDE_DOCUMENTS = {
    "CNINFO_1221244900": "Second 2024 scheme approved 2024-09-13, not initial 2024-05-14 scheme",
    "CNINFO_1221904961": "New scheme approved 2024-10-25, not initial 2024-03-12 scheme",
    "CNINFO_1222221143": "New scheme approved 2024-10-25, not initial 2024-03-12 scheme",
    "CNINFO_1222458551": "New scheme approved 2024-10-25, not initial 2024-03-12 scheme",
    "CNINFO_1220647767": "2020 approval / 2021 completion scheme, distinct from 2024 approval",
}


def normalized(text):
    return re.sub(r"\s+", "", text)


def reference_at(items,day):
    """Same-day documents are jointly available under the next-day policy.

    These schemes have no reviewed correction/termination event in this task.
    Actual cumulative execution does not revert merely because one report is a plan.
    """
    rank={"NO_EXECUTION_DISCLOSED":0,"STARTED":1,"COMPLETED":2}
    available=[pair for pair in items if pair[0]["disclosure_date"]<=day]
    return max(available,key=lambda pair:(rank[pair[1]["main_reference"]["repurchase_stage"]],pair[0]["disclosure_date"],pair[0]["id"]))


def stage_proof(doc):
    text = normalized(doc["text"])
    # Exact source-backed completion, not an if/when/compliance condition.
    patterns = [r"本次回购(?:股份)?(?:方案)?(?:已|已经)(?:全部)?(?:实施)?(?:完成|完毕)",
                r"本次(?:股份)?回购(?:方案)?(?:已)?实施完毕", r"本次回购股份实施期限(?:已)?届满"]
    if doc["role"] != "initial_candidate":
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                before, after = text[max(0, match.start()-22):match.start()], text[match.end():match.end()+8]
                if re.search(r"若|如果|一旦|当.*时|或者|或在|根据.*规定", before) or after.startswith(("后", "时", "之日")):
                    continue
                return "COMPLETED", text[max(0,match.start()-75):match.end()+100], "explicit_completion"
        if re.search(r"实施完毕|实施完成|回购完成", doc["title"]):
            return "COMPLETED", text[:500], "completion_filing_title_and_source"
        for pattern in [r"累计(?:已)?回购(?:公司)?(?:A股)?(?:股份)?", r"首次.{0,65}(?:实施回购|回购公司股份|回购股份)"]:
            for match in re.finditer(pattern, text):
                window = text[max(0,match.start()-45):match.end()+200]
                if re.search(r"[1-9][\d,]*(?:\.\d+)?(?:万)?股", window) and not re.search(r"首次.{0,25}事实发生.{0,15}(?:次一交易日|之日起)", window):
                    return "STARTED", window, "actual_purchase_quantity"
        match = re.search(r"(?:尚未|未曾|未)(?:实施|进行)(?:本次|股份|公司股份|本次股份|任何股份|回购股份|回购公司股份){0,3}回购|尚未回购", text)
        if match:
            return "NO_EXECUTION_DISCLOSED", text[max(0,match.start()-65):match.end()+90], "explicit_no_execution"
    if doc["role"] == "initial_candidate":
        return "NO_EXECUTION_DISCLOSED", text[:700], "initial_approved_report_without_disclosed_execution"
    return None, text[:500], "requires_semantic_adjudication"


def reconcile_quotes(draft, documents):
    result = []
    for evidence in draft.get("evidence", []):
        if not isinstance(evidence, dict) or evidence.get("document_id") not in documents:
            continue
        source = normalized(documents[evidence["document_id"]]["text"])
        quote = normalized(str(evidence.get("quote", "")))
        match = SequenceMatcher(None, quote, source, autojunk=False).find_longest_match()
        exact = bool(quote) and quote in source
        start = source.find(quote) if exact else max(0, match.b - match.a - 30)
        end = start + len(quote) if exact else min(len(source), start + len(quote) + 90)
        result.append({"field": evidence.get("field"), "document_id": evidence["document_id"],
            "original_draft_quote": evidence.get("quote"), "exact_draft_match": exact,
            "actual_source_window": source[start:end], "normalized_start": start,
            "normalized_end": end, "semantic_equivalence_claimed": False})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--drafts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists(): parser.error("Use a new output directory")
    corpus = read_jsonl(args.corpus); drafts = {r["id"]:r for r in read_jsonl(args.drafts)}
    args.out.mkdir(parents=True)
    (args.out/"plan.json").write_text(json.dumps(manifest([args.corpus,args.drafts],
        task="source_anchored_silver_execution_stage", human_reviewed=False,
        main_metric="repurchase_stage_only", secondary_cancellation="not_adjudicated_not_scored",
        selection="original split; no prediction-based exclusions; initial and latest eligible cutoffs per company",
        source_filters="initial approval 2024; same scheme; explicit source stage proof",
        question_unit="company_scheme; do not treat source documents as independent samples"),indent=2),encoding="utf-8")
    by_id={d["id"]:d for d in corpus}; references=[]; exclusions=[]; grouped={}
    for doc in corpus:
        if doc["stock_code"] in EXCLUDE_INITIAL_YEARS or doc["id"] in EXCLUDE_DOCUMENTS:
            exclusions.append({"id":doc["id"],"reason":EXCLUDE_INITIAL_YEARS.get(doc["stock_code"],EXCLUDE_DOCUMENTS.get(doc["id"]))})
            continue
        state,proof,rule=stage_proof(doc)
        aligned=reconcile_quotes(drafts[doc["id"]].get("draft",{}),by_id)
        row={"id":doc["id"],"stock_code":doc["stock_code"],"split":doc["split"],"text_sha256":doc["text_sha256"],
             "review_status":"source_anchored_silver_not_human_reviewed","human_reviewed":False,
             "main_reference":{"repurchase_stage":state,"source_id":doc["id"],"source_quote":proof,"rule":rule},
             "draft_stage_agrees":state==drafts[doc["id"]].get("draft",{}).get("repurchase_stage"),
             "quote_reconciliation":aligned,"auxiliary_draft_unchanged":drafts[doc["id"]].get("draft",{})}
        references.append(row)
        if state: grouped.setdefault(doc["candidate_id"],[]).append((doc,row))
        else: exclusions.append({"id":doc["id"],"reason":rule})
    episodes=[]
    excluded_ids={r["id"] for r in exclusions if r["reason"]!="requires_semantic_adjudication"}
    for group,items in sorted(grouped.items()):
        chosen=sorted(items,key=lambda pair:(pair[0]["disclosure_date"],pair[0]["id"]))
        first=next(d for d in corpus if d["candidate_id"]==group and d["role"]=="initial_candidate")
        documents=[]
        for d in corpus:
            if d["candidate_id"]!=group or d["id"] in excluded_ids:continue
            bound=(date.fromisoformat(d["disclosure_date"])+timedelta(days=1)).isoformat()+"T00:00:00+08:00"
            documents.append({"id":d["id"],"text":d["text"],"stock_code":d["stock_code"],"source_url":d["source_url"],"published_at":bound})
        for doc,ref in ([chosen[0]] if len(chosen)==1 else [chosen[0],chosen[-1]]):
            proof_doc,ref=reference_at(items,doc["disclosure_date"])
            as_of=(date.fromisoformat(doc["disclosure_date"])+timedelta(days=1)).isoformat()+"T00:00:00+08:00"
            episodes.append({"id":group+"_"+doc["id"],"independence_group":group,"stock_code":doc["stock_code"],"company":doc["company"],
                "split":doc["split"],"event_key":first["company"]+" "+first["title"]+" "+first["id"],
                "as_of":as_of,"documents":documents,"reference_origin":"source_anchored_silver_not_independent_human_gold",
                "gold":{"repurchase_stage":ref["main_reference"]["repurchase_stage"],"evidence_ids":[proof_doc["id"]]},
                "reference_proof":ref["main_reference"]})
    write_jsonl(args.out/"references-silver.jsonl",references);write_jsonl(args.out/"exclusions.jsonl",exclusions)
    write_jsonl(args.out/"episodes.jsonl",episodes)
    summary={"source_documents":len(corpus),"adjudication_records":len(references),"excluded_documents":len(exclusions),
        "scheme_groups":len({e["independence_group"] for e in episodes}),"questions":len(episodes),"partitions":{s:sum(e["split"]==s for e in episodes) for s in ("development","test_reserved")},
        "class_counts":dict(Counter(e["gold"]["repurchase_stage"] for e in episodes)),
        "source_stage_disagreements_with_draft":sum(not r["draft_stage_agrees"] for r in references if r["main_reference"]["repurchase_stage"]),
        "human_reviewed":False,"cancellation_scored":False}
    (args.out/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8");print(json.dumps(summary))

if __name__=="__main__":main()
