"""Domain models for decision journal."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class DecisionStatus(str, Enum):
    OPEN = "open"
    REVIEW_DUE = "review_due"
    CLOSED = "closed"
    INVALIDATED = "invalidated"


class AuthorType(str, Enum):
    HUMAN = "human"
    AI = "ai"


class DecisionType(str, Enum):
    INVESTMENT = "investment"
    ALLOCATION = "allocation"
    RISK_MANAGEMENT = "risk_management"
    OTHER = "other"


@dataclass(frozen=True)
class DecisionRevision:
    revision_id: str
    decision_id: str
    revision_no: int
    thesis: str
    baseline: str
    invalidation_conditions: str
    review_at: str
    author_type: AuthorType = AuthorType.HUMAN
    priced_in: Optional[str] = None
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    scenarios: List[Dict[str, Any]] = field(default_factory=list)
    position_reason: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class Decision:
    decision_id: str
    title: str
    decision_type: str
    as_of: str
    status: DecisionStatus = DecisionStatus.OPEN
    account_id: Optional[str] = None
    product_id: Optional[str] = None
    snapshot_batch_id: Optional[str] = None
    created_at: Optional[datetime] = None
    revisions: List[DecisionRevision] = field(default_factory=list)

    @property
    def latest_revision(self) -> Optional[DecisionRevision]:
        if not self.revisions:
            return None
        return max(self.revisions, key=lambda r: r.revision_no)
