"""Local annotation editor. Launch using streamlit run experiments/annotate.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from experiments.common import now, read_jsonl, reviewed_labels, write_jsonl

st.set_page_config(page_title="Fin-MemKG annotation", layout="wide")
st.title("News annotation and review")
st.caption("Review the complete source text. Empty events means no supported relation, not an unfinished annotation.")
folder = Path(st.sidebar.text_input("Dataset directory", "data/experiments/stage5-news40-unique"))
try:
    corpus, labels = read_jsonl(folder / "corpus.jsonl"), read_jsonl(folder / "annotations.jsonl")
except (OSError, ValueError) as exc:
    st.info(f"Select an existing collection: {type(exc).__name__}")
    st.stop()
by_id = {label["id"]: label for label in labels}
reviewed = sum(label.get("review_status") == "reviewed" for label in labels)
st.sidebar.metric("Reviewed", f"{reviewed} / {len(corpus)}")
st.sidebar.metric("Initial annotations completed", f"{sum(bool(label.get('draft_complete')) for label in labels)} / {len(corpus)}")
reviewer = st.sidebar.text_input("Reviewer name or group ID")
selected = st.sidebar.selectbox("Document", [doc["id"] for doc in corpus],
    format_func=lambda key: ("[done] " if by_id[key]["review_status"] == "reviewed" else "[todo] ") + key)
doc = next(doc for doc in corpus if doc["id"] == selected)
left, right = st.columns(2)
with left:
    st.subheader(doc.get("title", selected))
    st.write(doc["published_at"])
    if doc.get("source_url"):
        st.link_button("Open source", doc["source_url"])
    st.caption(doc.get("text_scope", "Document scope unspecified"))
    st.text(doc["text"])
with right:
    st.subheader("Typed relations")
    st.caption("Fields: source, source_type, relation, target, target_type, status. Preserve the original entity spelling.")
    label = by_id[selected]
    if label.get("category"):
        st.caption(f"Category: {label['category']}; adjudication needed: {bool(label.get('needs_adjudication'))}")
    initial = label["events"] if label["review_status"] == "reviewed" else label.get("proposed_events", label["events"])
    if label.get("proposal_by") and label["review_status"] != "reviewed":
        st.warning("AI proposal only. Correct these labels before confirming human review.")
    value = st.text_area("Events JSON list", json.dumps(initial, ensure_ascii=False, indent=2), height=330, key=selected)
    notes = st.text_area("Evidence spans / ambiguity notes", by_id[selected].get("notes", ""), key=selected + "_notes")
    confirmed = st.checkbox("I reviewed this document and its labels", key=selected + "_confirm")
    if st.button("Save reviewed annotation", disabled=not reviewer.strip() or not confirmed):
        try:
            events = json.loads(value)
            if not isinstance(events, list):
                raise ValueError("Events must be a list")
            from config import ENTITY_TYPES, REL_TYPES, STATUSES
            for event in events:
                if not all(event.get(key) for key in ("source", "target", "relation")):
                    raise ValueError("Each event needs source, target, relation")
                if event["relation"] not in REL_TYPES or event.get("status", "发酵中") not in STATUSES:
                    raise ValueError("Invalid relation or status")
                if event.get("source_type", "公司") not in ENTITY_TYPES or event.get("target_type", "公司") not in ENTITY_TYPES:
                    raise ValueError("Invalid entity type")
            # Re-read before saving to avoid overwriting other edits in this process.
            current = read_jsonl(folder / "annotations.jsonl")
            for label in current:
                if label["id"] == selected:
                    label.update(events=events, notes=notes, reviewer=reviewer.strip(), review_status="reviewed", reviewed_at=now())
            write_jsonl(folder / "annotations.jsonl", current)
            st.success("Saved. Select the next document.")
        except (ValueError, TypeError, KeyError) as exc:
            st.error(str(exc))
    if st.button("Validate completed dataset"):
        try:
            reviewed_labels(corpus, read_jsonl(folder / "annotations.jsonl"))
            st.success("Every document has a matching, reviewed annotation.")
        except ValueError as exc:
            st.warning(str(exc))
