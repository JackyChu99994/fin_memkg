from copy import deepcopy
import pytest
from scripts.audit_reserved_absence import controls, packet, reconcile


def fixture():
    q, docs, _, _ = controls()[1]
    result = {"decision": "insufficient", "first_purchase_date": None,
              "reason": "The only eligible proposal describes future implementation, not an actual first purchase.",
              "sources": [{"source_id": "CONTROL_SOURCE", "role": "target_scheme", "reason": "Original scheme proposal"}],
              "evidence": [{"source_id": "CONTROL_SOURCE", "quote": "拟在未来12个月择机实施"}], "conflicts": []}
    return q, docs, result


def test_reference_values_and_pending_labels_are_not_shared_with_auditor():
    q, docs, _ = fixture()
    q.update(reference_draft={}, source_qualification="pending", benchmark_family="insufficient")
    p = packet(q, docs)
    assert "reference_draft" not in p and "benchmark_family" not in p
    assert "source_qualification" not in p
    assert len(p["documents"]) == len(q["source_ids"])


def test_missing_source_or_invented_quote_prevents_audit_acceptance():
    _, docs, result = fixture()
    assert reconcile(result, docs)
    changed = deepcopy(result)
    changed["sources"] = []
    with pytest.raises(ValueError, match="inventory"):
        reconcile(changed, docs)
    changed = deepcopy(result)
    changed["evidence"][0]["quote"] = "公司没有实施任何回购"
    with pytest.raises(ValueError):
        reconcile(changed, docs)


def test_absence_cannot_contain_a_purchase_date():
    _, docs, result = fixture()
    result["first_purchase_date"] = "2024-01-02"
    with pytest.raises(ValueError, match="absence_contains_date"):
        reconcile(result, docs)


def test_id_keyed_source_inventory_normalizes_without_changing_quotes():
    _, docs, result = fixture()
    quote = result["evidence"][0]["quote"]
    result["sources"] = {"CONTROL_SOURCE": {"role": "target_scheme", "reason": "Original proposal"}}
    assert reconcile(result, docs)
    assert result["sources"][0]["source_id"] == "CONTROL_SOURCE"
    assert result["evidence"][0]["quote"] == quote
