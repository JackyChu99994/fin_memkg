"""Produce a portable source-grounded annotation review packet."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from experiments.common import read_jsonl, reviewed_labels


def render(corpus, annotations, output):
    labels = reviewed_labels(corpus, annotations, allow_draft=True)
    parts, markdown = [], ["# 40 条新闻初标审阅稿", "", "标注来源：AI逐条初标，等待用户复核。空事件有逐条排除理由，不代表漏标。", ""]
    for index, doc in enumerate(corpus, 1):
        label = labels[doc["id"]]
        event_rows = []
        for event in label["events"]:
            triple = f"{event['source']} — {event['relation']} → {event['target']}"
            quotes = "".join(f"<blockquote>{html.escape(span)}</blockquote>" for span in event.get("evidence_spans", []))
            event_rows.append(f"<li><strong>{html.escape(triple)}</strong><p>{html.escape(event.get('status', '发酵中'))} · {html.escape(event.get('event_phase', 'reported'))}</p>{quotes}</li>")
        events = "<ol>" + "".join(event_rows) + "</ol>" if event_rows else "<p class='empty'>不抽取关系：见本条说明。</p>"
        ambiguity = "需要重点复核" if label.get("needs_adjudication") else "常规复核"
        parts.append(f"""<article data-ambiguous="{str(bool(label.get('needs_adjudication'))).lower()}">
<h2>{index:02d} {html.escape(doc.get('title', doc['id']))}</h2>
<p class="meta">{html.escape(doc['id'])} · {html.escape(doc['published_at'])} · {ambiguity}</p>
<a href="{html.escape(doc['source_url'], quote=True)}" target="_blank" rel="noopener">打开来源</a>
<h3>冻结输入</h3><pre>{html.escape(doc['text'])}</pre>
<h3>初标关系</h3>{events}<h3>标注说明</h3><p>{html.escape(label.get('notes', ''))}</p>
<p class="meta">分类：{html.escape(label.get('category', ''))}；事件簇：{html.escape(label.get('event_group', doc['id']))}</p>
<label class="confirm"><input type="checkbox" data-id="{html.escape(doc['id'], quote=True)}"> 我已检查此条，并接受当前标签（如需修改，请先在标注页面修改后重新生成审阅稿）</label>
</article>""")
        markdown += [f"## {index:02d} {doc.get('title', doc['id'])}", "", f"编号：{doc['id']}；{ambiguity}", "", doc["text"], "", f"[来源]({doc['source_url']})", ""]
        if label["events"]:
            for event in label["events"]:
                markdown.append(f"- {event['source']} / {event['relation']} / {event['target']}（{event['status']}；{event.get('event_phase', 'reported')}）")
                markdown.extend(f"  - 证据：{span}" for span in event.get("evidence_spans", []))
        else:
            markdown.append("- 初标：不抽取关系。")
        markdown += ["", "说明：" + label.get("notes", ""), ""]
    data = json.dumps(annotations, ensure_ascii=False).replace("<", "\\u003c")
    template = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fin-MemKG 新闻标注审阅稿</title><style>
body{margin:0;background:#f5f5f2;color:#19303b;font:17px/1.7 system-ui,'Microsoft YaHei',sans-serif}main{max-width:1050px;margin:40px auto;padding:0 24px}h1{font-size:32px}h2{font-size:23px}h3{font-size:18px}article{background:white;padding:28px;margin:24px 0;border:1px solid #dce2df;border-radius:8px}pre{white-space:pre-wrap;font:inherit;background:#f6f8f7;padding:18px}.meta{color:#59706e;font-size:14px}blockquote{margin:12px 0;padding:8px 16px;border-left:3px solid #528c7f;background:#f3f8f5}.empty{color:#59676d}.confirm{display:block;border-top:1px solid #ddd;padding-top:16px}button,input[type=text]{padding:10px 14px;font:inherit}button{cursor:pointer}header{position:sticky;top:0;background:#edf3ef;padding:14px;border-bottom:1px solid #b8c9c2}label{cursor:pointer}@media print{header,.confirm{display:none}article{break-inside:avoid}}</style>
<header>复核人：<input id="reviewer" type="text" placeholder="姓名或组内编号"> <button id="download">导出已检查标注</button> <span id="count">0 条已检查</span></header>
<main><h1>40 条新闻初标审阅稿</h1><p>所有条目已由 AI 逐条初标。请检查证据、关系极性和事件粒度；这份初稿尚不属于已完成人工复核的金标准。24 条空事件均有理由，10 条被标记为需要重点复核。输入为标题和服务商摘要，不是核验后的全文。</p>__ARTICLES__</main>
<script id="labels" type="application/json">__DATA__</script><script>
const checks=[...document.querySelectorAll('input[data-id]')];
checks.forEach(c=>c.addEventListener('change',()=>document.getElementById('count').textContent=checks.filter(x=>x.checked).length+' 条已检查'));
document.getElementById('download').addEventListener('click',()=>{const reviewer=document.getElementById('reviewer').value.trim();if(!reviewer){alert('请填写复核人。');return;}
const accepted=new Set(checks.filter(x=>x.checked).map(x=>x.dataset.id));if(!accepted.size){alert('请先检查并勾选具体条目。');return;}
const labels=JSON.parse(document.getElementById('labels').textContent);labels.forEach(r=>{if(accepted.has(r.id)){r.review_status='reviewed';r.reviewer=reviewer;r.reviewed_at=new Date().toISOString();r.review_method='AI_initial_labels_checked_by_user';}});
const blob=new Blob([labels.map(r=>JSON.stringify(r)).join('\\n')+'\\n'],{type:'application/x-ndjson;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='annotations-user-reviewed.jsonl';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);});
</script></html>"""
    output = Path(output)
    output.write_text(template.replace("__ARTICLES__", "".join(parts)).replace("__DATA__", data), encoding="utf-8")
    output.with_suffix(".md").write_text("\n".join(markdown), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new review-packet filename")
    render(read_jsonl(args.corpus), read_jsonl(args.labels), args.out)
    print(args.out)


if __name__ == "__main__":
    main()
