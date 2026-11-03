"""Neutral event/provenance graph shared by the root UI and research experiment.

Facts are machine-extracted observations, not investment theses or human truth.
Superseding the current view never asserts that a historical disclosure was false.
"""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
import networkx as nx


class ResearchKG:
    def __init__(self, company, event_key, documents, observations):
        self.graph = nx.DiGraph()
        self.company, self.event_key = company, event_key
        self.documents = {doc["id"]: doc for doc in documents}
        self.observations = sorted(observations, key=lambda row:(row["available_at"],row["dimension"],row["evidence_ids"][0]))
        self.graph.add_node("company", kind="COMPANY", label=company)
        self.graph.add_node("scheme", kind="SCHEME", label=event_key)
        self.graph.add_edge("company", "scheme", relation="HAS_SCHEME")
        for ident,doc in self.documents.items():
            self.graph.add_node(ident,kind="SOURCE",label=ident,available_at=doc["published_at"],source_url=doc.get("source_url",""))
            self.graph.add_edge("scheme",ident,relation="DISCLOSED_BY")
        previous={}
        for index,row in enumerate(self.observations):
            if not row["evidence_ids"] or not set(row["evidence_ids"]) <= set(self.documents):
                raise ValueError("Observation has no actual archived source")
            ident=f"observation_{index:03}"
            self.graph.add_node(ident,kind="OBSERVATION",label=row["dimension"]+": "+row["state"],**row)
            self.graph.add_edge("scheme",ident,relation="HAS_OBSERVATION")
            for source in row["evidence_ids"]:
                if self.documents[source]["published_at"]>row["available_at"]:
                    raise ValueError("Observation cites a future source")
                self.graph.add_edge(ident,source,relation="SUPPORTED_BY")
            dimension=row["dimension"]
            if dimension in previous:
                self.graph.add_edge(ident,previous[dimension],relation="SUPERSEDES_CURRENT_VIEW")
            previous[dimension]=ident

    def current(self,as_of):
        current={}
        for row in self.observations:
            if row["available_at"]<=as_of and row.get("admission_status")!="quarantined":current[row["dimension"]]=row
        return list(current.values())

    def answer_graph(self,as_of):
        current=self.current(as_of)
        return {"company":self.company,"scheme":self.event_key,
                "observations":current,"relations":[{"source":"scheme","relation":"HAS_CURRENT_STATE","target":row["dimension"]} for row in current],
                "provenance":"machine_extracted_source_spans_checked_not_human_gold"}

    def dump(self,path,metadata=None):
        payload={"company":self.company,"event_key":self.event_key,"documents":list(self.documents.values()),
                 "observations":self.observations,"nodes":[{"id":key,**attrs} for key,attrs in self.graph.nodes(data=True)],
                 "edges":[{"source":a,"target":b,**attrs} for a,b,attrs in self.graph.edges(data=True)],"metadata":metadata or {}}
        Path(path).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

    def query(self,as_of,dimension=None):
        """Traverse scheme-state-source paths and return current eligible evidence."""
        selected={}
        for ident in self.graph.successors("scheme"):
            node=self.graph.nodes[ident]
            if node.get("kind")!="OBSERVATION" or node["available_at"]>as_of:continue
            if node.get("admission_status")=="quarantined":continue
            if dimension and node["dimension"]!=dimension:continue
            sources=[source for source in self.graph.successors(ident)
                     if self.graph.edges[ident,source]["relation"]=="SUPPORTED_BY"
                     and self.graph.nodes[source]["available_at"]<=as_of]
            if not sources:continue
            key=node["dimension"]
            if key not in selected or node["available_at"]>=selected[key]["available_at"]:
                selected[key]={"dimension":key,"state":node["state"],"available_at":node["available_at"],
                    "quote":node["evidence_quote"],"paths":[["company","scheme",ident,s] for s in sources],
                    "sources":[{"id":s,"url":self.graph.nodes[s]["source_url"]} for s in sources]}
        return list(selected.values())

    @classmethod
    def load(cls,path,expected_hashes=None):
        data=json.loads(Path(path).read_text(encoding="utf-8"))
        if expected_hashes is not None:
            for doc in data["documents"]:
                digest=hashlib.sha256(doc.get("text","").encode()).hexdigest()
                if expected_hashes.get(doc["id"])!=digest:
                    raise ValueError("Archived source does not match the frozen corpus")
        return cls(data["company"],data["event_key"],data["documents"],data["observations"])
