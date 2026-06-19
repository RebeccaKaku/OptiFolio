"""Tests for model promotion registry."""

import pytest
from datetime import datetime, timedelta, UTC
from typing import Dict, Any

from src.domain.model_governance import ModelStatus, ModelRegistryItem
from src.research.model_registry import (
    load_registry,
    validate_model,
    approve_model,
    retire_model,
    query_approved_models
)

class MockDecisionJournalValidator:
    def __init__(self, valid_ids=None):
        self.valid_ids = valid_ids or []
    def is_valid(self, decision_id: str) -> bool:
        return decision_id in self.valid_ids

@pytest.fixture
def base_model_dict() -> Dict[str, Any]:
    return {
        "model_id": "test_model",
        "version": "1.0.0",
        "status": "experimental",
        "code_ref": "git:abc",
        "input_contract": {"assets": "list"},
        "output_contract": {"weights": "dict"},
        "data_cutoff": "2026-01-01T00:00:00Z",
        "training_window": {"start": "2020-01-01"},
        "validation_window": {"start": "2025-01-01"},
        "validation_metrics": {},
        "leakage_checks": {},
        "stability_checks": {},
        "known_limitations": ["limited data"],
        "approved_use_cases": ["asset_allocation"],
        "forbidden_use_cases": ["high_frequency"],
        "expires_at": "2027-01-01T00:00:00Z",
        "created_at": "2026-01-01T00:00:00Z"
    }

def test_load_empty_registry():
    yaml = "schema_version: 1\nmodels: []"
    registry = load_registry(yaml)
    assert registry.schema_version == 1
    assert len(registry.models) == 0

def test_load_valid_registry(base_model_dict):
    import yaml
    content = yaml.dump({"schema_version": 1, "models": [base_model_dict]})
    registry = load_registry(content)
    assert len(registry.models) == 1
    assert registry.models[0].model_id == "test_model"
    assert registry.models[0].status == ModelStatus.EXPERIMENTAL

def test_load_fail_closed():
    # Invalid YAML
    with pytest.raises(ValueError):
        load_registry("invalid: yaml: :")

    # Missing fields
    with pytest.raises(ValueError):
        load_registry("schema_version: 1\nmodels: [{model_id: 'm1'}]")

def test_state_transition_validate(base_model_dict):
    import yaml
    content = yaml.dump({"schema_version": 1, "models": [base_model_dict]})
    registry = load_registry(content)

    metrics = {"sharpe": 1.5}
    lc = {"no_leakage": True}
    sc = {"stable": True}

    new_reg = validate_model(registry, "test_model", "1.0.0", metrics, lc, sc)
    assert new_reg.models[0].status == ModelStatus.VALIDATED
    assert new_reg.models[0].validation_metrics == metrics

def test_state_transition_approve(base_model_dict):
    import yaml
    # Start from validated
    base_model_dict["status"] = "validated"
    base_model_dict["validation_metrics"] = {"sharpe": 1.5}
    base_model_dict["leakage_checks"] = {"ok": True}
    base_model_dict["stability_checks"] = {"ok": True}

    content = yaml.dump({"schema_version": 1, "models": [base_model_dict]})
    registry = load_registry(content)

    validator = MockDecisionJournalValidator(valid_ids=["DJ-123"])
    approved_at = datetime.now(UTC)

    # Valid approval
    new_reg = approve_model(registry, "test_model", "1.0.0", "Jules", approved_at, "DJ-123", validator)
    assert new_reg.models[0].status == ModelStatus.APPROVED
    assert new_reg.models[0].human_approver == "Jules"

    # Invalid Decision Journal
    with pytest.raises(ValueError, match="Invalid decision journal ID"):
        approve_model(registry, "test_model", "1.0.0", "Jules", approved_at, "DJ-999", validator)

def test_state_transition_retire(base_model_dict):
    import yaml
    content = yaml.dump({"schema_version": 1, "models": [base_model_dict]})
    registry = load_registry(content)

    new_reg = retire_model(registry, "test_model", "1.0.0")
    assert new_reg.models[0].status == ModelStatus.RETIRED

    # Retired is terminal
    with pytest.raises(ValueError, match="cannot validate"):
        validate_model(new_reg, "test_model", "1.0.0", {}, {}, {})

def test_query_approved_models(base_model_dict):
    import yaml
    base_model_dict["status"] = "approved"
    base_model_dict["approved_use_cases"] = ["case1"]
    base_model_dict["forbidden_use_cases"] = ["case2"]
    base_model_dict["expires_at"] = "2027-01-01T00:00:00Z"
    base_model_dict["input_contract"] = {"required_field": "type"}

    content = yaml.dump({"schema_version": 1, "models": [base_model_dict]})
    registry = load_registry(content)

    as_of = datetime(2026, 6, 1, tzinfo=UTC)

    # Match
    matches = query_approved_models(registry, "case1", as_of, {"required_field": "value"})
    assert len(matches) == 1

    # Use case mismatch
    assert len(query_approved_models(registry, "unknown", as_of, {"required_field": "value"})) == 0

    # Forbidden use case
    assert len(query_approved_models(registry, "case2", as_of, {"required_field": "value"})) == 0

    # Expired
    future_as_of = datetime(2028, 1, 1, tzinfo=UTC)
    assert len(query_approved_models(registry, "case1", future_as_of, {"required_field": "value"})) == 0

    # Contract mismatch
    assert len(query_approved_models(registry, "case1", as_of, {"wrong_field": "value"})) == 0

def test_audit_info_complete(base_model_dict):
    import yaml
    base_model_dict["status"] = "validated"
    base_model_dict["validation_metrics"] = {"m": 1}
    base_model_dict["leakage_checks"] = {"l": 1}
    base_model_dict["stability_checks"] = {"s": 1}

    content = yaml.dump({"schema_version": 1, "models": [base_model_dict]})
    registry = load_registry(content)

    validator = MockDecisionJournalValidator(valid_ids=["DJ-1"])
    new_reg = approve_model(registry, "test_model", "1.0.0", "Jules", datetime.now(UTC), "DJ-1", validator)

    item = new_reg.models[0]
    assert item.human_approver == "Jules"
    assert item.approved_at is not None
    assert item.decision_journal_id == "DJ-1"
    assert item.validation_metrics == {"m": 1}
