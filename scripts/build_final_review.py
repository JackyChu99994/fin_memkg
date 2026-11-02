"""Build a read-only, offline inspector for actual reserved answers and sources."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.complete_stage5_study import cohort
from scripts.extend_reserved_source_review import read_rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--analysis", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error("New output path required")
    qs, docs, _, _ = cohort("test_reserved")
    records = read_rows(a.run / "records.jsonl")
    analysis = json.loads(a.analysis.read_text(encoding="utf-8"))
    payload = {"questions": qs, "documents": docs, "records": records, "analysis": analysis}
    html = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>第五棒正式对照逐题核查</title>
<style>body{font:16px/1.65 system-ui;max-width:1200px;margin:26px auto;padding:18px;color:#182530}h1{font-size:27px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #d2dce4;padding:9px;text-align:left}th{background:#eef3f7}select{font:inherit;padding:8px;max-width:95%}section{padding:18px;border:1px solid #d2dce4;border-radius:8px;margin:18px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:13px;max-height:540px;overflow:auto;font:14px/1.6 system-ui}summary{cursor:pointer}small{color:#526270}</style>
<h1>第五棒正式对照与原文核查</h1><p>91张题卡、48家公司、六种题型，一次冻结后的真实模型研究。参考为AI银标准，22道负例使用过Qwen全文审查；没有独立人工金标准。构建失败按失败保留。此页不修改题库，也不发起任何模型调用。</p>
<p>公司聚类区间、成本、失败原因和三组时序诊断均保存在交付分析文件中。三组案例不能当成9个独立样本；引文来源覆盖不等于语义正确。</p>
<table><thead><tr><th>方法</th><th>严格正确</th><th>公司宏平均</th><th>回答输入token</th><th>冷启动输入token</th></tr></thead><tbody id="summary"></tbody></table>
<section><label>题目 <select id="question"></select></label> <label>方法 <select id="method"></select></label><div id="detail"></div></section>
<script>const dataset=PAYLOAD;
const methodNames={full_text:'全文大模型',tfidf_rag:'词法RAG',append_memory:'追加记忆',current_flat:'当前平铺记忆',graph_assisted_retrieval:'图辅助检索'};
const el=id=>document.getElementById(id);
function node(tag,text,parent){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(parent)parent.append(n);return n;}
for(const [key,r] of Object.entries(dataset.analysis.methods)){const tr=node('tr',undefined,el('summary'));for(const t of [methodNames[key],`${r.correct}/${r.n}`,`${(100*r.company_macro_accuracy).toFixed(1)}%`,r.warm_answer_input_tokens.toLocaleString(),r.cold_input_tokens.toLocaleString()])node('td',t,tr);}
for(const q of dataset.questions){const o=node('option',`${q.company} ${q.id}`,el('question'));o.value=q.id;}for(const [key,name] of Object.entries(methodNames)){const o=node('option',name,el('method'));o.value=key;}
function block(parent,title,value){const d=node('details',undefined,parent);node('summary',title,d);node('pre',typeof value==='string'?value:JSON.stringify(value,null,2),d);return d;}
function render(){const q=dataset.questions.find(q=>q.id===el('question').value),r=dataset.records.find(r=>r.question_id===q.id&&r.method===el('method').value),box=el('detail');box.replaceChildren();node('h2',q.company+' '+q.id,box);node('p',q.question,box);node('p','截止 '+q.as_of+'；状态 '+r.status+'；严格正确 '+r.score.exact_answer_correct,box);
block(box,'实际模型回答与格式校验',{response:r.result||null,issues:r.score.validation_issues,field_matches:r.score.field_matches,scheme_correct:r.score.scheme_correct,provider_usage:r.usage,extraction_failures:r.extraction_failures});
block(box,'AI银标准参考与证据（非独立人工真值）',{reference:q.reference_draft,scheme:q.target_scheme,answerability:q.reference_answerability,missing_reason:q.reference_missing_reason,origin:q.reference_origin,proofs:q.reference_proofs});
if(r.user){let actual;try{actual=JSON.parse(r.user);}catch{actual=r.user;}block(box,'模型实际收到的完整公开输入',actual);}else node('p','此槽未调用模型；构建或预算失败保留为失败。',box);
const available=node('details',undefined,box);node('summary','全部可用原文供核对（检索模型不一定收到每篇全文）',available);for(const id of q.source_ids){const d=dataset.documents[id],s=node('details',undefined,available);node('summary',d.disclosure_date+' '+d.title+' '+id,s);if(d.source_url.startsWith('https://')||d.source_url.startsWith('http://')){const a=node('a','官方PDF',s);a.href=d.source_url;a.target='_blank';a.rel='noopener noreferrer';}node('pre',d.text,s);}}
el('question').value=dataset.questions[0].id;el('method').value='full_text';el('question').onchange=render;el('method').onchange=render;render();
</script></html>'''
    page = html.replace("PAYLOAD", json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c"))
    a.out.write_text(page, encoding="utf-8")
    print(json.dumps({"questions": len(qs), "answer_slots": len(records), "sources": len(docs), "read_only": True}))


if __name__ == "__main__":
    main()
