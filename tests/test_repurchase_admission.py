from copy import deepcopy
from repurchase_admission import project_machine_claim


def fixture():
    public = {"question_id": "Q1", "stock_code": "600001", "as_of": "2024-02-02T00:00:00+08:00", "target_scheme_prefix": "600001_BOARD_",
              "requested_fields": {"primary_issuer_source": "source ID"}, "documents": [
                  {"id": "ISSUER", "title": "Company scheme notice", "disclosure_date": "2024-02-01"},
                  {"id": "OPINION", "title": "关于回购方案的核查意见", "disclosure_date": "2024-02-01"}]}
    prediction = {"question_id": "Q1", "status": "answered", "target_scheme": "600001_BOARD_2024-01-31",
                  "answer": {"primary_issuer_source": "ISSUER"}, "evidence_ids": ["ISSUER"]}
    return public, prediction


def test_opinion_gate_uses_only_public_sources_and_never_changes_raw_answer():
    public, prediction = fixture()
    prediction["answer"]["primary_issuer_source"] = "OPINION"
    original = deepcopy(prediction)
    result = project_machine_claim(public, prediction)
    assert result["status"] == "quarantined" and not result["facts"]
    assert prediction == original and result["raw_prediction"] == original


def test_passing_structure_is_not_certified_as_true():
    public, prediction = fixture()
    result = project_machine_claim(public, prediction)
    assert result["status"] == "machine_claim_pending_semantic_review"
    assert not result["human_verified"] and not result["semantic_entailment_verified"]


def test_future_source_cannot_be_admitted():
    public, prediction = fixture()
    public["documents"][0]["disclosure_date"] = "2024-02-03"
    assert project_machine_claim(public, prediction)["status"] == "quarantined"


def test_nested_answer_does_not_become_a_verified_flat_fact():
    public, prediction = fixture()
    prediction["answer"] = {"field": {"primary_issuer_source": "ISSUER"}}
    assert project_machine_claim(public, prediction)["status"] == "quarantined"


def test_comparison_retains_two_scheme_links_and_flags_target_metadata():
    public, prediction = fixture()
    public["requested_fields"] = {"source_approval_dates": "mapping"}
    public["requested_source_ids"] = ["ISSUER", "OPINION"]
    prediction["answer"] = {"source_approval_dates": {"ISSUER": "2024-01-01", "OPINION": "2024-01-31"}}
    prediction["target_scheme"] = "600001_BOARD_2024-01-01"
    result = project_machine_claim(public, prediction)
    assert len(result["scheme_nodes"]) == 2 and result["warnings"]
    assert result["raw_prediction"]["target_scheme"] == "600001_BOARD_2024-01-01"


def test_abstention_produces_no_fact():
    public, prediction = fixture()
    prediction.update(status="insufficient", answer={}, evidence_ids=[], missing_reason="No evidence")
    result = project_machine_claim(public, prediction)
    assert result["status"] == "no_admitted_answer" and result["facts"] == []
