from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from research_kg import ResearchKG
import stage5_research_ui as ui


def test_readonly_graph_page_renders_without_api_calls(tmp_path):
    directory=tmp_path/"groups"/"example";directory.mkdir(parents=True)
    documents=[{"id":"source","text":"actual purchase","published_at":"2024-01-02T00:00:00+08:00","source_url":"https://example.com/filing"}]
    observations=[{"dimension":"repurchase_stage","state":"STARTED","available_at":documents[0]["published_at"],"evidence_ids":["source"],"evidence_quote":"actual purchase"}]
    ResearchKG("Example company","One scheme",documents,observations).dump(directory/"graph.json")
    with patch.object(ui,"STUDY",tmp_path),patch.object(ui,"ROOT",tmp_path):
        app=AppTest.from_string("from stage5_research_ui import render_research\nrender_research()").run(timeout=25)
    assert not app.exception
    assert app.dataframe[0].value.iloc[0]["state"]=="STARTED"
