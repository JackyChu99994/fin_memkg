"""Read-only development source/scheme catalogue in the original workbench."""
from datetime import date, timedelta
import html
import json
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network
from repurchase_catalogue import build_catalogue


def render_scheme_catalogue(root: Path):
    st.subheader("Development scheme links")
    st.caption("Source-bound candidates from development documents. No model call, reference answer, or graph write occurs on this page.")
    path = root / "modules/l0l4-memory/data/experiments/development-identity-audit-v3-20261101/development-source-corpus.jsonl"
    if not path.exists():
        st.info("The development source delivery is not present. No sample facts are substituted.")
        return
    documents = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(d.get("split_candidate") != "development" for d in documents):
        st.warning("This view accepts development sources only.")
        return
    codes = sorted({d["stock_code"] for d in documents})
    names = {d["stock_code"]: d.get("company", d["stock_code"]) for d in documents}
    code = st.selectbox("Development company", codes, format_func=lambda c: names[c] + " (" + c + ")", key="scheme_company")
    selected = [d for d in documents if d["stock_code"] == code]
    latest = max(date.fromisoformat(d["disclosure_date"]) for d in selected) + timedelta(days=1)
    cutoff_day = st.date_input("Catalogue available by", value=latest, key="scheme_cutoff")
    cutoff = cutoff_day.isoformat() + "T23:59:59+08:00"
    try:
        catalogue = build_catalogue(selected, cutoff)
    except ValueError:
        st.warning("Source integrity or date checks failed; candidate facts are not displayed.")
        return
    st.warning("These are machine-derived scheme candidates, not certified unique events or human-verified facts. Same-company/same-date documents are not automatically merged.")
    st.caption("Only sources available by this cutoff can create candidates or alias links. Date-only announcements become available on the following calendar day.")
    schemes = catalogue["schemes"]
    if not schemes:
        st.info("No source-bound candidate can be established at this cutoff; this does not establish absence of a real scheme.")
    else:
        st.dataframe([{"candidate_id": s["scheme_id"], "board_date_candidate": s["board_date_candidate"],
                       "anchor_sources": ", ".join(s["anchor_sources"])} for s in schemes], hide_index=True)
    net = Network(height="480px", width="100%", directed=True, cdn_resources="in_line")
    net.add_node("company", label=names[code], color="#334e68")
    for scheme in schemes:
        net.add_node(scheme["scheme_id"], label=scheme["board_date_candidate"], title=scheme["scheme_id"], color="#8fb9aa")
        net.add_edge("company", scheme["scheme_id"], label="CANDIDATE_SCHEME")
    for source in catalogue["sources"]:
        net.add_node(source["id"], label=source["id"], title=html.escape(source["title"]), color="#cad9e8")
    for link in catalogue["links"]:
        net.add_edge(link["scheme_id"], link["source_id"], title=link["relation"],
                     label="ANCHORED_BY" if link["relation"] == "ANCHORS_CANDIDATE" else "MENTION_CANDIDATE")
    components.html(net.generate_html(), height=500, scrolling=True)
    source_map = {d["id"]: d for d in selected}
    for scheme in schemes:
        with st.expander(scheme["scheme_id"] + " | source evidence"):
            for proof in scheme["proofs"]:
                st.write(proof["quote"])
                st.link_button("Original " + proof["source_id"], source_map[proof["source_id"]]["source_url"])
            st.caption("Matching a date and source text is an identity lead, not proof that all follow-up announcements belong to this scheme.")
    with st.expander("Unresolved documents and candidate aliases"):
        st.json({"unresolved_primaries": catalogue["unresolved_primaries"], "alias_proofs": catalogue["alias_proofs"]})
    st.download_button("Download source-bound candidate catalogue", json.dumps(catalogue, ensure_ascii=False, indent=2),
                       file_name=code + "-candidate-catalogue.json", key="scheme_download")
