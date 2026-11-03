"""Source-span and identity diagnostics, never automatic human adjudication."""
from datetime import date
import hashlib
import re


def compact_with_offsets(text):
    chars, offsets = [], []
    for index, char in enumerate(text):
        if not char.isspace():
            chars.append(char)
            offsets.append(index)
    return "".join(chars), offsets


def source_span(document, pattern):
    compact, offsets = compact_with_offsets(document["text"])
    match = re.search(pattern, compact)
    if not match or match.end() == match.start():
        raise ValueError("Required source pattern not found: " + document["id"])
    start, end = offsets[match.start()], offsets[match.end() - 1] + 1
    return {"source_id": document["id"], "start": start, "end": end,
            "quote": document["text"][start:end], "text_sha256": document["text_sha256"]}


def validate_span(document, span):
    return (span["source_id"] == document["id"]
            and hashlib.sha256(document["text"].encode()).hexdigest() == span["text_sha256"]
            and document["text"][span["start"]:span["end"]] == span["quote"])


def own_number(text):
    compact, _ = compact_with_offsets(text)
    match = re.search(r"(?:公告)?编号[：:]?(?:临)?(\d{4})[\-－—](\d{1,4})", compact[:260])
    return f"{match[1]}-{int(match[2]):03}" if match else None


def approval_candidates(document):
    compact, _ = compact_with_offsets(document["text"])
    results = []
    for match in re.finditer(r"(\d{4})年(\d{1,2})月(\d{1,2})日", compact):
        tail = compact[match.end():match.end() + 190]
        passed = tail.find("审议通过")
        if passed < 0 or passed > 100 or not re.search(r"召开|会议", tail[:passed]):
            continue
        relevant = tail[:passed + 90]
        if "回购" not in relevant:
            continue
        try:
            iso = date(*map(int, match.groups())).isoformat()
        except ValueError:
            continue
        after = tail[passed:passed + 90]
        kind = "termination_decision" if re.search(r"终止|取消", after) else (
            "amendment_candidate" if re.search(r"调整|增加|修订", after) else "scheme_approval_candidate")
        # A mention is a diagnostic, not a certified governing approval.
        span = source_span(document, re.escape(compact[match.start():match.end()]) + re.escape(tail[:passed + 60]))
        results.append({"date": iso, "kind": kind, "proof": span,
                        "status": "candidate_not_final_scheme_assignment"})
    return results


def anchor_gate(title, text):
    compact, _ = compact_with_offsets(text)
    if re.search(r"核查意见|法律意见", title):
        return "auxiliary_opinion_use_issuer_disclosure_for_primary_fact"
    if "非交易过户" in title or ("持股计划" in title and "处理完成" in title):
        return "share_disposal_not_a_second_repurchase_scheme"
    if "终止" in title and re.search(r"(?<!无)需提交公司股东大会审议", compact):
        return "termination_board_decision_pending_shareholder_gate"
    if re.search(r"更正|修订", title):
        return "field_scoped_update_not_automatic_stage_change"
    return "source_identity_review_required"
