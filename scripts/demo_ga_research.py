"""Actual generic-Agent integration smoke with a strict source-query contract.

Requires --live for paid model calls. Natural-language embellishments are never
accepted as verified KG facts. This is one integration check, not a benchmark.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ga_core.llm import load_config,OpenAICompatibleClient
from ga_core.handler import AgentHandler
from ga_core.loop import AgentLoop
from ga_core.tools import TOOLS_SCHEMA
from research_kg import ResearchKG


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live",action="store_true");parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    if not args.live:parser.error("Use the read-only query script without --live; explicit flag required for this model smoke")
    if args.out.exists():parser.error("New output directory required")
    args.out.mkdir(parents=True)
    config=load_config();config.temperature=0;config.max_tokens=1000
    base=OpenAICompatibleClient(config);calls=[]
    class Recorder:
        def chat(self,messages,tools=None):
            response=base.chat(messages,tools)
            calls.append({"prompt_hash":hashlib.sha256(json.dumps(messages,ensure_ascii=False).encode()).hexdigest(),
                "usage":response.usage,"model":config.model,"content":response.content,
                "tool_calls":[{"name":c.name,"arguments":c.arguments} for c in response.tool_calls]})
            (args.out/"calls.json").write_text(json.dumps(calls,ensure_ascii=False,indent=2),encoding="utf-8")
            return response
    system="""You perform a single read-only local evidence query. Use only the provided code_run tool.
Do not read credentials, access networks, modify project data, or claim universal correctness or bias removal.
After inspecting the tool result, return only JSON with repurchase_stage and source_ids.
Do not invent a ThesisNode, investment thesis, or any schema not present in the tool result."""
    prompt=f"Run {ROOT/'scripts/query_research_kg.py'} using sys.executable and subprocess.run with arguments --scheme CANDIDATE_301193 --as-of 2024-07-26. Capture/print UTF-8 output. Then return the disclosed stage and supporting source IDs."
    handler=AgentHandler(workspace=args.out,verbose=False)
    loop=AgentLoop(Recorder(),handler,system,tools_schema=[t for t in TOOLS_SCHEMA if t['function']['name']=='code_run'],max_turns=3,verbose=False)
    result=loop.run(prompt)
    graph=ROOT/'modules/l0l4-memory/data/experiments/expanded-study-20261031/deployment-graphs-v2/CANDIDATE_301193/graph.json'
    actual=ResearchKG.load(graph).query('2024-07-26T23:59:59+08:00','repurchase_stage')
    try:answer=json.loads(result['content'].removeprefix('```json').removesuffix('```').strip())
    except ValueError:answer={}
    verified=bool(actual) and answer.get('repurchase_stage')==actual[0]['state'] and set(answer.get('source_ids',[]))=={s['id'] for s in actual[0]['sources']}
    record={'result':result,'verified_supported_fields':verified,'actual_graph_query':actual,'trace':handler.trace,
        'calls':len(calls),'scope':'one actual tool-use integration; not general task accuracy or automatic skill learning'}
    (args.out/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    if not verified:raise ValueError('Final model fields were not accepted as verified source facts')
    print(json.dumps({'verified_supported_fields':verified,'calls':len(calls),'result':answer},ensure_ascii=True))


if __name__=='__main__':main()
