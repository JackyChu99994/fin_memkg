"""Generate explicitly synthetic fixtures for debugging, never empirical evidence."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from experiments.collect_corpus import annotation_forms
from experiments.common import write_jsonl


def datasets():
    # Chinese entity and relation strings preserve the existing module's schema.
    examples = [
        ("宁德时代与特斯拉签订新电池供应合同。", "宁德时代", "特斯拉", "利好事件", "公司"),
        ("宁德时代宣布终止与特斯拉的电池供应合同。", "宁德时代", "特斯拉", "利空事件", "公司"),
        ("宁德时代成功注册一枚商标。", None, None, None, None),
        ("宁德时代今天股价上涨3%，成交额突破100亿元。", None, None, None, None),
        ("比亚迪与特斯拉签订合作协议。", "比亚迪", "特斯拉", "利好事件", "公司"),
        ("比亚迪宣布终止与特斯拉的合作协议。", "比亚迪", "特斯拉", "利空事件", "公司"),
        ("中际旭创与英伟达签订光模块供货合同。", "中际旭创", "英伟达", "利好事件", "公司"),
        ("中际旭创宣布终止与英伟达的光模块供货合同。", "中际旭创", "英伟达", "利空事件", "公司"),
    ]
    corpus = [{"id": f"SYN_{i:02d}", "text": text, "published_at": "2026-10-01T09:00:00+08:00",
               "provenance": "synthetic_development_fixture", "source_url": None}
              for i, (text, *_) in enumerate(examples, 1)]
    labels = annotation_forms(corpus)
    for label, (_, source, target, relation, ttype) in zip(labels, examples):
        label["events"] = [] if source is None else [{"source": source, "target": target, "relation": relation,
            "source_type": "公司", "target_type": ttype, "status": "发酵中"}]
        label["notes"] = "Author-created synthetic reference; not a reviewed real-news label."
    episodes = []
    for index, (company, partner) in enumerate((("宁德时代", "特斯拉"), ("比亚迪", "特斯拉"), ("中际旭创", "英伟达")), 1):
        for reverse in (True, False):
            suffix = "reversal" if reverse else "confirmation"
            docs = [{"id": "d1", "text": f"{company}与{partner}签订供货合同。", "published_at": "2026-10-01T09:00:00+08:00"},
                {"id": "d2", "text": f"{company}宣布{'终止' if reverse else '扩大'}与{partner}的供货合同。", "published_at": "2026-10-02T09:00:00+08:00"},
                {"id": "future", "text": f"{company}未来五日股价大涨。", "published_at": "2026-10-03T09:00:00+08:00"}]
            # More than top-k inputs are needed to distinguish full-text and RAG.
            docs += [{"id": f"noise_{i}", "text": f"无关公司{i}发布商标注册公告。", "published_at": "2026-10-01T10:00:00+08:00"} for i in range(5)]
            episodes.append({"id": f"SYN_EP_{index}_{suffix}", "scenario": suffix,
                "query": f"截至基准时点，{company}与{partner}的供货合同对当前投资逻辑是利好还是利空？",
                "as_of": "2026-10-02T12:00:00+08:00", "documents": docs,
                "provenance": "synthetic_development_fixture", "review_status": "unreviewed", "reviewer": "",
                "gold": {"direction": "BEARISH" if reverse else "BULLISH", "evidence_ids": ["d2"]}})
    return corpus, labels, episodes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    corpus, labels, episodes = datasets()
    write_jsonl(args.out / "corpus.jsonl", corpus)
    write_jsonl(args.out / "annotations.jsonl", labels)
    write_jsonl(args.out / "episodes.jsonl", episodes)
    print("Created 8 synthetic extraction cases and 6 synthetic memory episodes. Development use only.")


if __name__ == "__main__":
    main()
