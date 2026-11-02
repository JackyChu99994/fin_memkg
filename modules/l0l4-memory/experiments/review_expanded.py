"""Streamlit review of expanded source-grounded lifecycle reference drafts.

Run with streamlit run experiments/review_expanded.py -- --corpus ... --references ... --save ...
Saving requires an actual reviewer action; original drafts are preserved.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.common import now, read_jsonl, write_jsonl
from experiments.draft_expanded_references import validate


def main():
    import streamlit as st
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--save", type=Path, required=True)
    args = parser.parse_args()
    if args.save.resolve() in {args.corpus.resolve(), args.references.resolve()}:
        raise ValueError("Save reviewed records to a separate file")
    corpus = read_jsonl(args.corpus)
    originals = read_jsonl(args.references)
    records = read_jsonl(args.save) if args.save.exists() else originals
    if {row["id"] for row in records} != {row["id"] for row in originals}:
        raise ValueError("Review file does not match the original dataset")
    by_id = {doc["id"]: doc for doc in corpus}
    initial = {doc["candidate_id"]: doc for doc in corpus if doc["role"] == "initial_candidate"}
    for record in records:
        if record["text_sha256"] != by_id[record["id"]]["text_sha256"]:
            raise ValueError("Review source hash mismatch")
    st.set_page_config(page_title="Expanded lifecycle review", layout="wide")
    st.title("Expanded lifecycle reference review")
    st.caption("AI drafts are not reviewed truth. Review source identity and factual support; do not infer correctness from a matched quote alone.")
    done = sum(row.get("review_status") == "reviewed" for row in records)
    st.write(f"Reviewed: {done}/{len(records)}")
    reviewer = st.sidebar.text_input("Reviewer name or stable identifier")
    partition = st.sidebar.selectbox("Partition", ["All", "development", "test_reserved"])
    flagged_only = st.sidebar.checkbox("Show only validation flags / failures")
    unreviewed_only = st.sidebar.checkbox("Show only unreviewed", value=True)
    choices = [row for row in records if (partition == "All" or row["split"] == partition)
               and (not flagged_only or row.get("validation_errors") or row.get("status") == "failed")
               and (not unreviewed_only or row.get("review_status") != "reviewed")]
    if not choices:
        st.info("No matching records")
        return
    ident = st.sidebar.selectbox("Document", [row["id"] for row in choices], format_func=lambda key:
        by_id[key]["stock_code"] + " | " + by_id[key]["disclosure_date"] + " | " + by_id[key]["title"])
    record = next(row for row in records if row["id"] == ident)
    doc = by_id[ident]
    first = initial[doc["candidate_id"]]
    st.subheader(doc["stock_code"] + " " + doc["company"] + " — " + doc["title"])
    st.write("Partition:", doc["split"], "| Disclosure date:", doc["disclosure_date"])
    st.link_button("Open original current filing", doc["source_url"])
    st.write("Draft validation flags:", record.get("validation_errors", []))
    left, right = st.columns(2)
    with left:
        with st.expander("Initial filing full text", expanded=False):
            st.link_button("Open initial filing", first["source_url"])
            st.text(first["text"])
        with st.expander("Current filing full text", expanded=True):
            st.text(doc["text"])
    with right:
        values = record.get("adjudicated") or record.get("draft") or {}
        st.caption("Edit JSON fields and source evidence as needed. UNKNOWN and UNCERTAIN remain explicit exclusions for formal scoring.")
        edited = st.text_area("Reference fields and evidence", json.dumps(values, ensure_ascii=False, indent=2), height=650, key="editor_" + ident)
        confirmed = st.checkbox("I checked scheme identity, dates, state values, and supporting source evidence", key="checked_" + ident)
        if st.button("Save reviewed record", type="primary"):
            if not reviewer.strip() or not confirmed:
                st.error("Enter a reviewer identifier and confirm the source check")
                return
            try:
                adjudicated = json.loads(edited)
                errors = validate(adjudicated, {row["id"]: row for row in (first, doc)})
                if errors:
                    st.error("Resolve validation errors before saving: " + ", ".join(errors))
                    return
                record.update(adjudicated=adjudicated, review_status="reviewed", reviewer=reviewer.strip(),
                    reviewed_at=now(), review_method="explicit_reviewer_source_check_in_editor",
                    validation_errors=[], status="reviewed")
                args.save.parent.mkdir(parents=True, exist_ok=True)
                temporary = args.save.with_name(args.save.name + ".tmp")
                write_jsonl(temporary, records)
                temporary.replace(args.save)
                st.success("Saved separately; original AI draft retained")
                st.rerun()
            except (ValueError, TypeError, KeyError) as exc:
                st.error("Cannot save reference: " + type(exc).__name__)


if __name__ == "__main__":
    main()
