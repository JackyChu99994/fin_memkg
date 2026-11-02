"""Fill three development-chain gaps using already archived official metadata."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
GAPS = [("600703", "2023-12-15", "1218619830", "CNINFO_1219054168"),
        ("300415", "2023-11-18", "1218368029", "CNINFO_1220950049"),
        ("688353", "2024-10-15", "1221382712", "CNINFO_1222880154")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new supplement version")
    from pypdf import PdfReader
    base = ROOT / "modules/l0l4-memory/data/experiments/diverse-announcements-20261031"
    corpus = [json.loads(line) for line in (base / "corpus-split-v2.jsonl").read_text(encoding="utf-8").splitlines()]
    docs = {d["id"]: d for d in corpus}
    args.out.mkdir(parents=True)
    added = []
    for code, day, ident, anchor_id in GAPS:
        anchor = docs[anchor_id]
        assert anchor["split_candidate"] == "development" and "CNINFO_" + ident not in docs
        metadata = {str(r["announcementId"]): r for path in (base / "companies" / code / "queries").glob("*.json")
                    for r in json.loads(path.read_text(encoding="utf-8")).get("announcements", [])}
        row = metadata[ident]
        assert row["secCode"] == code and day in row["adjunctUrl"]
        url = "https://static.cninfo.com.cn/" + row["adjunctUrl"]
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=35) as response:
            data = response.read()
        assert data.startswith(b"%PDF")
        path = args.out / (ident + ".pdf")
        path.write_bytes(data)
        reader = PdfReader(path)
        text = "\n\n".join(f"[Page {i+1}]\n" + (page.extract_text() or "") for i, page in enumerate(reader.pages))
        assert len(text) > 100 and text.count("\ufffd") <= 3
        path.with_suffix(".txt").write_text(text, encoding="utf-8")
        added.append({"id": "CNINFO_" + ident, "stock_code": code, "company": anchor["company"],
            "title": row["announcementTitle"].replace("<em>", "").replace("</em>", ""),
            "disclosure_date": day, "source_url": url, "pdf": path.name, "pdf_sha256": hashlib.sha256(data).hexdigest(),
            "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "pages": len(reader.pages),
            "official_metadata": row, "split_candidate": "development", "split_version": 2,
            "role": "first_purchase_source_gap_supplement", "cited_by_anchor": anchor_id,
            "review_status": "unreviewed", "scheme_identity_verified": False})
    (args.out / "corpus.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in added), encoding="utf-8")
    summary = {"supplemental_documents": len(added), "pages": sum(r["pages"] for r in added),
        "development_only": True, "old_corpus_unchanged": True, "model_calls": 0, "human_reviewed": 0,
        "selection_reason": "First-purchase source explicitly cited by development anchor; nearest-date acquisition had selected a different scheme"}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
