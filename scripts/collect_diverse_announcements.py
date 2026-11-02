"""Collect original CNINFO challenge candidates; no inferred labels or model calls."""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules/l0l4-memory"))
from experiments.expand_lifecycle import query, clean, EXCLUDED

SEED = "fin-memkg-diverse-sources-20261031-v1"
SEARCHES = ["回购更正", "回购修订", "终止回购", "第二期回购", "回购实施完毕", "回购实施完成", "回购实施结果"]
PATTERNS = {"correction": r"更正|修订|调整回购.*(?:方案|用途)",
            "termination": r"终止|取消", "multiple_scheme": r"第二期|第三期|新一期|第二次",
            "completion": r"实施完毕|实施完成|实施结果|回购完成"}


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def eligible(row):
    title = clean(row.get("announcementTitle"))
    return (bool(re.fullmatch(r"(?:00|30|60|68)\d{4}", row.get("secCode", "")))
            and "回购" in title and not re.search(
                r"限制性|激励|法律意见|监事|独立董事|债权人|英文|摘要|注销|H股", title))


def categories(row):
    title = clean(row["announcementTitle"])
    return [name for name, pattern in PATTERNS.items() if re.search(pattern, title)]


def rank(code):
    return digest((SEED + ":" + code).encode())


def fetch_query(path, page, term, interval, stock=""):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    attempts = []
    for attempt in range(3):
        try:
            value = query(page, term, interval, stock)
            dump(path, value)
            if attempts:
                dump(path.with_suffix(".attempts.json"), attempts + [{"attempt": attempt + 1, "status": "ok"}])
            return value
        except Exception as exc:
            attempts.append({"attempt": attempt + 1, "error": type(exc).__name__})
            time.sleep(.5 * (attempt + 1))
    dump(path.with_suffix(".attempts.json"), attempts)
    raise RuntimeError("Official query failed after three recorded attempts")


def search_pool(out, excluded):
    pools, audits = {}, []
    for term_index, term in enumerate(SEARCHES):
        first = fetch_query(out / f"searches/{term_index:02}/001.json", 1, term, "2023-01-01~2025-12-31")
        needed = math.ceil(first["totalAnnouncement"] / 30)
        limit = min(needed, 12)
        responses = [first]
        for page in range(2, limit + 1):
            responses.append(fetch_query(out / f"searches/{term_index:02}/{page:03}.json", page, term, "2023-01-01~2025-12-31"))
        rows = [r for response in responses for r in response.get("announcements") or []]
        unique = {str(r["announcementId"]): r for r in rows}
        audits.append({"term": term, "reported_totals": sorted({r["totalAnnouncement"] for r in responses}),
                       "pages": limit, "page_cap": 12, "retrieved_rows": len(rows), "unique_ids": len(unique),
                       "exhaustive_coverage_claimed": False, "page_cap_reached": needed > limit})
        for ident, row in unique.items():
            if row["secCode"] not in excluded and eligible(row) and categories(row):
                pools[ident] = row
        print("search", term_index, "rows", len(rows), "eligible_pool", len(pools), flush=True)
    dump(out / "search-audit.json", audits)
    dump(out / "candidate-pool.json", list(pools.values()))
    return list(pools.values())


def select(pool, target):
    selected = {}
    for category in ("correction", "termination", "multiple_scheme", "completion"):
        options = sorted([r for r in pool if category in categories(r)],
                         key=lambda r: (rank(r["secCode"]), r["adjunctUrl"], str(r["announcementId"])))
        allocated = 0
        for row in options:
            if row["secCode"] in selected:
                continue
            selected[row["secCode"]] = {"anchor": row, "acquisition_stratum": category}
            allocated += 1
            if allocated >= target // 4:
                break
    for row in sorted(pool, key=lambda r: (rank(r["secCode"]), str(r["announcementId"]))):
        if len(selected) >= target:
            break
        selected.setdefault(row["secCode"], {"anchor": row, "acquisition_stratum": categories(row)[0]})
    result = sorted(selected.values(), key=lambda item: rank(item["anchor"]["secCode"]))[:target]
    development = development_codes(result, target // 4)
    for item in result:
        item["split_candidate"] = "development" if item["anchor"]["secCode"] in development else "test_reserved"
        item["status"] = "title_selected_identity_and_reference_unreviewed"
    return result


def development_codes(selected, count):
    """Round-robin stratum allocation avoids an empty development class."""
    groups = {category: sorted([r for r in selected if r["acquisition_stratum"] == category],
                              key=lambda r: rank(r["anchor"]["secCode"])) for category in PATTERNS}
    chosen = set()
    index = 0
    while len(chosen) < count:
        added = False
        for category in PATTERNS:
            if len(groups[category]) > index and len(chosen) < count:
                chosen.add(groups[category][index]["anchor"]["secCode"])
                added = True
        if not added:
            break
        index += 1
    return chosen


def collect_company(item, out):
    anchor = item["anchor"]
    code = anchor["secCode"]
    folder = out / "companies" / code
    result_path = folder / "candidate.json"
    if result_path.exists():
        previous = json.loads(result_path.read_text(encoding="utf-8"))
        if previous.get("collection_pass_finished"):
            return previous
    result = {"stock_code": code, "company": clean(anchor["secName"]),
              "acquisition_stratum": item["acquisition_stratum"], "split_candidate": item["split_candidate"],
              "anchor_id": "CNINFO_" + str(anchor["announcementId"]), "documents": [], "errors": [],
              "scheme_identity_verified": False, "review_status": "unreviewed"}
    try:
        first = fetch_query(folder / "queries/001.json", 1, "回购", "2022-01-01~2025-12-31", code + "," + anchor["orgId"])
        count = math.ceil(first["totalAnnouncement"] / 30)
        responses = [first]
        for page in range(2, min(count, 12) + 1):
            responses.append(fetch_query(folder / f"queries/{page:03}.json", page, "回购", "2022-01-01~2025-12-31", code + "," + anchor["orgId"]))
        all_rows = [r for response in responses for r in response.get("announcements") or []]
        if any(r["secCode"] != code for r in all_rows):
            raise ValueError("Company query returned different security")
        unique = {str(r["announcementId"]): r for r in all_rows}
        result["query_audit"] = {"metadata_rows": len(all_rows), "unique_ids": len(unique),
                                  "reported_total": first["totalAnnouncement"], "page_cap_reached": count > 12,
                                  "context_window": "2022-01-01~2025-12-31", "complete_chain_claimed": False}
        rows = [r for r in unique.values() if eligible(r)]
        anchor_date = anchor["adjunctUrl"].split("/")[1]
        def proximity(row):
            date = row["adjunctUrl"].split("/")[1]
            return (abs((datetime.fromisoformat(date) - datetime.fromisoformat(anchor_date)).days), str(row["announcementId"]))
        chosen = {str(anchor["announcementId"]): anchor}
        for pattern, quota in ((r"回购(?:股份)?报告书|回购.*方案", 3), (r"首次", 1),
                               (r"进展", 2), (r"更正|终止|实施完毕|实施完成|实施结果|第二期", 2)):
            kept = 0
            for row in sorted(rows, key=proximity):
                ident = str(row["announcementId"])
                if re.search(pattern, clean(row["announcementTitle"])) and ident not in chosen:
                    chosen[ident] = row
                    kept += 1
                    if kept >= quota or len(chosen) >= 9:
                        break
            if len(chosen) >= 9:
                break
        result["selection_policy"] = "anchor plus nearest title-qualified context, maximum nine PDFs; scheme identity NOT assumed"
        dump(folder / "selected-metadata.json", list(chosen.values()))
        for ident, row in chosen.items():
            path = folder / (ident + ".pdf")
            url = "https://static.cninfo.com.cn/" + row["adjunctUrl"]
            try:
                content = path.read_bytes() if path.exists() else urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=35).read()
                if not content.startswith(b"%PDF"):
                    raise ValueError("Response is not PDF")
                if not path.exists():
                    path.write_bytes(content)
                result["documents"].append({"id": "CNINFO_" + ident, "title": clean(row["announcementTitle"]),
                    "disclosure_date": row["adjunctUrl"].split("/")[1], "source_url": url,
                    "pdf": path.relative_to(out).as_posix(), "pdf_sha256": digest(content), "official_metadata": row,
                    "role": "anchor_candidate" if ident == str(anchor["announcementId"]) else "context_candidate",
                    "title_tags": categories(row), "review_status": "unreviewed"})
            except Exception as exc:
                result["errors"].append({"id": "CNINFO_" + ident, "phase": "download", "error": type(exc).__name__})
            dump(result_path, result)
            time.sleep(.15)
    except Exception as exc:
        result["errors"].append({"phase": "company_context", "error": type(exc).__name__})
    result["collection_pass_finished"] = True
    dump(result_path, result)
    print("company", code, item["acquisition_stratum"], "pdfs", len(result["documents"]), "errors", len(result["errors"]), flush=True)
    return result


def extract(candidates, out):
    from pypdf import PdfReader
    docs, errors = [], []
    for candidate in candidates:
        for doc in candidate["documents"]:
            try:
                path = out / doc["pdf"]
                assert digest(path.read_bytes()) == doc["pdf_sha256"]
                reader = PdfReader(path)
                text = "\n\n".join(f"[Page {i+1}]\n" + (page.extract_text() or "") for i, page in enumerate(reader.pages))
                if len(clean(text)) < 100 or text.count("\ufffd") > 3:
                    raise ValueError("OCR_or_encoding_review_required")
                path.with_suffix(".txt").write_text(text, encoding="utf-8")
                docs.append({**doc, "stock_code": candidate["stock_code"], "company": candidate["company"],
                    "split_candidate": candidate["split_candidate"], "acquisition_stratum": candidate["acquisition_stratum"],
                    "pages": len(reader.pages), "text": text, "text_sha256": digest(text.encode()),
                    "scheme_identity_verified": False})
            except Exception as exc:
                errors.append({"id": doc["id"], "error": type(exc).__name__})
    (out / "corpus.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs), encoding="utf-8")
    dump(out / "extraction-errors.json", errors)
    summary = {"candidate_companies": len(candidates), "companies_with_extracted_text": len({d["stock_code"] for d in docs}),
        "downloaded_pdfs": sum(len(c["documents"]) for c in candidates), "extracted_documents": len(docs),
        "pages": sum(d["pages"] for d in docs), "unique_pdf_hashes": len({d["pdf_sha256"] for d in docs}),
        "acquisition_strata": dict(Counter(c["acquisition_stratum"] for c in candidates)),
        "document_title_tags": dict(Counter(t for d in docs for t in d["title_tags"])),
        "company_errors": sum(len(c["errors"]) for c in candidates), "extraction_errors": len(errors),
        "human_reviewed_documents": 0, "qualified_questions": 0, "model_calls": 0,
        "status": "downloaded_candidates_not_evaluation_ready"}
    dump(out / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--target", type=int, default=80)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.target < 4 or args.target % 4:
        parser.error("Target must be a positive multiple of four, at least four")
    if args.out.exists() and not args.resume:
        parser.error("Use a new directory or explicit --resume")
    args.out.mkdir(parents=True, exist_ok=True)
    old = ROOT / "modules/l0l4-memory/data/experiments/lifecycle-expanded40-20261030/corpus.jsonl"
    excluded = EXCLUDED | {json.loads(line)["stock_code"] for line in old.read_text(encoding="utf-8").splitlines()}
    if not (args.out / "protocol.json").exists():
        dump(args.out / "protocol.json", {"created_at": datetime.now(timezone.utc).isoformat(), "seed": SEED,
            "target_companies": args.target, "search_terms": SEARCHES, "anchor_interval": "2023-01-01~2025-12-31",
            "excluded_companies": sorted(excluded), "selection": "title-stratified hash-ranked observed pool; unmet strata reported",
            "search_page_cap_per_term": 12, "source": "official_CNINFO_PDF",
            "sampling": "purposive_challenge_candidates_not_market_random", "model_calls": 0})
    if (args.out / "selected-companies.json").exists():
        selected = json.loads((args.out / "selected-companies.json").read_text(encoding="utf-8"))
    else:
        pool = search_pool(args.out, excluded)
        selected = select(pool, args.target)
        dump(args.out / "selected-companies.json", selected)
    print("frozen candidate companies", len(selected), flush=True)
    with ThreadPoolExecutor(max_workers=3) as executor:
        candidates = list(executor.map(lambda item: collect_company(item, args.out), selected))
    dump(args.out / "candidates.json", candidates)
    extract(candidates, args.out)


if __name__ == "__main__":
    main()
