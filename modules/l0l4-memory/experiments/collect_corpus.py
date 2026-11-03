"""Collect attributable news and create empty human annotation forms."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from experiments.common import now, write_jsonl


def collect(codes, per_code):
    import akshare as ak
    rows, failures, seen, seen_urls, overflow = [], [], set(), set(), []
    for code in codes:
        try:
            frame = ak.stock_news_em(symbol=code)
            kept = 0
            # The provider's search results are not guaranteed to be chronological.
            items = sorted(frame.to_dict("records"), key=lambda item: str(item.get("发布时间", "")), reverse=True)
            for item in items:
                title, content = str(item.get("新闻标题", "")).strip(), str(item.get("新闻内容", "")).strip()
                url, date = str(item.get("新闻链接", "")).strip(), str(item.get("发布时间", "")).strip()
                if not url.startswith(("https://", "http://")) or not date or not content:
                    continue
                text = title + "\n" + content
                digest = hashlib.sha256(text.encode()).hexdigest()
                if digest in seen or url in seen_urls:
                    continue
                seen.add(digest)
                seen_urls.add(url)
                record = {"id": "NEWS_" + digest[:16], "stock_code": code, "published_at": date,
                    "title": title, "text": text, "source_url": url,
                    "source_name": str(item.get("文章来源", "")), "retrieved_at": now(),
                    "provenance": "live_eastmoney_news_via_akshare", "text_sha256": digest,
                    "text_scope": "provider_search_excerpt_not_verified_full_article"}
                (rows if kept < per_code else overflow).append(record)
                kept += 1
        except Exception as exc:
            failures.append({"code": code, "error": type(exc).__name__})
    target = len(codes) * per_code
    rows.extend(sorted(overflow, key=lambda row: (row["published_at"], row["id"]), reverse=True)[:max(0, target - len(rows))])
    if len(rows) < target:
        failures.append({"error": "insufficient_unique_news", "target": target, "collected": len(rows)})
    return rows, failures


def annotation_forms(rows):
    return [{"id": row["id"], "text_sha256": hashlib.sha256(row["text"].encode()).hexdigest(),
             "review_status": "unreviewed", "reviewer": "", "events": [], "notes": ""} for row in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codes", nargs="+", default=["300750", "002594", "300308", "300502", "002466"])
    parser.add_argument("--per-code", type=int, default=8)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.per_code < 1:
        parser.error("--per-code must be positive")
    args.out.mkdir(parents=True, exist_ok=False)
    rows, failures = collect(args.codes, args.per_code)
    write_jsonl(args.out / "corpus.jsonl", rows)
    write_jsonl(args.out / "annotations.jsonl", annotation_forms(rows))
    write_jsonl(args.out / "collection_failures.jsonl", failures)
    print(f"Collected {len(rows)} unique documents; {len(failures)} source/coverage failures. Labels await human review.")
    return 0 if len(rows) == len(args.codes) * args.per_code else 2


if __name__ == "__main__":
    raise SystemExit(main())
