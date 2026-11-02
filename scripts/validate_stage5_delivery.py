"""Validate the saved study and deployment graphs without network or model calls."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research_kg import ResearchKG


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    base = ROOT / "modules/l0l4-memory/data/experiments"
    corpus_dir = base / "lifecycle-expanded40-20261030"
    corpus = rows(corpus_dir / "corpus.jsonl")
    hashes = {}
    for doc in corpus:
        digest = hashlib.sha256(doc["text"].encode()).hexdigest()
        assert digest == doc["text_sha256"], doc["id"]
        pdf = corpus_dir / Path(doc["pdf"].replace("\\", "/"))
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == doc["pdf_sha256"], doc["id"]
        hashes[doc["id"]] = digest
    study = base / "expanded-study-20261031"
    records = rows(study / "records.jsonl")
    corrected = rows(study / "corrected-reference-scores/records.jsonl")
    assert len(corpus) == 196 and len(records) == len(corrected) == 385
    for old, new in zip(records, corrected):
        for field in ("id", "prompt", "raw", "prediction", "usage"):
            assert old[field] == new[field], (old["id"], field)
        prompt = json.loads(old["prompt"])
        assert not {"gold", "reference_proof", "reference_origin"} & prompt.keys()
        for doc in prompt["evidence"]["documents"]:
            assert doc["published_at"] <= old["as_of"], old["id"]
    graph_paths = sorted((study / "deployment-graphs-v2").glob("*/graph.json"))
    assert len(graph_paths) == 39
    quarantined = 0
    for path in graph_paths:
        kg = ResearchKG.load(path, expected_hashes=hashes)
        quarantined += sum(r.get("admission_status") == "quarantined" for r in kg.observations)
        for row in kg.query("2099-01-01T00:00:00+08:00"):
            assert row["sources"] and row["paths"]
    assert quarantined == 5
    summary = json.loads((study / "summary.json").read_text(encoding="utf-8"))
    assert summary["physical_calls"] == 556 and summary["provider_failed_calls"] == 0
    print(json.dumps({"status": "passed", "documents": len(corpus), "saved_answers": len(records),
                      "hash_checked_graphs": len(graph_paths), "quarantined_observations": quarantined,
                      "rescoring_preserves_model_outputs": True, "network_calls": 0,
                      "reference_tier": "source_anchored_silver_not_human_gold"}, indent=2))


if __name__ == "__main__":
    main()
