"""Service for managing screenshot import drafts."""

from __future__ import annotations

import json
import re
import uuid
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.core.portfolio_book_db import PortfolioBookDatabase, PortfolioBookError
from src.domain.import_drafts import (
    ImportDraft,
    ImportCandidate,
    ImportDraftStatus,
    ImportTargetKind,
    ReviewStatus,
)

_log = logging.getLogger(__name__)


class ImportDraftService:
    """Manages the lifecycle of import drafts and candidates."""

    def __init__(self, db: PortfolioBookDatabase) -> None:
        self._db = db

    def create_draft(
        self,
        target_kind: str,
        source_type: str,
        source_ref: str,
        candidates_data: List[Dict[str, Any]],
        contract_version: int = 1,
    ) -> str:
        """Create a new import draft with candidates."""
        if target_kind not in (
            ImportTargetKind.ACCOUNT,
            ImportTargetKind.PRODUCT,
            ImportTargetKind.POSITION,
        ):
            raise ValueError(f"Invalid target_kind: {target_kind}")

        import_id = str(uuid.uuid4())

        # Sanitize source_ref
        source_ref = self._sanitize_text(source_ref)
        if self._contains_sensitive_data(source_ref):
            raise ValueError("source_ref contains sensitive data")

        conn = self._db.connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO import_drafts (
                        import_id, contract_version, target_kind, source_type, source_ref, status
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        import_id,
                        contract_version,
                        target_kind,
                        source_type,
                        source_ref,
                        ImportDraftStatus.PENDING,
                    ),
                )

                for cdata in candidates_data:
                    candidate_id = str(uuid.uuid4())
                    field_name = cdata["field_name"]

                    raw_text_in = cdata.get("raw_text", "")
                    if self._contains_sensitive_data(raw_text_in):
                        raise ValueError(f"Field {field_name} contains sensitive data in raw_text")

                    raw_text = self._sanitize_text(raw_text_in)
                    proposed_value = cdata.get("proposed_value")
                    confidence = cdata.get("confidence")
                    notes = self._sanitize_text(cdata.get("notes", ""))

                    proposed_value_json = json.dumps(proposed_value) if proposed_value is not None else None

                    conn.execute(
                        """
                        INSERT INTO import_candidates (
                            candidate_id, import_id, field_name, raw_text, proposed_value_json, confidence, notes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            candidate_id,
                            import_id,
                            field_name,
                            raw_text,
                            proposed_value_json,
                            confidence,
                            notes,
                        ),
                    )
            return import_id
        finally:
            conn.close()

    def get_draft(self, import_id: str) -> Optional[ImportDraft]:
        """Fetch a draft and its candidates."""
        conn = self._db.connect()
        try:
            draft_row = conn.execute(
                "SELECT * FROM import_drafts WHERE import_id = ?", (import_id,)
            ).fetchone()
            if not draft_row:
                return None

            candidate_rows = conn.execute(
                "SELECT * FROM import_candidates WHERE import_id = ?", (import_id,)
            ).fetchall()

            candidates = []
            for row in candidate_rows:
                candidates.append(
                    ImportCandidate(
                        candidate_id=row["candidate_id"],
                        import_id=row["import_id"],
                        field_name=row["field_name"],
                        raw_text=row["raw_text"],
                        proposed_value=json.loads(row["proposed_value_json"])
                        if row["proposed_value_json"]
                        else None,
                        confidence=row["confidence"],
                        review_status=row["review_status"],
                        corrected_value=json.loads(row["corrected_value_json"])
                        if row["corrected_value_json"]
                        else None,
                        notes=row["notes"],
                    )
                )

            return ImportDraft(
                import_id=draft_row["import_id"],
                contract_version=draft_row["contract_version"],
                target_kind=draft_row["target_kind"],
                source_type=draft_row["source_type"],
                source_ref=draft_row["source_ref"],
                status=draft_row["status"],
                candidates=candidates,
                created_at=datetime.fromisoformat(draft_row["created_at"].replace(" ", "T")),
                updated_at=datetime.fromisoformat(draft_row["updated_at"].replace(" ", "T")),
            )
        finally:
            conn.close()

    def update_candidate(
        self,
        candidate_id: str,
        review_status: str,
        corrected_value: Any = None,
        notes: Optional[str] = None,
    ) -> None:
        """Update review status and correction for a candidate."""
        if review_status not in (
            ReviewStatus.ACCEPTED,
            ReviewStatus.CORRECTED,
            ReviewStatus.REJECTED,
            ReviewStatus.UNREVIEWED,
        ):
            raise ValueError(f"Invalid review_status: {review_status}")

        notes = self._sanitize_text(notes) if notes else None
        corrected_value_json = json.dumps(corrected_value) if corrected_value is not None else None

        conn = self._db.connect()
        try:
            with conn:
                # Check if draft is still editable
                draft_status = conn.execute(
                    """
                    SELECT d.status FROM import_drafts d
                    JOIN import_candidates c ON d.import_id = c.import_id
                    WHERE c.candidate_id = ?
                    """,
                    (candidate_id,),
                ).fetchone()

                if not draft_status:
                    raise PortfolioBookError(f"Candidate {candidate_id} not found")
                if draft_status["status"] != ImportDraftStatus.PENDING:
                    raise PortfolioBookError(f"Cannot update candidate for draft in {draft_status['status']} status")

                conn.execute(
                    """
                    UPDATE import_candidates SET
                        review_status = ?, corrected_value_json = ?, notes = ?
                    WHERE candidate_id = ?
                    """,
                    (review_status, corrected_value_json, notes, candidate_id),
                )

                conn.execute(
                    """
                    UPDATE import_drafts SET updated_at = CURRENT_TIMESTAMP
                    WHERE import_id = (SELECT import_id FROM import_candidates WHERE candidate_id = ?)
                    """,
                    (candidate_id,),
                )
        finally:
            conn.close()

    def reject_draft(self, import_id: str) -> None:
        """Mark a draft as rejected."""
        self._update_draft_status(import_id, ImportDraftStatus.REJECTED)

    def mark_reviewed(self, import_id: str) -> None:
        """Mark a draft as reviewed if all requirements are met."""
        draft = self.get_draft(import_id)
        if not draft:
            raise PortfolioBookError(f"Draft {import_id} not found")

        if draft.status != ImportDraftStatus.PENDING:
            raise PortfolioBookError(f"Draft {import_id} is already in {draft.status} status")

        # Validation
        valid, errors = self.validate_draft(draft)
        if not valid:
            raise ValueError(f"Draft validation failed: {', '.join(errors)}")

        self._update_draft_status(import_id, ImportDraftStatus.REVIEWED)

    def generate_preview(self, import_id: str) -> Dict[str, Any]:
        """Generate the payload preview for a reviewed draft."""
        draft = self.get_draft(import_id)
        if not draft:
            raise PortfolioBookError(f"Draft {import_id} not found")

        if draft.status != ImportDraftStatus.REVIEWED:
            raise PortfolioBookError("Only reviewed drafts can generate preview")

        payload = {}
        candidates_dict = {c.field_name: c for c in draft.candidates}

        if draft.target_kind == ImportTargetKind.ACCOUNT:
            payload = {
                "name": self._get_final_value(candidates_dict, "name"),
                "institution": self._get_final_value(candidates_dict, "institution", ""),
                "account_type": self._get_final_value(candidates_dict, "account_type", "brokerage"),
                "base_currency": self._get_final_value(candidates_dict, "base_currency"),
                "notes": self._get_final_value(candidates_dict, "notes", ""),
            }
        elif draft.target_kind == ImportTargetKind.PRODUCT:
            payload = {
                "name": self._get_final_value(candidates_dict, "name"),
                "product_type": self._get_final_value(candidates_dict, "product_type"),
                "currency": self._get_final_value(candidates_dict, "currency"),
                "issuer": self._get_final_value(candidates_dict, "issuer", ""),
                "notes": self._get_final_value(candidates_dict, "notes", ""),
            }
        elif draft.target_kind == ImportTargetKind.POSITION:
            payload = {
                "account_id": self._get_final_value(candidates_dict, "account_id"),
                "product_id": self._get_final_value(candidates_dict, "product_id"),
                "currency": self._get_final_value(candidates_dict, "currency"),
                "quantity": self._get_final_value(candidates_dict, "quantity"),
                "market_value": self._get_final_value(candidates_dict, "market_value"),
                "notes": self._get_final_value(candidates_dict, "notes", ""),
            }

        return {
            "import_id": draft.import_id,
            "target_kind": draft.target_kind,
            "payload": payload,
            "needs_attention": [
                c.field_name for c in draft.candidates
                if (c.confidence is not None and c.confidence < 0.8)
                or c.review_status == ReviewStatus.UNREVIEWED
            ]
        }

    def validate_draft(self, draft: ImportDraft) -> Tuple[bool, List[str]]:
        """Validate if a draft is ready to be marked as reviewed."""
        errors = []
        candidates_dict = {c.field_name: c for c in draft.candidates}

        def check_field(field_name: str, required: bool = True):
            c = candidates_dict.get(field_name)
            if not c:
                if required:
                    errors.append(f"Missing required field: {field_name}")
                return
            if c.review_status == ReviewStatus.UNREVIEWED:
                errors.append(f"Field {field_name} is unreviewed")
            elif c.review_status == ReviewStatus.REJECTED:
                if required:
                    errors.append(f"Required field {field_name} is rejected")
            elif c.review_status in (ReviewStatus.ACCEPTED, ReviewStatus.CORRECTED):
                val = c.final_value
                if required and val in (None, ""):
                    errors.append(f"Field {field_name} has no valid value")

        if draft.target_kind == ImportTargetKind.ACCOUNT:
            check_field("name")
            check_field("base_currency")
        elif draft.target_kind == ImportTargetKind.PRODUCT:
            check_field("name")
            check_field("product_type")
            check_field("currency")
        elif draft.target_kind == ImportTargetKind.POSITION:
            check_field("account_id")
            check_field("product_id")
            check_field("currency")

            q = candidates_dict.get("quantity")
            mv = candidates_dict.get("market_value")

            if not q and not mv:
                errors.append("Position must have at least one of quantity or market_value")
            else:
                q_val = q.final_value if q and q.review_status in (ReviewStatus.ACCEPTED, ReviewStatus.CORRECTED) else None
                mv_val = mv.final_value if mv and mv.review_status in (ReviewStatus.ACCEPTED, ReviewStatus.CORRECTED) else None
                if q_val is None and mv_val is None:
                    errors.append("Position must have at least one valid quantity or market_value")

        return len(errors) == 0, errors

    def _get_final_value(self, candidates: Dict[str, ImportCandidate], field_name: str, default: Any = None) -> Any:
        c = candidates.get(field_name)
        if not c or c.review_status not in (ReviewStatus.ACCEPTED, ReviewStatus.CORRECTED):
            return default
        return c.final_value

    def _update_draft_status(self, import_id: str, status: str) -> None:
        conn = self._db.connect()
        try:
            with conn:
                cursor = conn.execute(
                    "UPDATE import_drafts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE import_id = ?",
                    (status, import_id),
                )
                if cursor.rowcount == 0:
                    raise PortfolioBookError(f"Draft {import_id} not found")
        finally:
            conn.close()

    def _sanitize_text(self, text: str) -> str:
        """Mask sensitive info like account numbers."""
        if not text:
            return text

        # Simple account hint masking (keep only last 4 digits)
        # We look for "account" or similar keywords followed by numbers
        # But for general text, we might just look for long number sequences

        # Mask sequences of 12+ digits (likely card or account numbers)
        text = re.sub(r'\d{12,}', lambda m: '*' * (len(m.group()) - 4) + m.group()[-4:], text)

        return text

    def _contains_sensitive_data(self, text: str) -> bool:
        """Check for hard-reject sensitive data."""
        if not text:
            return False

        # Hard rules: Bank card (16-19 digits), ID cards, passwords, tokens
        # Bank cards: 16-19 digits
        if re.search(r'\d{16,19}', text):
            return True

        # Generic "password" or "token" keywords near something that looks like one
        if re.search(r'(password|token|secret|passwd)[:=]\s*\S+', text, re.I):
            return True

        return False
