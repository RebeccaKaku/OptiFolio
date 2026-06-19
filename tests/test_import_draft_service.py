"""Tests for ImportDraftService — DS-010 screenshot import drafts."""

import pytest
import uuid
import json
from datetime import datetime

from src.core.portfolio_book_db import PortfolioBookDatabase, PortfolioBookError
from src.services.import_draft_service import ImportDraftService
from src.domain.import_drafts import ImportDraftStatus, ImportTargetKind, ReviewStatus


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_import.sqlite"
    db = PortfolioBookDatabase(path=db_path)
    db.initialize()
    return db


@pytest.fixture
def service(db):
    return ImportDraftService(db)


class TestImportDraftService:
    def test_create_and_get_draft(self, service):
        candidates = [
            {"field_name": "name", "raw_text": "My Account", "proposed_value": "My Account", "confidence": 0.9},
            {"field_name": "base_currency", "raw_text": "USD", "proposed_value": "USD", "confidence": 0.95},
        ]
        import_id = service.create_draft(
            target_kind=ImportTargetKind.ACCOUNT,
            source_type="screenshot",
            source_ref="test_screenshot.png",
            candidates_data=candidates
        )

        draft = service.get_draft(import_id)
        assert draft is not None
        assert draft.import_id == import_id
        assert draft.target_kind == ImportTargetKind.ACCOUNT
        assert len(draft.candidates) == 2
        assert draft.status == ImportDraftStatus.PENDING

        # Verify candidate values
        names = {c.field_name for c in draft.candidates}
        assert names == {"name", "base_currency"}

    def test_update_candidate_and_mark_reviewed(self, service):
        candidates = [
            {"field_name": "name", "raw_text": "My Accoutn", "proposed_value": "My Accoutn", "confidence": 0.7},
            {"field_name": "base_currency", "raw_text": "USD", "proposed_value": "USD", "confidence": 0.99},
        ]
        import_id = service.create_draft(
            target_kind=ImportTargetKind.ACCOUNT,
            source_type="screenshot",
            source_ref="test.png",
            candidates_data=candidates
        )

        draft = service.get_draft(import_id)
        c_name = next(c for c in draft.candidates if c.field_name == "name")
        c_curr = next(c for c in draft.candidates if c.field_name == "base_currency")

        # Accept currency
        service.update_candidate(c_curr.candidate_id, ReviewStatus.ACCEPTED)

        # Correction needed for name
        service.update_candidate(c_name.candidate_id, ReviewStatus.CORRECTED, corrected_value="My Account")

        # Mark as reviewed
        service.mark_reviewed(import_id)

        draft_rev = service.get_draft(import_id)
        assert draft_rev.status == ImportDraftStatus.REVIEWED

        # Generate preview
        preview = service.generate_preview(import_id)
        assert preview["payload"]["name"] == "My Account"
        assert preview["payload"]["base_currency"] == "USD"
        # name was low confidence (0.7)
        assert "name" in preview["needs_attention"]

    def test_validation_missing_required_fields(self, service):
        candidates = [
            {"field_name": "name", "proposed_value": "My Account", "confidence": 0.9},
        ]
        # Missing base_currency for ACCOUNT
        import_id = service.create_draft(
            target_kind=ImportTargetKind.ACCOUNT,
            source_type="screenshot",
            source_ref="test.png",
            candidates_data=candidates
        )

        draft = service.get_draft(import_id)
        service.update_candidate(draft.candidates[0].candidate_id, ReviewStatus.ACCEPTED)

        with pytest.raises(ValueError, match="Missing required field: base_currency"):
            service.mark_reviewed(import_id)

    def test_validation_unreviewed_fields(self, service):
        candidates = [
            {"field_name": "name", "proposed_value": "My Account", "confidence": 0.9},
            {"field_name": "base_currency", "proposed_value": "USD", "confidence": 0.9},
        ]
        import_id = service.create_draft(
            target_kind=ImportTargetKind.ACCOUNT,
            source_type="screenshot",
            source_ref="test.png",
            candidates_data=candidates
        )

        # Only one reviewed
        draft = service.get_draft(import_id)
        service.update_candidate(draft.candidates[0].candidate_id, ReviewStatus.ACCEPTED)

        with pytest.raises(ValueError, match="Field base_currency is unreviewed"):
            service.mark_reviewed(import_id)

    def test_sensitive_data_protection(self, service):
        # 1. Reject bank card in raw_text
        bad_candidates = [
            {"field_name": "notes", "raw_text": "Card number 622202123456789012", "proposed_value": "notes"}
        ]
        with pytest.raises(ValueError, match="contains sensitive data in raw_text"):
            service.create_draft(ImportTargetKind.ACCOUNT, "screenshot", "test.png", bad_candidates)

        # 2. Masking of long numbers
        ok_candidates = [
            {"field_name": "notes", "raw_text": "Reference 12345678901234", "proposed_value": "notes"}
        ]
        import_id = service.create_draft(ImportTargetKind.ACCOUNT, "screenshot", "test.png", ok_candidates)
        draft = service.get_draft(import_id)
        assert draft.candidates[0].raw_text == "Reference **********1234"

    def test_illegal_status_transitions(self, service):
        candidates = [
            {"field_name": "name", "proposed_value": "A", "confidence": 1.0},
            {"field_name": "base_currency", "proposed_value": "CNY", "confidence": 1.0},
        ]
        import_id = service.create_draft(ImportTargetKind.ACCOUNT, "screenshot", "ref", candidates)

        # 1. Preview before review
        with pytest.raises(PortfolioBookError, match="Only reviewed drafts"):
            service.generate_preview(import_id)

        # 2. Reject then try to review
        service.reject_draft(import_id)
        with pytest.raises(PortfolioBookError, match="already in rejected status"):
            service.mark_reviewed(import_id)

        # 3. Update candidate of non-pending draft
        draft = service.get_draft(import_id)
        with pytest.raises(PortfolioBookError, match="Cannot update candidate for draft in rejected status"):
            service.update_candidate(draft.candidates[0].candidate_id, ReviewStatus.ACCEPTED)

    def test_position_validation(self, service):
        # Position needs quantity OR market_value
        candidates = [
            {"field_name": "account_id", "proposed_value": "acc1", "confidence": 1.0},
            {"field_name": "product_id", "proposed_value": "prod1", "confidence": 1.0},
            {"field_name": "currency", "proposed_value": "CNY", "confidence": 1.0},
        ]
        import_id = service.create_draft(ImportTargetKind.POSITION, "test", "ref", candidates)
        draft = service.get_draft(import_id)
        for c in draft.candidates:
            service.update_candidate(c.candidate_id, ReviewStatus.ACCEPTED)

        with pytest.raises(ValueError, match="Position must have at least one of quantity or market_value"):
            service.mark_reviewed(import_id)
