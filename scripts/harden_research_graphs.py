"""Publish a separately versioned admission view; preserve frozen study outputs."""
from pathlib import Path
import json
import sys
import importlib.util

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research_kg import ResearchKG
spec=importlib.util.spec_from_file_location("fact_admission",ROOT/"modules/l0l4-memory/factual_memory.py")
rules=importlib.util.module_from_spec(spec);spec.loader.exec_module(rules)


def main():
    study=ROOT/"modules/l0l4-memory/data/experiments/expanded-study-20261031"
    out=study/"deployment-graphs-v2"
    if out.exists():raise ValueError("Deployment version already exists")
    out.mkdir();quarantined=[]
    for path in sorted((study/"groups").glob("*/graph.json")):
        kg=ResearchKG.load(path);observations=[]
        for index,row in enumerate(kg.observations):
            row=dict(row)
            if row["dimension"]=="repurchase_stage" and row["state"]=="STARTED" and not rules.supports_started(row["evidence_quote"]):
                row["admission_status"]="quarantined"
                row["admission_reason"]="actual_purchase_not_supported_by_quoted_span"
                quarantined.append({"group":path.parent.name,"source_ids":row["evidence_ids"],"quote":row["evidence_quote"]})
            observations.append(row)
        directory=out/path.parent.name;directory.mkdir()
        ResearchKG(kg.company,kg.event_key,list(kg.documents.values()),observations).dump(directory/"graph.json",
            {"origin":"separate deployment hardening; original frozen study preserved","quarantine_is_not_human_adjudication":True})
    (out/"admission-audit.json").write_text(json.dumps(quarantined,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"graphs":len(list(out.glob('*/graph.json'))),"quarantined_observations":len(quarantined),"additional_api_calls":0}))


if __name__=="__main__":main()
