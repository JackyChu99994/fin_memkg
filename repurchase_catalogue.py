"""Conservative source-bound scheme candidates, independent of reference answers."""
from collections import defaultdict
from datetime import date, timedelta
import hashlib
import re
from repurchase_identity import compact_with_offsets, own_number, source_span


def available_at(document):
    return (date.fromisoformat(document["disclosure_date"]) + timedelta(days=1)).isoformat() + "T00:00:00+08:00"


def board_decisions(document):
    text, _ = compact_with_offsets(document["text"])
    decisions = []
    for match in re.finditer(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text):
        tail = text[match.end():match.end() + 220]
        passed = tail.find("审议通过")
        if passed < 0 or passed > 130:
            continue
        before = tail[:passed]
        if "召开" not in before or "董事会" not in before:
            continue
        # Never carry an old deadline/citation date across a new sentence or date.
        if re.search(r"[。；]|\d{4}年\d{1,2}月\d{1,2}日", before):
            continue
        proposal = re.search(r"审议通过(?:了)?《([^》]{1,130})》", tail[passed:])
        if not proposal or "回购" not in proposal[1]:
            continue
        try:
            day = date(*map(int, match.groups())).isoformat()
        except ValueError:
            continue
        if day > document["disclosure_date"]:
            continue
        title = proposal[1]
        kind = "termination" if re.search(r"终止|取消", title) else (
            "amendment" if re.search(r"增加|调整|修订|变更", title) else "initial_scheme_candidate")
        fragment = text[match.start():match.end()] + tail[:passed + proposal.end()]
        decisions.append({"date": day, "kind": kind, "proposal": title,
                          "proof": source_span(document, re.escape(fragment))})
    return decisions


def primary_kind(title):
    if re.search(r"修订|更正|核查|法律|终止|调整|增加|提议|非交易过户|处理完成", title):
        return None
    if "报告书" in title:
        return "report"
    if re.search(r"回购.*方案|方案.*回购", title):
        return "proposal"
    return None


def phase(title):
    found = re.search(r"第([一二三四五六七八九十\d]+)期", title)
    return found[1] if found else None


def mentioned_numbers(text):
    return {f"{year}-{int(number):03}" for year, number in re.findall(r"(\d{4})[\-－—](\d{3,4})(?!\d)", text)}


def build_catalogue(documents, as_of):
    documents = [d for d in documents if available_at(d) <= as_of]
    if len({d["id"] for d in documents}) != len(documents):
        raise ValueError("Duplicate source ID")
    decisions, roots, unresolved = {}, {}, []
    for doc in documents:
        if hashlib.sha256(doc["text"].encode()).hexdigest() != doc["text_sha256"]:
            raise ValueError("Source text hash mismatch")
        decisions[doc["id"]] = board_decisions(doc)
        kind = primary_kind(doc["title"])
        if not kind:
            continue
        candidates = [d for d in decisions[doc["id"]] if d["kind"] == "initial_scheme_candidate"]
        days = {d["date"] for d in candidates}
        if len(days) != 1:
            unresolved.append({"source_id": doc["id"], "reason": "no_unique_explicit_initial_board_date", "dates": sorted(days)})
            continue
        roots[doc["id"]] = {"source_id": doc["id"], "stock_code": doc["stock_code"], "date": next(iter(days)),
            "kind": kind, "phase": phase(doc["title"]), "own_number": own_number(doc["text"]),
            "available_at": available_at(doc), "proof": candidates[0]["proof"]}
    parent = {ident: ident for ident in roots}
    def find(ident):
        while parent[ident] != ident:
            ident = parent[ident]
        return ident
    date_phases = defaultdict(set)
    for root in roots.values():
        if root["phase"]:
            date_phases[(root["stock_code"], root["date"])].add(root["phase"])
    alias_proofs = []
    by_doc = {d["id"]: d for d in documents}
    for ident, report in roots.items():
        if report["kind"] != "report":
            continue
        numbers = mentioned_numbers(by_doc[ident]["text"])
        options = [p for p in roots.values() if p["kind"] == "proposal" and p["stock_code"] == report["stock_code"]
                   and p["date"] == report["date"] and p["own_number"] and p["own_number"] in numbers
                   and (not p["phase"] or not report["phase"] or p["phase"] == report["phase"])]
        if len(date_phases[(report["stock_code"], report["date"])]) > 1:
            options = [p for p in options if p["phase"] and p["phase"] == report["phase"]]
        if len(options) == 1:
            target = options[0]["source_id"]
            parent[find(ident)] = find(target)
            alias_proofs.append({"report": ident, "proposal": target, "rule": "same_explicit_board_date_and_unique_cited_proposal_number",
                                 "available_at": max(roots[ident]["available_at"], roots[target]["available_at"])})
    groups = defaultdict(list)
    for ident in roots:
        groups[find(ident)].append(ident)
    schemes, source_map = [], {}
    for members in groups.values():
        ordered = sorted(members, key=lambda ident: (roots[ident]["available_at"], ident))
        anchor = ordered[0]
        key = roots[anchor]["stock_code"] + "_SRC_" + anchor
        schemes.append({"scheme_id": key, "stock_code": roots[anchor]["stock_code"], "board_date_candidate": roots[anchor]["date"],
                        "anchor_sources": ordered, "proofs": [roots[i]["proof"] for i in ordered], "human_verified": False,
                        "identity_status": "source_bound_candidate_not_certified_unique_event"})
        for ident in ordered:
            source_map[ident] = key
    links = []
    for doc in documents:
        if doc["id"] in source_map:
            links.append({"source_id": doc["id"], "scheme_id": source_map[doc["id"]], "relation": "ANCHORS_CANDIDATE"})
            continue
        dates = {d["date"] for d in decisions[doc["id"]] if d["kind"] == "initial_scheme_candidate"}
        numbers = mentioned_numbers(doc["text"])
        for scheme in schemes:
            if scheme["stock_code"] != doc["stock_code"]:
                continue
            cited = [i for i in scheme["anchor_sources"] if roots[i]["own_number"] and roots[i]["own_number"] in numbers]
            if scheme["board_date_candidate"] in dates or cited:
                links.append({"source_id": doc["id"], "scheme_id": scheme["scheme_id"], "relation": "REFERS_TO_CANDIDATE",
                              "explicit_board_date_match": scheme["board_date_candidate"] in dates, "cited_anchor_sources": cited})
    return {"as_of": as_of, "schemes": sorted(schemes, key=lambda s: s["scheme_id"]), "links": links,
            "unresolved_primaries": unresolved, "alias_proofs": alias_proofs,
            "sources": [{k: d[k] for k in ("id", "stock_code", "title", "disclosure_date", "source_url", "text_sha256")} for d in documents],
            "no_model_calls": True, "reference_answers_used": False, "all_identities_pending_semantic_review": True}


def resolve_source_scheme(catalogue, source_id, claimed_date):
    normalized = date.fromisoformat(claimed_date).isoformat()
    candidates = {link["scheme_id"] for link in catalogue["links"] if link["source_id"] == source_id}
    matched = [s for s in catalogue["schemes"] if s["scheme_id"] in candidates and s["board_date_candidate"] == normalized]
    return {"source_id": source_id, "claimed_board_date": normalized,
            "status": "unique_source_bound_candidate" if len(matched) == 1 else "unresolved_or_ambiguous",
            "scheme_ids": [s["scheme_id"] for s in matched], "human_verified": False}
