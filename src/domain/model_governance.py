"""Domain models for model promotion registry and governance."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, Tuple


class ModelStatus:
    EXPERIMENTAL = "experimental"
    VALIDATED = "validated"
    APPROVED = "approved"
    RETIRED = "retired"

    @classmethod
    def all(cls) -> List[str]:
        return [cls.EXPERIMENTAL, cls.VALIDATED, cls.APPROVED, cls.RETIRED]


@dataclass(frozen=True)
class ModelRegistryItem:
    model_id: str
    version: str
    status: str
    code_ref: str
    input_contract: Dict[str, Any]
    output_contract: Dict[str, Any]
    data_cutoff: datetime
    training_window: Dict[str, Any]
    validation_window: Dict[str, Any]
    validation_metrics: Dict[str, Any]
    leakage_checks: Dict[str, Any]
    stability_checks: Dict[str, Any]
    known_limitations: List[str]
    approved_use_cases: List[str]
    forbidden_use_cases: List[str]
    expires_at: datetime
    created_at: datetime
    human_approver: Optional[str] = None
    approved_at: Optional[datetime] = None
    decision_journal_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in ModelStatus.all():
            raise ValueError(f"Unknown status: {self.status}")


@dataclass(frozen=True)
class ModelRegistry:
    schema_version: int
    models: Tuple[ModelRegistryItem, ...] = field(default_factory=tuple)


class DecisionJournalValidator(Protocol):
    def is_valid(self, decision_id: str) -> bool:
        """Checks if the decision journal ID exists and is valid."""
        ...
