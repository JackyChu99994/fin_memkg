"""Fixed source-bound task templates; candidates still require semantic review."""
from datetime import date, timedelta
from itertools import combinations
import re
from repurchase_catalogue import board_decisions, primary_kind
from repurchase_evaluation import build_public_task, normalize_field, normalize_number
from repurchase_identity import compact_with_offsets, source_span, validate_span


def cutoff_for(doc):
    return (date.fromisoformat(doc["disclosure_date"]) + timedelta(days=1)).isoformat() + "T00:00:00+08:00"


def identity(doc):
    decisions = [m for m in board_decisions(doc) if m["kind"] == "initial_scheme_candidate"]
    dates = {m["date"] for m in decisions}
    if len(dates) != 1:
        return None
    return next(m for m in decisions if m["date"] == next(iter(dates)))


def quantity(doc):
    text, _ = compact_with_offsets(doc["text"])
    pattern = r"(?:累计已回购股数|累计(?:已)?回购(?:公司)?(?:A股)?(?:股份)?(?:数量)?(?:为)?)([\d,]+(?:\.\d+)?)(万)?股"
    candidates = []
    for match in re.finditer(pattern, text):
        before = text[max(0, match.start()-35):match.start()]
        if re.search(r"若|如果|预计|假设|拟|计划|将", before):
            continue
        try:
            count = int(normalize_number(match[1] + (match[2] or "") + "股", "shares"))
        except ValueError:
            continue
        if count > 0:
            candidates.append((count, source_span(doc, re.escape(match.group()))))
    if len({c[0] for c in candidates}) != 1:
        return None
    return candidates[0]


def explicit_stage(doc):
    text, _ = compact_with_offsets(doc["text"])
    # A terminated scheme may have real purchases; do not call termination completion.
    if "终止" not in doc["title"]:
        for match in re.finditer(r"本次(?:股份)?回购(?:股份)?(?:方案)?(?:已|已经)?(?:全部)?实施(?:完毕|完成)|公司完成回购", text):
            before = text[max(0, match.start()-30):match.start()]
            after = text[match.end():match.end()+8]
            if re.search(r"若|如果|假设|拟|将|当.*时|根据.*规定", before) or after.startswith(("后", "时", "之日")):
                continue
            fragment = text[max(0, match.start()-50):match.end()+60]
            return "COMPLETED", source_span(doc, re.escape(fragment))
    actual = quantity(doc)
    if actual:
        return "STARTED", actual[1]
    match = re.search(r"(?:尚未|未曾)(?:进行|实施)?(?:任何|本次)?(?:股份)?回购|尚未回购股份", text)
    if match:
        return "NO_EXECUTION_DISCLOSED", source_span(doc, re.escape(text[max(0,match.start()-30):match.end()+50]))
    return None


def first_purchase(doc):
    text, _ = compact_with_offsets(doc["text"])
    # Try each date independently: a statistics date preceding a heading must
    # not consume the subsequent transaction date or be used as its answer.
    pattern = r"(\d{4})年(\d{1,2})月(\d{1,2})日([^。]{0,110}?)首次([^。]{0,130})"
    for start in re.finditer(r"\d{4}年\d{1,2}月\d{1,2}日", text):
        match = re.match(pattern, text[start.start():])
        if not match:
            continue
        fragment = match.group()
        if "回购" not in fragment or re.search(r"若|如果|拟|将|计划|预计", match[4] + match[5]):
            continue
        shares = re.search(r"[1-9][\d,]*(?:\.\d+)?(?:万)?股", fragment)
        if not shares:
            continue
        if re.search(r"\d{4}年\d{1,2}月\d{1,2}日", fragment[match.end(3)+1:shares.start()]):
            continue
        try:
            day = date(*map(int, match.group(1,2,3))).isoformat()
        except ValueError:
            continue
        if day <= doc["disclosure_date"]:
            return day, source_span(doc, re.escape(fragment))
    return None


def build_question(item, family, documents):
    ordered = sorted(documents, key=lambda d: (d["disclosure_date"], d["id"]))
    identities = {d["id"]: identity(d) for d in ordered}
    proofs, answer, requested, extra = [], {}, [], {}
    selected = None
    question = ""
    if family == "stage":
        for doc in reversed(ordered):
            stage = explicit_stage(doc)
            if identities[doc["id"]] and stage:
                selected = doc
                answer = {"repurchase_stage": stage[0]}
                proofs = [{**stage[1], "fields": ["repurchase_stage"]}]
                question = f"According to {doc['id']}, what repurchase execution stage is explicitly disclosed for its original scheme? Reported purchases before termination remain purchases; termination is not implementation completion."
                break
    elif family == "historical":
        for doc in ordered:
            first = first_purchase(doc)
            if identities[doc["id"]] and first and doc["disclosure_date"] < ordered[-1]["disclosure_date"]:
                selected = doc
                answer = {"first_purchase_date": first[0]}
                proofs = [{**first[1], "fields": ["first_purchase_date"]}]
                question = f"At this historical cutoff, what first actual purchase date does {doc['id']} disclose for its original scheme? Do not use later filings."
                break
    elif family == "multi_scheme":
        roots = [d for d in ordered if primary_kind(d["title"]) and identities[d["id"]]]
        pair = next(((a,b) for a,b in combinations(roots, 2) if identities[a["id"]]["date"] != identities[b["id"]]["date"]), None)
        if pair:
            a,b = pair
            selected = max(pair, key=lambda d: d["disclosure_date"])
            answer = {"same_scheme": False, "source_approval_dates": {d["id"]: identities[d["id"]]["date"] for d in pair}}
            proofs = [{**identities[d["id"]]["proof"], "fields": ["same_scheme", "source_approval_dates"]} for d in pair]
            extra["requested_source_ids"] = [d["id"] for d in pair]
            extra["target_date"] = max(identities[d["id"]]["date"] for d in pair)
            target_doc = max(pair, key=lambda d: identities[d["id"]]["date"])
            extra["identity_override"] = identities[target_doc["id"]]["proof"]
            question = f"Do reports {a['id']} and {b['id']} concern the same original scheme? Map ONLY these two source IDs to their original board approval dates."
    elif family == "update":
        for doc in reversed(ordered):
            terms = {m["date"]:m for m in board_decisions(doc) if m["kind"] == "termination"}
            if identities[doc["id"]] and len(terms) == 1:
                term = next(iter(terms.values()))
                selected = doc
                answer = {"termination_board_date": term["date"], "board_approved_termination": True}
                proofs = [{**term["proof"], "fields": list(answer)}]
                text, _ = compact_with_offsets(doc["text"])
                no = re.search(r"本次(?:提前)?终止[^。]{0,110}无需提交(?:公司)?股东大会审议", text)
                yes = re.search(r"本次(?:提前)?终止[^。]{0,110}(?<!无)需提交(?:公司)?股东大会审议", text)
                if bool(no) != bool(yes):
                    match = no or yes
                    answer["shareholder_approval_still_required"] = bool(yes)
                    proofs.append({**source_span(doc, re.escape(match.group())), "fields": ["shareholder_approval_still_required"]})
                question = f"What termination board decision date is disclosed in {doc['id']} for its original scheme? Return any requested shareholder-gate condition separately from execution history."
                break
    elif family == "evidence_trace":
        outcomes = []
        for doc in ordered:
            stage, count = explicit_stage(doc), quantity(doc)
            if identities[doc["id"]] and stage and stage[0] == "COMPLETED" and count:
                outcomes.append((doc, count))
        for (a, ca), (b, cb) in combinations(outcomes, 2):
            if identities[a["id"]]["date"] == identities[b["id"]]["date"]:
                continue
            atext, _ = compact_with_offsets(a["text"])
            btext, _ = compact_with_offsets(b["text"])
            # Conservative necessity check: reject a source that repeats the other operand.
            if str(ca[0]) in btext.replace(",", "") or str(cb[0]) in atext.replace(",", ""):
                continue
            selected = max((a,b), key=lambda d: d["disclosure_date"])
            answer = {"shares": ca[0] + cb[0]}
            proofs = [{**ca[1], "fields": ["shares"]}, {**cb[1], "fields": ["shares"]}]
            extra["target_date"] = max(identities[a["id"]]["date"], identities[b["id"]]["date"])
            target_doc = max((a,b), key=lambda d: identities[d["id"]]["date"])
            extra["identity_override"] = identities[target_doc["id"]]["proof"]
            extra["derivation"] = {"operation": "integer_sum", "operands": [{"source_id": a["id"], "shares": ca[0]}, {"source_id": b["id"], "shares": cb[0]}],
                "necessity_status": "source_nonrepetition_check_passed_semantic_review_pending"}
            question = f"Using completed-scheme disclosures {a['id']} and {b['id']}, what is the combined actual repurchased share count across those two different schemes? Add each scheme once; no planned counts."
            break
    elif family == "insufficient":
        for doc in ordered:
            if not primary_kind(doc["title"]) or not identities[doc["id"]]:
                continue
            eligible = [d for d in ordered if d["disclosure_date"] <= doc["disclosure_date"]]
            if any(first_purchase(d) for d in eligible):
                continue
            selected = doc
            requested = ["first_purchase_date"]
            proofs = [{**identities[doc["id"]]["proof"], "fields": []}]
            extra["reference_answerability"] = "insufficient"
            extra["reference_missing_reason"] = "The complete supplied archive at this cutoff has no matched explicit first-purchase date; this is an archive-scoped candidate absence, not proof of no real-world purchases."
            extra["absence_status"] = "conservative_pattern_check_requires_semantic_review"
            question = f"Can the supplied archive available at this cutoff establish the actual first purchase date for the original scheme described in {doc['id']}? Give that date only if disclosed; a planned deadline or board approval is not the purchase date."
            break
    if selected is None:
        return None, "No source combination meets this fixed template; identity/field/source supplementation or semantic adjudication needed"
    identity_row = identities[selected["id"]]
    board = extra.pop("target_date", identity_row["date"])
    identity_proof = extra.pop("identity_override", identity_row["proof"])
    cutoff = cutoff_for(selected)
    eligible = [d for d in ordered if cutoff_for(d) <= cutoff]
    result = {"id": "RSV_SOURCE_" + item["stock_code"] + "_" + family, "stock_code": item["stock_code"], "company": item["company"],
        "split": "test_reserved", "split_version": 2, "benchmark_family": family, "as_of": cutoff, "question": question,
        "target_scheme": item["stock_code"] + "_BOARD_" + board, "requested_fields": requested or list(answer),
        "source_ids": [d["id"] for d in eligible], "reference_draft": answer, "reference_proofs": proofs,
        "identity_proof": identity_proof, "reference_answerability": "answerable", "reference_missing_reason": "",
        "reference_tier": "source_anchored_silver", "reference_origin": "fixed_source_template_not_model_generated_answer",
        "source_qualification": "pending", "human_reviewed": False, "formal_evaluation_ready": False,
        "evidence_policy": "natural_archive_gap", "mechanical_checks": "passed_for_review_only", **extra}
    by_id = {d["id"]:d for d in documents}
    for proof in proofs + [result["identity_proof"]]:
        assert proof["source_id"] in result["source_ids"] and validate_span(by_id[proof["source_id"]], proof)
    for field, value in answer.items():
        normalize_field(field, value, value)
    build_public_task(result, by_id)
    return result, None
