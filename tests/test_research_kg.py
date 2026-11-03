import pytest
from research_kg import ResearchKG


def example():
    docs=[{"id":"a","published_at":"2024-01-02T00:00:00+08:00","source_url":"https://example.com/a"},
          {"id":"b","published_at":"2024-02-02T00:00:00+08:00","source_url":"https://example.com/b"}]
    obs=[{"dimension":"repurchase_stage","state":"STARTED","available_at":docs[0]["published_at"],"evidence_ids":["a"],"evidence_quote":"actual purchase"},
         {"dimension":"repurchase_stage","state":"COMPLETED","available_at":docs[1]["published_at"],"evidence_ids":["b"],"evidence_quote":"implementation completed"}]
    return docs,obs


def test_graph_query_filters_future_facts_and_resolves_sources():
    docs,obs=example();kg=ResearchKG("Company","Plan",docs,obs)
    result=kg.query("2024-01-03T00:00:00+08:00")
    assert result[0]["state"]=="STARTED" and result[0]["paths"][0][-1]=="a"
    assert kg.query("2024-02-03T00:00:00+08:00")[0]["state"]=="COMPLETED"
    assert len(kg.observations)==2


def test_graph_rejects_missing_and_future_evidence():
    docs,obs=example();obs[0]["evidence_ids"]=["missing"]
    with pytest.raises(ValueError):ResearchKG("Company","Plan",docs,obs)
    docs,obs=example();obs[0]["evidence_ids"]=["b"]
    with pytest.raises(ValueError):ResearchKG("Company","Plan",docs,obs)


def test_graph_roundtrip_preserves_query(tmp_path):
    docs,obs=example();kg=ResearchKG("Company","Plan",docs,obs);path=tmp_path/"graph.json";kg.dump(path)
    assert ResearchKG.load(path).query("2024-02-03T00:00:00+08:00")==kg.query("2024-02-03T00:00:00+08:00")


def test_graph_rejects_changed_corpus_hash(tmp_path):
    docs,obs=example();kg=ResearchKG("Company","Plan",docs,obs);path=tmp_path/"graph.json";kg.dump(path)
    with pytest.raises(ValueError,match="frozen corpus"):
        ResearchKG.load(path,expected_hashes={"a":"wrong","b":"wrong"})
