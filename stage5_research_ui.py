"""Read-only real-source event KG projection in the original workbench."""
from pathlib import Path
import json
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network
from research_kg import ResearchKG

ROOT=Path(__file__).resolve().parent
STUDY=ROOT/"modules/l0l4-memory/data/experiments/expanded-study-20261031"


def render_research():
    from stage5_scheme_ui import render_scheme_catalogue
    historical, development = st.tabs(["Historical study", "Development scheme links"])
    with historical:
        _render_historical_research()
    with development:
        render_scheme_catalogue(ROOT)


def _render_historical_research():
    st.header("Source-linked event research")
    st.caption("Machine-extracted observations with checked quotations. This page performs read-only graph queries; it makes no API calls or trading predictions.")
    base=next((STUDY/name for name in ("deployment-graphs-v2","deployment-graphs","groups") if (STUDY/name).exists()),STUDY/"groups")
    files=sorted(base.glob("*/graph.json"))
    if not files:
        st.info("Prepare the expanded study artifacts first. No simulated facts are substituted.")
        return
    selected=st.selectbox("Company scheme",files,format_func=lambda p:p.parent.name)
    corpus=ROOT/"modules/l0l4-memory/data/experiments/lifecycle-expanded40-20261030/corpus.jsonl"
    hashes=None
    if corpus.exists():
        hashes={r["id"]:r["text_sha256"] for r in (json.loads(line) for line in corpus.read_text(encoding="utf-8").splitlines() if line.strip())}
    try:kg=ResearchKG.load(selected,expected_hashes=hashes)
    except (ValueError,OSError):
        st.warning("This artifact is not yet complete. Select another scheme or refresh later.")
        return
    last=max(d["published_at"] for d in kg.documents.values())
    day=st.date_input("Evidence available by",value=__import__('datetime').date.fromisoformat(last[:10]))
    cutoff=day.isoformat()+"T23:59:59+08:00"
    st.subheader(kg.company)
    st.write(kg.event_key)
    st.caption("Date-only announcements are admitted on the following calendar day. This is a conservative availability policy, not an exact first-release timestamp.")
    results=kg.query(cutoff)
    if not results:st.info("No admitted observation is available at this cutoff. This does not prove that no real-world event occurred.")
    st.dataframe([{k:row[k] for k in ("dimension","state","available_at")} for row in results],hide_index=True)
    colors={"COMPANY":"#243b53","SCHEME":"#486581","SOURCE":"#c5d8e8","OBSERVATION":"#76b5a5"}
    net=Network(height="510px",width="100%",directed=True,cdn_resources="in_line")
    allowed={"company","scheme"}
    for ident,attrs in kg.graph.nodes(data=True):
        if attrs.get("available_at","")<=cutoff:allowed.add(ident)
    for ident,attrs in kg.graph.nodes(data=True):
        if ident in allowed:net.add_node(ident,label=attrs["label"][:70],title=attrs.get("evidence_quote",attrs["label"]),color=colors[attrs["kind"]])
    for a,b,attrs in kg.graph.edges(data=True):
        if a in allowed and b in allowed:net.add_edge(a,b,title=attrs["relation"],label=attrs["relation"])
    components.html(net.generate_html(),height=530,scrolling=True)
    for result in results:
        with st.expander(result["dimension"]+": "+result["state"]):
            st.write(result["quote"])
            for source in result["sources"]:st.link_button("Original filing "+source["id"],source["url"])
            st.json({"graph_paths":result["paths"]})
    payload=json.loads(selected.read_text(encoding="utf-8"))
    st.download_button("Download auditable graph",json.dumps(payload,ensure_ascii=False,indent=2),file_name=selected.parent.name+".json")
    with st.expander("Admission and interpretation limits"):
        st.json(payload.get("metadata",{}))
        st.write("A quotation match does not prove semantic entailment. SUPERSEDES_CURRENT_VIEW selects the latest disclosed state without declaring earlier historical facts false.")
