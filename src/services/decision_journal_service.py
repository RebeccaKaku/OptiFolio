"""Service for managing decision journal."""

from __future__ import annotations

import json
import uuid
import sqlite3
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.core.portfolio_book_db import PortfolioBookDatabase, PortfolioBookError
from src.domain.decision_journal import (
    Decision,
    DecisionRevision,
    DecisionStatus,
    AuthorType,
)

_log = logging.getLogger(__name__)


class DecisionJournalService:
    """Manages investment decision journal entries and revisions."""

    def __init__(self, db: PortfolioBookDatabase) -> None:
        self._db = db

    def create_decision(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new decision with its first revision."""
        try:
            decision_id = str(uuid.uuid4())
            revision_id = str(uuid.uuid4())

            # Required fields for decision
            title = data.get("title")
            decision_type = data.get("decision_type")
            as_of = data.get("as_of")

            if not all([title, decision_type, as_of]):
                return self._failure("Missing required decision fields", "VALIDATION_ERROR")

            # Required fields for first revision
            thesis = data.get("thesis")
            baseline = data.get("baseline")
            invalidation_conditions = data.get("invalidation_conditions")
            review_at = data.get("review_at")

            if not all([thesis, baseline, invalidation_conditions, review_at]):
                return self._failure("Missing required revision fields (thesis, baseline, invalidation_conditions, review_at)", "VALIDATION_ERROR")

            conn = self._db.connect()
            try:
                with conn:
                    # Validate references
                    self._validate_references(conn, data)

                    conn.execute(
                        """
                        INSERT INTO decisions (
                            decision_id, title, decision_type, as_of, status,
                            account_id, product_id, snapshot_batch_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            decision_id, title, decision_type, as_of, DecisionStatus.OPEN,
                            data.get("account_id"), data.get("product_id"), data.get("snapshot_batch_id")
                        )
                    )

                    conn.execute(
                        """
                        INSERT INTO decision_revisions (
                            revision_id, decision_id, revision_no, thesis, baseline,
                            priced_in, evidence_json, scenarios_json, position_reason,
                            invalidation_conditions, review_at, author_type
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            revision_id, decision_id, 1, thesis, baseline,
                            data.get("priced_in"),
                            json.dumps(data.get("evidence", [])),
                            json.dumps(data.get("scenarios", [])),
                            data.get("position_reason"),
                            invalidation_conditions,
                            review_at,
                            data.get("author_type", AuthorType.HUMAN)
                        )
                    )
                return {"success": True, "decision_id": decision_id}
            except sqlite3.IntegrityError as exc:
                if "FOREIGN KEY constraint failed" in str(exc):
                    return self._failure("Foreign key constraint failed (account, product, or snapshot batch not found)", "FOREIGN_KEY_ERROR")
                return self._failure(f"Database error: {exc}", "DATABASE_ERROR")
            except PortfolioBookError as exc:
                return self._failure(str(exc), "FOREIGN_KEY_ERROR")
            finally:
                conn.close()
        except Exception as exc:
            _log.exception("Failed to create decision")
            return self._failure(str(exc), "INTERNAL_ERROR")

    def append_revision(self, decision_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Append a new revision to an existing decision."""
        try:
            revision_id = str(uuid.uuid4())

            thesis = data.get("thesis")
            baseline = data.get("baseline")
            invalidation_conditions = data.get("invalidation_conditions")
            review_at = data.get("review_at")

            if not all([thesis, baseline, invalidation_conditions, review_at]):
                return self._failure("Missing required revision fields", "VALIDATION_ERROR")

            conn = self._db.connect()
            try:
                with conn:
                    # Check if decision exists and get next revision_no
                    row = conn.execute(
                        "SELECT MAX(revision_no) FROM decision_revisions WHERE decision_id = ?",
                        (decision_id,)
                    ).fetchone()
                    if row[0] is None:
                        return self._failure(f"Decision {decision_id} not found", "NOT_FOUND")

                    next_no = row[0] + 1

                    conn.execute(
                        """
                        INSERT INTO decision_revisions (
                            revision_id, decision_id, revision_no, thesis, baseline,
                            priced_in, evidence_json, scenarios_json, position_reason,
                            invalidation_conditions, review_at, author_type
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            revision_id, decision_id, next_no, thesis, baseline,
                            data.get("priced_in"),
                            json.dumps(data.get("evidence", [])),
                            json.dumps(data.get("scenarios", [])),
                            data.get("position_reason"),
                            invalidation_conditions,
                            review_at,
                            data.get("author_type", AuthorType.HUMAN)
                        )
                    )
                return {"success": True, "revision_id": revision_id, "revision_no": next_no}
            finally:
                conn.close()
        except Exception as exc:
            _log.exception("Failed to append revision")
            return self._failure(str(exc), "INTERNAL_ERROR")

    def get_decision(self, decision_id: str) -> Dict[str, Any]:
        """Get decision details including full revision history."""
        conn = self._db.connect()
        try:
            row = conn.execute("SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)).fetchone()
            if not row:
                return self._failure(f"Decision {decision_id} not found", "NOT_FOUND")

            decision = dict(row)
            revisions = conn.execute(
                "SELECT * FROM decision_revisions WHERE decision_id = ? ORDER BY revision_no ASC",
                (decision_id,)
            ).fetchall()

            decision["revisions"] = [self._map_revision(r) for r in revisions]
            return {"success": True, "decision": decision}
        finally:
            conn.close()

    def list_decisions(self, status: Optional[str] = None, decision_type: Optional[str] = None) -> Dict[str, Any]:
        """List and filter decisions."""
        conn = self._db.connect()
        try:
            query = "SELECT * FROM decisions WHERE 1=1"
            params = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if decision_type:
                query += " AND decision_type = ?"
                params.append(decision_type)

            query += " ORDER BY as_of DESC, created_at DESC"
            rows = conn.execute(query, params).fetchall()

            decisions = []
            for r in rows:
                d = dict(r)
                # Include latest revision info
                latest = conn.execute(
                    "SELECT thesis, review_at FROM decision_revisions WHERE decision_id = ? ORDER BY revision_no DESC LIMIT 1",
                    (d["decision_id"],)
                ).fetchone()
                if latest:
                    d["latest_thesis"] = latest["thesis"]
                    d["review_at"] = latest["review_at"]
                decisions.append(d)

            return {"success": True, "decisions": decisions}
        finally:
            conn.close()

    def mark_status(self, decision_id: str, status: str) -> Dict[str, Any]:
        """Update decision status."""
        if status not in [s.value for s in DecisionStatus]:
            return self._failure(f"Invalid status: {status}", "VALIDATION_ERROR")

        conn = self._db.connect()
        try:
            with conn:
                cursor = conn.execute(
                    "UPDATE decisions SET status = ? WHERE decision_id = ?",
                    (status, decision_id)
                )
                if cursor.rowcount == 0:
                    return self._failure(f"Decision {decision_id} not found", "NOT_FOUND")
            return {"success": True}
        finally:
            conn.close()

    def list_reviews_due(self, as_of: Optional[str] = None) -> Dict[str, Any]:
        """List open decisions with review_at <= as_of."""
        if not as_of:
            as_of = datetime.now().strftime("%Y-%m-%d")

        conn = self._db.connect()
        try:
            rows = conn.execute(
                """
                SELECT d.*, r.review_at, r.thesis
                FROM decisions d
                JOIN decision_revisions r ON d.decision_id = r.decision_id
                WHERE d.status IN ('open', 'review_due')
                AND r.revision_no = (SELECT MAX(revision_no) FROM decision_revisions WHERE decision_id = d.decision_id)
                AND r.review_at <= ?
                ORDER BY r.review_at ASC
                """,
                (as_of,)
            ).fetchall()
            return {"success": True, "decisions": [dict(r) for r in rows]}
        finally:
            conn.close()

    def _validate_references(self, conn: sqlite3.Connection, data: Dict[str, Any]) -> None:
        """Validate account, product, and snapshot batch IDs if provided."""
        if data.get("account_id"):
            row = conn.execute("SELECT 1 FROM accounts WHERE account_id = ?", (data["account_id"],)).fetchone()
            if not row:
                raise PortfolioBookError(f"Account {data['account_id']} not found")

        if data.get("product_id"):
            row = conn.execute("SELECT 1 FROM products WHERE product_id = ?", (data["product_id"],)).fetchone()
            if not row:
                raise PortfolioBookError(f"Product {data['product_id']} not found")

        if data.get("snapshot_batch_id"):
            row = conn.execute("SELECT 1 FROM snapshot_batches WHERE batch_id = ?", (data["snapshot_batch_id"],)).fetchone()
            if not row:
                raise PortfolioBookError(f"Snapshot batch {data['snapshot_batch_id']} not found")

    def _map_revision(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        d["evidence"] = json.loads(d.pop("evidence_json", "[]"))
        d["scenarios"] = json.loads(d.pop("scenarios_json", "[]"))
        return d

    def _failure(self, message: str, error_code: str) -> Dict[str, Any]:
        return {"success": False, "message": message, "error_code": error_code}
