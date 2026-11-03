"""Prepare unlabelled real-source episodes for independent human adjudication."""
import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from experiments.common import read_jsonl, write_jsonl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new episode file")
    groups = defaultdict(list)
    for doc in read_jsonl(args.corpus):
        # Provider dates are Shanghai local time. Preserve that explicitly.
        stamp = datetime.fromisoformat(doc["published_at"])
        if stamp.tzinfo is None:
            from zoneinfo import ZoneInfo
            stamp = stamp.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        groups[doc["stock_code"]].append({"id": doc["id"], "text": doc["text"],
            "published_at": stamp.isoformat(), "source_url": doc["source_url"],
            "stock_code": doc["stock_code"]})
    episodes = []
    for code, documents in sorted(groups.items()):
        documents.sort(key=lambda doc: (doc["published_at"], doc["id"]))
        episodes.append({"id": f"NEWS_EP_{code}", "stock_code": code,
            "scenario": "current_evidence_pending_adjudication",
            "query": f"Using only these documents, what is the current investment-thesis implication for stock {code}? Distinguish announcements from price and fund-flow summaries.",
            "as_of": documents[-1]["published_at"], "documents": documents,
            "review_status": "unreviewed", "reviewer": "",
            "provenance": "real_provider_excerpts; not independently verified",
            "gold": {"direction": None, "evidence_ids": []},
            "review_notes": "Assign a defensible current-evidence label and supporting IDs independently. Reject this episode if excerpts do not support an answer. These groups do not guarantee contradiction cases."})
    write_jsonl(args.out, episodes)
    print(f"Prepared {len(episodes)} real-source episode drafts. Gold answers are intentionally unset.")


if __name__ == "__main__":
    main()
