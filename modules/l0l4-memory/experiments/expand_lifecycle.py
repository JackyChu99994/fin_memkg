"""Collect a frozen multi-company candidate corpus from original CNINFO filings.

Candidates are not automatically verified independent event chains or labeled
test cases. No model calls, market outcomes, or reference answers are used.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from experiments.common import manifest, now, sha256, write_jsonl

EXCLUDED = {"002594", "300750", "300308", "300502", "002466", "600519"}
SEED = "fin-memkg-expansion-20261030-v1"
API = "https://www.cninfo.com.cn/new/hisAnnouncement/query"


def clean(value):
    return re.sub(r"\s+", "", re.sub(r"<[^>]*>", "", value or ""))


def rank(code):
    return hashlib.sha256((SEED + ":" + code).encode()).hexdigest()


def initial_candidate(row):
    title = clean(row.get("announcementTitle"))
    return bool(re.search(r"回购(?:股份)?报告书", title)) and not re.search(
        r"更正|修订|英文|摘要|法律意见|限制性股票|注销部分", title)


def followup_candidate(row):
    title = clean(row.get("announcementTitle"))
    return "回购" in title and bool(re.search(r"进展|首次|实施完毕|实施完成|回购完成|注销完成|终止|取消", title)) and not re.search(
        r"限制性股票|激励对象|法律意见|债权人|前十|英文|摘要", title)


def request_json(parameters):
    request = Request(API, data=urlencode(parameters).encode(), headers={
        "User-Agent": "Mozilla/5.0", "Referer": "https://www.cninfo.com.cn/"})
    with urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    time.sleep(.15)
    if "totalAnnouncement" not in result:
        raise ValueError("Unexpected official query response")
    return result


def query(page, search, interval, stock=""):
    return request_json({"pageNum": page, "pageSize": 30, "column": "szse", "tabName": "fulltext",
        "searchkey": search, "stock": stock, "seDate": interval, "sortName": "time",
        "sortType": "asc", "isHLtitle": "true"})


def select_companies(rows, target=40):
    first = {}
    for row in sorted(rows, key=lambda r: (r["adjunctUrl"].split("/")[1], str(r["announcementId"]))):
        code = row.get("secCode", "")
        if len(code) == 6 and code.isdigit() and code not in EXCLUDED and initial_candidate(row):
            first.setdefault(code, row)
    return sorted(first.values(), key=lambda r: rank(r["secCode"]))[:target]


def collect_chain(initial, out, split):
    code = initial["secCode"]
    directory = out / "companies" / code
    directory.mkdir(parents=True)
    result = {"id": "CANDIDATE_" + code, "stock_code": code, "company": clean(initial["secName"]),
              "split": split, "event_identity_status": "candidate_pending_full_source_review",
              "review_status": "unreviewed", "documents": [], "errors": []}
    try:
        start = initial["adjunctUrl"].split("/")[1]
        rows = []
        page = 1
        while True:
            response = query(page, "回购", start + "~2025-03-31", code + "," + initial["orgId"])
            (directory / f"query-{page:02}.json").write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
            batch = response.get("announcements") or []
            if any(row["secCode"] != code for row in batch):
                raise ValueError("Company query returned a different security")
            rows.extend(batch)
            if page * 30 >= response["totalAnnouncement"]:
                break
            if not batch or page >= 50:
                raise ValueError("Incomplete company pagination")
            page += 1
        candidates = sorted({row["announcementId"]: row for row in rows if followup_candidate(row)
            and row["announcementId"] != initial["announcementId"]}.values(),
            key=lambda r: (r["adjunctUrl"].split("/")[1], str(r["announcementId"])))[:4]
        selected = [initial] + candidates
        for row in selected:
            url = "https://static.cninfo.com.cn/" + row["adjunctUrl"]
            with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response:
                content = response.read()
            if not content.startswith(b"%PDF"):
                raise ValueError("Source download is not a PDF")
            path = directory / (row["announcementId"] + ".pdf")
            path.write_bytes(content)
            result["documents"].append({"id": "CNINFO_" + row["announcementId"],
                "title": clean(row["announcementTitle"]), "disclosure_date": row["adjunctUrl"].split("/")[1],
                "source_url": url, "pdf": str(path.relative_to(out)), "pdf_sha256": sha256(path),
                "official_metadata": row, "role": "initial_candidate" if row is initial else "followup_candidate"})
            time.sleep(.15)
        result["download_status"] = "complete" if len(result["documents"]) == 5 else "partial_coverage"
    except Exception as exc:
        result["download_status"] = "failed_or_partial"
        result["errors"].append(type(exc).__name__)
    (directory / "candidate.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(code, split, len(result["documents"]), result["download_status"], flush=True)
    return result


def extract(out):
    if (out / "corpus.jsonl").exists() or (out / "review-forms.jsonl").exists():
        raise ValueError("Refuse to overwrite an extracted corpus or review forms")
    from pypdf import PdfReader
    candidates = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    docs, failures = [], []
    for candidate in candidates:
        for row in candidate["documents"]:
            try:
                path = out / row["pdf"]
                if sha256(path) != row["pdf_sha256"]:
                    raise ValueError("PDF hash mismatch")
                reader = PdfReader(path)
                text = "\n\n".join(f"[Page {index + 1}]\n" + (page.extract_text() or "") for index, page in enumerate(reader.pages))
                if len(clean(text)) < 100 or text.count("\ufffd") > 3:
                    raise ValueError("Extracted source requires OCR or encoding review")
                target = path.with_suffix(".txt")
                target.write_text(text, encoding="utf-8")
                docs.append({**row, "stock_code": candidate["stock_code"], "candidate_id": candidate["id"],
                    "company": candidate["company"], "split": candidate["split"], "pages": len(reader.pages),
                    "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "event_identity_status": candidate["event_identity_status"], "review_status": "unreviewed"})
            except Exception as exc:
                failures.append({"id": row["id"], "error": type(exc).__name__})
    write_jsonl(out / "corpus.jsonl", docs)
    form = [{"id": row["id"], "stock_code": row["stock_code"], "split": row["split"],
             "text_sha256": row["text_sha256"], "review_status": "unreviewed", "reviewer": "",
             "same_scheme_as_initial": None, "original_approval_in_2024": None,
             "repurchase_stage": None, "cancellation_stage": None, "evidence_spans": [], "notes": ""} for row in docs]
    write_jsonl(out / "review-forms.jsonl", form)
    summary = {"candidate_companies": len(candidates), "downloaded_pdfs": sum(len(c["documents"]) for c in candidates),
        "extracted_documents": len(docs), "pages": sum(d["pages"] for d in docs),
        "unique_pdf_hashes": len({d["pdf_sha256"] for d in docs}), "unique_text_hashes": len({d["text_sha256"] for d in docs}),
        "splits": {split: {"companies": len({d["stock_code"] for d in docs if d["split"] == split}),
                            "documents": sum(d["split"] == split for d in docs)} for split in ("development", "test_reserved")},
        "extraction_failures": failures, "verified_independent_chains": 0, "reviewed_documents": 0,
        "model_calls": 0, "status": "candidate_corpus_not_evaluation_ready", "created_at": now()}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--extract-only", action="store_true")
    parser.add_argument("--observed-search-pool", action="store_true",
                        help="Allow an explicitly non-exhaustive snapshot when official pagination overlaps")
    args = parser.parse_args()
    if args.extract_only:
        extract(args.out)
        return
    if args.out.exists():
        parser.error("Use a new collection directory")
    args.out.mkdir(parents=True)
    protocol = manifest([], task="multi_company_candidate_collection_v1", target_companies=40,
        target_documents_per_company=5, seed=SEED, excluded_known_companies=sorted(EXCLUDED),
        selection="first eligible 2024 report per company, sort companies by sha256(seed:code), take first 40",
        split="first 10 ranked companies development; remaining 30 test_reserved",
        followups="first four title-filtered progress/result filings through 2025-03-31; identity NOT assumed",
        universe="paginated CNINFO repurchase-report search snapshot for calendar 2024",
        allow_nonexhaustive_observed_pool=args.observed_search_pool,
        full_source_identity_review_required=True, model_calls=0,
        replacement_policy="no replacement after inference; retain missing/ambiguous candidates in audit")
    (args.out / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    raw = args.out / "queries"
    raw.mkdir()
    first = query(1, "回购报告书", "2024-01-01~2024-12-31")
    pages = math.ceil(first["totalAnnouncement"] / 30)
    if pages > 150:
        raise ValueError("Unexpectedly large source response; inspect before proceeding")
    (raw / "page-001.json").write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    def fetch(page):
        value = query(page, "回购报告书", "2024-01-01~2024-12-31")
        (raw / f"page-{page:03}.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return value
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = [first] + list(pool.map(fetch, range(2, pages + 1)))
    rows = [row for response in responses for row in response.get("announcements") or []]
    if len(rows) < first["totalAnnouncement"]:
        raise ValueError("Incomplete universe; do not rank a truncated pool")
    if len({row["announcementId"] for row in rows}) < max(response["totalAnnouncement"] for response in responses):
        if not args.observed_search_pool:
            raise ValueError("Overlapping official pages: exhaustive coverage not established; inspect saved query snapshots")
        deviation = {"type": "official_search_pagination_overlap", "retrieved_rows": len(rows),
            "unique_announcement_ids": len({row["announcementId"] for row in rows}),
            "reported_totals": sorted({response["totalAnnouncement"] for response in responses}),
            "exhaustive_universe_verified": False, "selection_scope": "frozen_observed_search_pool"}
        (args.out / "collection-deviations.json").write_text(json.dumps(deviation, indent=2), encoding="utf-8")
    selected = select_companies(rows)
    if len(selected) < 40:
        raise ValueError("Insufficient unique candidate companies")
    (args.out / "selected-companies.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Frozen selection:", len(selected), "companies from", len(rows), "metadata rows", flush=True)
    work = [(row, args.out, "development" if index < 10 else "test_reserved") for index, row in enumerate(selected)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        candidates = list(pool.map(lambda values: collect_chain(*values), work))
    (args.out / "candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Collected", len(candidates), "candidates; PDFs", sum(len(c["documents"]) for c in candidates), flush=True)


if __name__ == "__main__":
    main()
