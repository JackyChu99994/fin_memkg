"""Read-only chronological source-graph query for the UI and generic Agent tool."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research_kg import ResearchKG


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scheme",required=True)
    parser.add_argument("--as-of",required=True)
    parser.add_argument("--dimension",default="repurchase_stage")
    args=parser.parse_args()
    if not args.scheme.startswith("CANDIDATE_") or not args.scheme[10:].isdigit():parser.error("Use a candidate scheme identifier")
    base=ROOT/"modules/l0l4-memory/data/experiments"
    study=base/"expanded-study-20261031"
    directory=next(study/name for name in ("deployment-graphs-v2","deployment-graphs","groups") if (study/name).exists())
    graph=directory/args.scheme/"graph.json"
    hashes={r["id"]:r["text_sha256"] for r in (json.loads(line) for line in (base/"lifecycle-expanded40-20261030/corpus.jsonl").read_text(encoding="utf-8").splitlines())}
    kg=ResearchKG.load(graph,expected_hashes=hashes)
    cutoff=args.as_of if "T" in args.as_of else args.as_of+"T23:59:59+08:00"
    print(json.dumps({"company":kg.company,"scheme":kg.event_key,"as_of":cutoff,
        "results":kg.query(cutoff,args.dimension),"origin":"machine-extracted quotations; source hashes checked",
        "network_calls":0,"history_preserved":True},ensure_ascii=True))


if __name__=="__main__":main()
