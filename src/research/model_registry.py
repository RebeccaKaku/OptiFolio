"""Research model registry implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import yaml

from src.domain.model_governance import (
    DecisionJournalValidator,
    ModelRegistry,
    ModelRegistryItem,
    ModelStatus,
)


def load_registry(yaml_content: str) -> ModelRegistry:
    """Loads and validates the model registry from YAML content."""
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}")

    if not isinstance(data, dict):
        raise ValueError("Registry data must be a dictionary")

    schema_version = data.get("schema_version")
    if not isinstance(schema_version, int):
        raise ValueError("schema_version must be an integer")

    models_data = data.get("models", [])
    if not isinstance(models_data, list):
        raise ValueError("models must be a list")

    models = []
    for item in models_data:
        models.append(_parse_item(item))

    return ModelRegistry(schema_version=schema_version, models=tuple(models))


def _parse_item(data: Dict[str, Any]) -> ModelRegistryItem:
    # Ensure mandatory fields
    required = [
        "model_id", "version", "status", "code_ref", "input_contract",
        "output_contract", "data_cutoff", "training_window", "validation_window",
        "validation_metrics", "leakage_checks", "stability_checks",
        "known_limitations", "approved_use_cases", "forbidden_use_cases",
        "expires_at", "created_at"
    ]
    for field in required:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    # Helper to parse datetime
    def parse_dt(val: Any, field_name: str) -> datetime:
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val)
            except ValueError:
                raise ValueError(f"Invalid datetime format for {field_name}: {val}")
        raise ValueError(f"Expected datetime or ISO string for {field_name}, got {type(val)}")

    return ModelRegistryItem(
        model_id=data["model_id"],
        version=data["version"],
        status=data["status"],
        code_ref=data["code_ref"],
        input_contract=data["input_contract"],
        output_contract=data["output_contract"],
        data_cutoff=parse_dt(data["data_cutoff"], "data_cutoff"),
        training_window=data["training_window"],
        validation_window=data["validation_window"],
        validation_metrics=data["validation_metrics"],
        leakage_checks=data["leakage_checks"],
        stability_checks=data["stability_checks"],
        known_limitations=data["known_limitations"],
        approved_use_cases=data["approved_use_cases"],
        forbidden_use_cases=data["forbidden_use_cases"],
        expires_at=parse_dt(data["expires_at"], "expires_at"),
        created_at=parse_dt(data["created_at"], "created_at"),
        human_approver=data.get("human_approver"),
        approved_at=parse_dt(data["approved_at"], "approved_at") if data.get("approved_at") else None,
        decision_journal_id=data.get("decision_journal_id"),
    )


def validate_model(
    registry: ModelRegistry,
    model_id: str,
    version: str,
    metrics: Dict[str, Any],
    leakage_checks: Dict[str, Any],
    stability_checks: Dict[str, Any]
) -> ModelRegistry:
    """Transitions an experimental model to validated."""
    new_models = []
    found = False
    for item in registry.models:
        if item.model_id == model_id and item.version == version:
            if item.status != ModelStatus.EXPERIMENTAL:
                raise ValueError(f"Model {model_id} v{version} is in status {item.status}, cannot validate")

            # Create validated version
            new_item = ModelRegistryItem(
                **{**item.__dict__,
                   "status": ModelStatus.VALIDATED,
                   "validation_metrics": metrics,
                   "leakage_checks": leakage_checks,
                   "stability_checks": stability_checks}
            )
            new_models.append(new_item)
            found = True
        else:
            new_models.append(item)

    if not found:
        raise ValueError(f"Model {model_id} v{version} not found")

    return ModelRegistry(schema_version=registry.schema_version, models=tuple(new_models))


def approve_model(
    registry: ModelRegistry,
    model_id: str,
    version: str,
    human_approver: str,
    approved_at: datetime,
    decision_journal_id: str,
    validator: DecisionJournalValidator
) -> ModelRegistry:
    """Transitions a validated model to approved."""
    if not validator.is_valid(decision_journal_id):
        raise ValueError(f"Invalid decision journal ID: {decision_journal_id}")

    new_models = []
    found = False
    for item in registry.models:
        if item.model_id == model_id and item.version == version:
            if item.status != ModelStatus.VALIDATED:
                raise ValueError(f"Model {model_id} v{version} is in status {item.status}, cannot approve")

            # Check if validation evidence is "complete" (non-empty as a basic check)
            if not item.validation_metrics or not item.leakage_checks or not item.stability_checks:
                raise ValueError(f"Model {model_id} v{version} lacks complete validation evidence")

            new_item = ModelRegistryItem(
                **{**item.__dict__,
                   "status": ModelStatus.APPROVED,
                   "human_approver": human_approver,
                   "approved_at": approved_at,
                   "decision_journal_id": decision_journal_id}
            )
            new_models.append(new_item)
            found = True
        else:
            new_models.append(item)

    if not found:
        raise ValueError(f"Model {model_id} v{version} not found")

    return ModelRegistry(schema_version=registry.schema_version, models=tuple(new_models))


def retire_model(registry: ModelRegistry, model_id: str, version: str) -> ModelRegistry:
    """Transitions a model to retired."""
    new_models = []
    found = False
    for item in registry.models:
        if item.model_id == model_id and item.version == version:
            if item.status == ModelStatus.RETIRED:
                new_models.append(item) # Already retired
            else:
                new_item = ModelRegistryItem(**{**item.__dict__, "status": ModelStatus.RETIRED})
                new_models.append(new_item)
            found = True
        else:
            new_models.append(item)

    if not found:
        raise ValueError(f"Model {model_id} v{version} not found")

    return ModelRegistry(schema_version=registry.schema_version, models=tuple(new_models))


def query_approved_models(
    registry: ModelRegistry,
    use_case: str,
    as_of: datetime,
    input_contract: Dict[str, Any]
) -> List[ModelRegistryItem]:
    """Queries for approved models that match use case and input contract."""
    matches = []
    for item in registry.models:
        if item.status != ModelStatus.APPROVED:
            continue

        if item.expires_at <= as_of:
            continue

        if use_case in item.forbidden_use_cases:
            continue

        if use_case not in item.approved_use_cases:
            continue

        # Contract matching: provided input_contract must satisfy model's requirements
        # Basic check: all keys in item.input_contract must exist in provided input_contract
        # and types/values should match if specified (here we just check keys and basic type)
        contract_ok = True
        for req_key, req_spec in item.input_contract.items():
            if req_key not in input_contract:
                contract_ok = False
                break
            # Optional: deep type check could be added here

        if contract_ok:
            matches.append(item)

    return matches
