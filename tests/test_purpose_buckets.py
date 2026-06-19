import pytest
import uuid
from src.core.portfolio_book_db import PortfolioBookDatabase, PortfolioBookError
from src.services.portfolio_book_service import PortfolioBookService
from src.domain.products import ProductDefinition

@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_book.sqlite"
    db = PortfolioBookDatabase(db_path)
    db.initialize()
    return db

@pytest.fixture
def service(db):
    return PortfolioBookService(db)

def test_bucket_crud(service):
    # Create
    res = service.create_bucket({
        "bucket_id": "core",
        "name": "Core Savings",
        "bucket_type": "core",
        "base_currency": "CNY",
        "risk_notes": "Very safe"
    })
    assert res["success"]
    assert res["data"]["bucket_id"] == "core"

    # List
    res = service.list_buckets()
    assert res["success"]
    assert len(res["data"]) == 1
    assert res["data"][0]["bucket_id"] == "core"

    # Get
    res = service.get_bucket("core")
    assert res["success"]
    assert res["data"]["name"] == "Core Savings"

    # Update
    res = service.update_bucket("core", {"name": "Main Savings", "liquidity_horizon_days": 365})
    assert res["success"]
    assert res["data"]["name"] == "Main Savings"
    assert res["data"]["liquidity_horizon_days"] == 365

    # Deactivate
    res = service.deactivate_bucket("core")
    assert res["success"]
    assert res["data"]["status"] == "inactive"

    # List active
    res = service.list_buckets(status="active")
    assert len(res["data"]) == 0

    # List all
    res = service.list_buckets(status="all")
    assert len(res["data"]) == 1

def test_allocation_ppm_validation(service, db):
    # Setup: Bucket, Account, Product, Confirmed Batch with position
    service.create_bucket({"bucket_id": "b1", "name": "B1", "bucket_type": "core"})
    db.create_account("acc1", "Acc 1")

    db.create_product(ProductDefinition("prod1", "Prod 1", "deposit"))

    batch_id = "batch1"
    db.create_snapshot_batch(batch_id, "2024-01-01")
    db.set_batch_account_coverage(batch_id, "acc1", "complete")
    db.add_snapshot(batch_id, "acc1", "prod1", quantity=100.0)
    db.confirm_batch(batch_id)

    # Set allocation
    res = service.set_position_bucket_allocation(batch_id, "acc1", "prod1", {
        "bucket_id": "b1",
        "allocation_ppm": 600000,
        "notes": "part 1"
    })
    assert res["success"]

    # Try exceeding 1M
    res = service.set_position_bucket_allocation(batch_id, "acc1", "prod1", {
        "bucket_id": "b3", # Non-existent bucket
        "allocation_ppm": 500000
    })
    assert not res["success"]
    assert "not found" in res["error"].lower()

    service.create_bucket({"bucket_id": "b2", "name": "B2", "bucket_type": "learning"})
    res = service.set_position_bucket_allocation(batch_id, "acc1", "prod1", {
        "bucket_id": "b2",
        "allocation_ppm": 500000
    })
    assert not res["success"]
    assert "exceeds 1,000,000" in res["error"]

    # Update existing to stay within 1M
    res = service.set_position_bucket_allocation(batch_id, "acc1", "prod1", {
        "bucket_id": "b1",
        "allocation_ppm": 400000
    })
    assert res["success"]

    res = service.set_position_bucket_allocation(batch_id, "acc1", "prod1", {
        "bucket_id": "b2",
        "allocation_ppm": 500000
    })
    assert res["success"]

    # Check residuals
    res = service.get_position_bucket_allocations(batch_id, "acc1", "prod1")
    assert res["success"]
    assert res["data"]["total_ppm"] == 900000
    assert res["data"]["unassigned_ppm"] == 100000
    assert len(res["data"]["allocations"]) == 2

def test_allocation_constraints(service, db):
    service.create_bucket({"bucket_id": "b1", "name": "B1", "bucket_type": "core"})
    db.create_account("acc1", "Acc 1")
    db.create_product(ProductDefinition("prod1", "Prod 1", "deposit"))

    batch_id = "draft_batch"
    db.create_snapshot_batch(batch_id, "2024-01-01")
    db.set_batch_account_coverage(batch_id, "acc1", "complete")
    db.add_snapshot(batch_id, "acc1", "prod1", quantity=100.0)

    # Reject allocation to draft batch
    res = service.set_position_bucket_allocation(batch_id, "acc1", "prod1", {
        "bucket_id": "b1",
        "allocation_ppm": 100000
    })
    assert not res["success"]
    assert "confirmed" in res["error"].lower()

    db.confirm_batch(batch_id)

    # Reject allocation to inactive bucket
    service.deactivate_bucket("b1")
    res = service.set_position_bucket_allocation(batch_id, "acc1", "prod1", {
        "bucket_id": "b1",
        "allocation_ppm": 100000
    })
    assert not res["success"]
    assert "inactive" in res["error"].lower()

def test_pii_rejection(service):
    res = service.create_bucket({
        "bucket_id": "b1",
        "name": "B1",
        "bucket_type": "core",
        "bank_card": "1234"
    })
    assert not res["success"]
    assert "PII_REJECTED" in res["error_code"]
