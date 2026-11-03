"""Build a standalone review form; never promote draft labels to human gold."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    base = ROOT / "modules/l0l4-memory/data/experiments"
    source = base / "source-adjudicated-v4-20261031/episodes.jsonl"
    episodes = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    questions = []
    for row in episodes:
        eligible = [d for d in row["documents"] if d["published_at"] <= row["as_of"]]
        assert set(row["gold"]["evidence_ids"]) <= {d["id"] for d in eligible}
        questions.append({key: row[key] for key in
            ("id", "company", "stock_code", "split", "as_of", "event_key", "gold", "reference_proof")}
            | {"documents": eligible})
    assert len(questions) == 77
    payload = {"reference_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "questions": questions}
    page = HTML.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page, encoding="utf-8")
    print(json.dumps({"questions": len(questions), "initial_reviewed": 0,
                      "reference_sha256": payload["reference_sha256"], "network_calls": 0}))


HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>77题来源核对清单</title><style>
body{font:16px/1.65 system-ui,sans-serif;max-width:1080px;margin:30px auto;padding:0 20px;color:#17212b;background:#fafbfc}
header,.card{background:white;border:1px solid #ccd6df;border-radius:10px;padding:20px;margin:16px 0}
nav{display:flex;gap:12px;flex-wrap:wrap;align-items:center}button,select,input,textarea{font:inherit;padding:7px;border:1px solid #aab8c4;border-radius:5px}
button{cursor:pointer;background:#eef4fa}button:disabled{opacity:.5}textarea{width:96%;min-height:75px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.65 system-ui;max-height:520px;overflow:auto;background:#f4f6f8;padding:12px}
label{display:block;margin:12px 0}summary{cursor:pointer}small{color:#4f6070}.notice{border-left:4px solid #c58c22;padding:10px;background:#fff7e7}#message{white-space:pre-wrap}
</style><header><h1>77题来源核对清单</h1>
<p>这是待人工检查的银标准参考。核对范围仅为：截至指定可用时间，该具体回购方案已披露的执行阶段。请先阅读来源、独立判断，再展开现有参考；本页不展示任何方法的模型成绩。</p>
<p class="notice">当前样本缺少终止、更正等复杂类别；不要把“未披露实际执行”解释为现实中绝对没有交易。月内未买入不抹去此前累计买入。批准、账户开立和未来计划不等于已经买入。同日来源按次日可用规则共同考虑。</p>
<label>复核人标识（可使用项目内代号） <input id="reviewer" autocomplete="off"></label>
<nav><button id="export">导出核对记录</button><label>导入记录 <input type="file" id="import" accept=".json"></label></nav>
<p><small>本页不联网。记录自动保存在当前浏览器；更换浏览器或清理数据会丢失，务必导出JSON留档。导出的个人复核不自动等于独立双人金标准，原参考文件不会被修改。</small></p>
<p id="progress"></p><p id="message" role="status"></p></header>
<nav><button id="prev">上一题</button><select id="jump" aria-label="选择题目"></select><button id="next">下一题</button><button id="pending">跳到下一待核对题</button></nav>
<main id="question" class="card"></main>
<script>
const dataset=__PAYLOAD__;
const labels={NO_EXECUTION_DISCLOSED:'尚无实际执行披露',STARTED:'已经开始回购',COMPLETED:'实施完成'};
const storageKey='fin-memkg-review-'+dataset.reference_sha256;
let saved={reviewer:'',records:{}};let index=0;
try{const value=JSON.parse(localStorage.getItem(storageKey));if(value&&value.records)saved=value;}catch(e){}
const el=id=>document.getElementById(id);
function node(tag,text,parent){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(parent)parent.append(n);return n;}
function persist(){try{localStorage.setItem(storageKey,JSON.stringify(saved));}catch(e){el('message').textContent='浏览器保存失败，请立即导出记录。';}progress();}
function progress(){const counts={pending:0,confirmed:0,corrected:0,uncertain:0};for(const q of dataset.questions){const s=saved.records[q.id]?.decision||'pending';counts[s]=(counts[s]||0)+1;}el('progress').textContent=`共77题：待核对 ${counts.pending}；确认 ${counts.confirmed}；修改 ${counts.corrected}；存疑 ${counts.uncertain}。确认与修改必须由你实际阅读后填写。`;}
function render(){
 const q=dataset.questions[index];const r=saved.records[q.id]||{};const box=el('question');box.replaceChildren();el('jump').value=String(index);
 node('h2',`${index+1}/77 · ${q.company}（${q.stock_code}）`,box);node('p',`截止可用时间：${q.as_of}；分区：${q.split}`,box);node('p',`方案：${q.event_key}`,box);
 node('h3','先查看截至该时间可用的全部来源',box);
 for(const d of q.documents){const details=node('details',undefined,box);node('summary',`${d.id} · 可用时间 ${d.published_at}`,details);const a=node('a','打开官方原始PDF',details);a.href=d.source_url;a.target='_blank';a.rel='noopener noreferrer';node('pre',d.text,details);}
 const ref=node('details',undefined,box);node('summary','阅读来源后，展开现有银标准参考',ref);node('p',labels[q.gold.repurchase_stage],ref);node('p','指定证据：'+q.gold.evidence_ids.join('、'),ref);node('pre',q.reference_proof.source_quote,ref);node('small','判定规则：'+q.reference_proof.rule,ref);
 node('h3','填写本题复核',box);
 const decisionLabel=node('label','处理结果 ',box);const decision=node('select',undefined,decisionLabel);
 for(const [v,t] of Object.entries({pending:'待核对',confirmed:'确认现有参考',corrected:'修改参考',uncertain:'存疑，需进一步判定'})){const o=node('option',t,decision);o.value=v;}decision.value=r.decision||'pending';
 const stageLabel=node('label','你独立判定的阶段 ',box);const stage=node('select',undefined,stageLabel);const blank=node('option','请选择，不自动沿用参考',stage);blank.value='';for(const [v,t] of Object.entries(labels)){const o=node('option',t,stage);o.value=v;}stage.value=r.stage||'';
 const evidenceLabel=node('label','支持你判断的公告编号（多个用逗号分隔） ',box);const evidence=node('input',undefined,evidenceLabel);evidence.style.width='90%';evidence.value=(r.evidence_ids||[]).join(', ');
 const notesLabel=node('label','原文依据、修改原因或疑点 ',box);const notes=node('textarea',undefined,notesLabel);notes.value=r.notes||'';
 const save=node('button','保存本题',box);save.onclick=()=>{
  const ids=evidence.value.split(/[,，\s]+/).filter(Boolean);const allowed=new Set(q.documents.map(d=>d.id));
  if(decision.value!=='pending'&&!el('reviewer').value.trim()){alert('请先填写复核人标识。');return;}
  if(['confirmed','corrected'].includes(decision.value)&&(!stage.value||!ids.length)){alert('请填写独立阶段判断和来源编号。');return;}
  if(ids.some(id=>!allowed.has(id))){alert('来源编号必须属于本题截止时间前提供的来源。');return;}
  if(decision.value==='confirmed'&&stage.value!==q.gold.repurchase_stage){alert('你的阶段与参考不同，请选择修改参考或存疑。');return;}
  if(['corrected','uncertain'].includes(decision.value)&&!notes.value.trim()){alert('请留下修改理由或疑点。');return;}
  saved.reviewer=el('reviewer').value.trim();saved.records[q.id]={question_id:q.id,decision:decision.value,stage:stage.value,evidence_ids:ids,notes:notes.value.trim(),reviewer:saved.reviewer,recorded_at:new Date().toISOString(),reference_opened:ref.open};persist();el('message').textContent=`已保存第${index+1}题，请定期导出记录。`;
 };
 el('prev').disabled=index===0;el('next').disabled=index===76;progress();
}
dataset.questions.forEach((q,i)=>{const o=node('option',`${i+1} · ${q.company} · ${q.as_of.slice(0,10)}`,el('jump'));o.value=String(i);});
el('reviewer').value=saved.reviewer||'';el('reviewer').onchange=()=>{saved.reviewer=el('reviewer').value.trim();persist();};
el('prev').onclick=()=>{index--;render();};el('next').onclick=()=>{index++;render();};el('jump').onchange=()=>{index=Number(el('jump').value);render();};
el('pending').onclick=()=>{for(let offset=1;offset<=77;offset++){const i=(index+offset)%77;if(!saved.records[dataset.questions[i].id]||saved.records[dataset.questions[i].id].decision==='pending'){index=i;render();return;}}el('message').textContent='没有待核对题；存疑题仍需处理。';};
el('export').onclick=()=>{const payload={schema_version:1,reference_sha256:dataset.reference_sha256,exported_at:new Date().toISOString(),scope:'owner_self_review_not_independent_double_annotation',original_reference_unchanged:true,...saved};const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download='stage5-owner-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
el('import').onchange=async()=>{try{const value=JSON.parse(await el('import').files[0].text());if(value.reference_sha256!==dataset.reference_sha256||!value.records)throw Error('参考版本不匹配');const ids=new Set(dataset.questions.map(q=>q.id));if(Object.keys(value.records).some(id=>!ids.has(id)))throw Error('含未知题号');if(!confirm('导入将替换当前浏览器中的核对记录。继续？'))return;saved={reviewer:String(value.reviewer||''),records:value.records};el('reviewer').value=saved.reviewer;persist();render();el('message').textContent='已导入记录。';}catch(e){el('message').textContent='导入失败：'+e.message;}};
render();
</script></html>'''


if __name__ == "__main__":
    main()
