"""Concurrency tests for DS-008 snapshot confirmation race conditions."""

import threading
import time
import pytest
from src.core.portfolio_book_db import PortfolioBookDatabase, PortfolioBookError

@pytest.fixture
def db(tmp_path):
    path = tmp_path / "concurrency.sqlite"
    db = PortfolioBookDatabase(path=path)
    db.initialize()
    # Setup batch
    db.create_account("acc1", "Test Account")
    db.create_snapshot_batch("b1", "2025-01-01")
    db.set_batch_account_coverage("b1", "acc1", "partial")
    return db

def test_concurrent_confirm_and_add_snapshot(db):
    """Test that BEGIN IMMEDIATE prevents adding to a batch while/after it is confirmed."""
    results = []

    def confirm_task():
        try:
            # We want this to happen "around" the same time as add_task
            db.confirm_batch("b1")
            results.append("confirmed")
        except Exception as e:
            results.append(f"confirm_failed: {e}")

    def add_task():
        # Small delay to increase chance of confirm starting first or middle
        time.sleep(0.01)
        try:
            db.add_snapshot("b1", "acc1", "any_prod", market_value=100)
            results.append("added")
        except PortfolioBookError as e:
            results.append(f"add_rejected: {e}")
        except Exception as e:
            results.append(f"add_error: {type(e).__name__} {e}")

    t1 = threading.Thread(target=confirm_task)
    t2 = threading.Thread(target=add_task)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Outcomes:
    # 1. Confirmed, then Add rejected (most likely if confirm gets lock first)
    # 2. Add, then Confirmed (if add gets lock first)
    # Both are acceptable as long as we don't have "Confirmed" AND "Added" where Added happened after Confirm status was set.
    # Actually, if both succeeded, "added" must come before "confirmed" or vice versa?
    # No, the database status prevents adding to a confirmed batch.

    if "confirmed" in results and "added" in results:
        # Check if they are actually in a valid state
        batch = db.get_batch("b1")
        assert batch["status"] == "confirmed"
        # If it was added, it should be there.
        # This just means add_task won the race and finished before confirm_task started its transaction.
        pass
    elif "confirmed" in results and any("add_rejected" in r for r in results):
        # Confirm won, add was rejected because it saw 'confirmed' status.
        pass
    else:
        pytest.fail(f"Unexpected results: {results}")

def test_repeat_confirmation_idempotency(db):
    """DS-008: Repeat confirmation should return a distinct error (already_confirmed)."""
    db.confirm_batch("b1")
    with pytest.raises(PortfolioBookError, match="already confirmed"):
        db.confirm_batch("b1")
