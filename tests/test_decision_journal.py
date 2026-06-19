import pytest
import os
import uuid
from datetime import datetime, timedelta
from src.core.portfolio_book_db import PortfolioBookDatabase
from src.services.decision_journal_service import DecisionJournalService
from src.domain.decision_journal import DecisionStatus, AuthorType
from src.domain.products import ProductDefinition

@pytest.fixture
def db():
    db_path = f"local/test_decision_journal_{uuid.uuid4()}.sqlite"
    db = PortfolioBookDatabase(path=db_path)
    db.initialize()
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.fixture
def svc(db):
    return DecisionJournalService(db)

def test_create_decision_full(svc, db):
    db.create_account("acc1", "Test Account")
    prod = ProductDefinition(
        product_id="prod1",
        name="Test Product",
        product_type="stock",
        currency="CNY",
        data_source="manual",
        metadata={}
    )
    db.create_product(prod)
    db.create_snapshot_batch("batch1", "2026-06-01")

    data = {
        "title": "Buy Apple",
        "decision_type": "investment",
        "as_of": "2026-06-01",
        "account_id": "acc1",
        "product_id": "prod1",
        "snapshot_batch_id": "batch1",
        "thesis": "Apple is good",
        "baseline": "P/E 20",
        "invalidation_conditions": "P/E > 30",
        "review_at": "2026-12-01",
        "evidence": [{"source": "news", "content": "iPhone 18 launch"}],
        "scenarios": [{"name": "bull", "outcome": "+20%"}],
    }

    result = svc.create_decision(data)
    assert result["success"] is True
    decision_id = result["decision_id"]

    # Verify decision
    res = svc.get_decision(decision_id)
    assert res["success"] is True
    d = res["decision"]
    assert d["title"] == "Buy Apple"
    assert d["account_id"] == "acc1"
    assert len(d["revisions"]) == 1
    rev = d["revisions"][0]
    assert rev["thesis"] == "Apple is good"
    assert rev["revision_no"] == 1
    assert rev["evidence"][0]["source"] == "news"

def test_append_revision(svc, db):
    data = {
        "title": "Buy Apple",
        "decision_type": "investment",
        "as_of": "2026-06-01",
        "thesis": "Apple is good",
        "baseline": "P/E 20",
        "invalidation_conditions": "P/E > 30",
        "review_at": "2026-12-01"
    }
    res = svc.create_decision(data)
    decision_id = res["decision_id"]

    rev_data = {
        "thesis": "Apple is still good, but more expensive",
        "baseline": "P/E 25",
        "invalidation_conditions": "P/E > 35",
        "review_at": "2027-01-01",
        "author_type": AuthorType.AI
    }
    res = svc.append_revision(decision_id, rev_data)
    assert res["success"] is True
    assert res["revision_no"] == 2

    res = svc.get_decision(decision_id)
    assert len(res["decision"]["revisions"]) == 2
    assert res["decision"]["revisions"][1]["author_type"] == "ai"

def test_mark_status(svc, db):
    data = {
        "title": "Test Decision",
        "decision_type": "other",
        "as_of": "2026-06-01",
        "thesis": "Thesis",
        "baseline": "Baseline",
        "invalidation_conditions": "Invalid if X",
        "review_at": "2026-12-01"
    }
    res = svc.create_decision(data)
    decision_id = res["decision_id"]

    svc.mark_status(decision_id, DecisionStatus.CLOSED)
    res = svc.get_decision(decision_id)
    assert res["decision"]["status"] == "closed"

def test_reviews_due(svc, db):
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Due yesterday
    svc.create_decision({
        "title": "Due Yesterday", "decision_type": "other", "as_of": "2026-06-01",
        "thesis": "T1", "baseline": "B1", "invalidation_conditions": "I1", "review_at": yesterday
    })
    # Due today
    svc.create_decision({
        "title": "Due Today", "decision_type": "other", "as_of": "2026-06-01",
        "thesis": "T2", "baseline": "B2", "invalidation_conditions": "I2", "review_at": today
    })
    # Due tomorrow
    svc.create_decision({
        "title": "Due Tomorrow", "decision_type": "other", "as_of": "2026-06-01",
        "thesis": "T3", "baseline": "B3", "invalidation_conditions": "I3", "review_at": tomorrow
    })

    res = svc.list_reviews_due(as_of=today)
    assert len(res["decisions"]) == 2
    titles = [d["title"] for d in res["decisions"]]
    assert "Due Yesterday" in titles
    assert "Due Today" in titles
    assert "Due Tomorrow" not in titles

def test_invalid_references(svc, db):
    data = {
        "title": "Bad Ref",
        "decision_type": "investment",
        "as_of": "2026-06-01",
        "account_id": "nonexistent",
        "thesis": "T", "baseline": "B", "invalidation_conditions": "I", "review_at": "2026-12-01"
    }
    res = svc.create_decision(data)
    assert res["success"] is False
    assert res["error_code"] == "FOREIGN_KEY_ERROR"
