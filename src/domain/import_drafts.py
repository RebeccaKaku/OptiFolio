"""Domain models for screenshot import drafts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


class ImportDraftStatus:
    PENDING = "pending"
    REVIEWED = "reviewed"
    APPLIED = "applied"
    REJECTED = "rejected"


class ImportTargetKind:
    ACCOUNT = "account"
    PRODUCT = "product"
    POSITION = "position"


class ReviewStatus:
    UNREVIEWED = "unreviewed"
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ImportCandidate:
    candidate_id: str
    import_id: str
    field_name: str
    raw_text: Optional[str] = None
    proposed_value: Any = None
    confidence: Optional[float] = None
    review_status: str = ReviewStatus.UNREVIEWED
    corrected_value: Any = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "import_id": self.import_id,
            "field_name": self.field_name,
            "raw_text": self.raw_text,
            "proposed_value": self.proposed_value,
            "confidence": self.confidence,
            "review_status": self.review_status,
            "corrected_value": self.corrected_value,
            "notes": self.notes,
        }

    @property
    def final_value(self) -> Any:
        if self.review_status == ReviewStatus.CORRECTED:
            return self.corrected_value
        if self.review_status == ReviewStatus.ACCEPTED:
            return self.proposed_value
        return None


@dataclass(frozen=True)
class ImportDraft:
    import_id: str
    contract_version: int
    target_kind: str
    source_type: str
    source_ref: str
    status: str = ImportDraftStatus.PENDING
    candidates: List[ImportCandidate] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "import_id": self.import_id,
            "contract_version": self.contract_version,
            "target_kind": self.target_kind,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "status": self.status,
            "candidates": [c.to_dict() for c in self.candidates],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
