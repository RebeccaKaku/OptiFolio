"""Tests for product exposure snapshots (DS-016)."""

import pytest
from pathlib import Path
from src.core.portfolio_book_db import PortfolioBookDatabase, PortfolioBookError
from src.services.portfolio_book_service import PortfolioBookService
from src.domain.products import ProductDefinition

@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_exposures.sqlite"
    db = PortfolioBookDatabase(db_path)
    db.initialize()
    return db

@pytest.fixture
def svc(db):
    return PortfolioBookService(db)

@pytest.fixture
def sample_product(db):
    p = ProductDefinition(
        product_id="test-p",
        name="Test Product",
        product_type="bank_wmp",
        currency="CNY"
    )
    db.create_product(p)
    return p

def test_exposure_batch_crud(svc, sample_product):
    # 1. Create batch
    res = svc.create_exposure_batch({
        "batch_id": "b1",
        "product_id": sample_product.product_id,
        "as_of": "2026-06-01",
        "known_at": "2026-06-02",
        "notes": "Test batch"
    })
    assert res["success"]
    assert res["data"]["exposure_batch_id"] == "b1"
    assert res["data"]["status"] == "draft"

    # 2. Add exposures
    svc.add_product_exposure("b1", {
        "dimension": "asset_class",
        "bucket": "equity",
        "weight_ppm": 600000,
        "method": "reported"
    })
    svc.add_product_exposure("b1", {
        "dimension": "asset_class",
        "bucket": "fixed_income",
        "weight_ppm": 300000,
        "method": "reported"
    })

    # 3. Get batch and check residuals
    res = svc.get_exposure_batch("b1")
    assert res["success"]
    assert len(res["data"]["exposures"]) == 2
    # 1M - 0.6M - 0.3M = 0.1M
    assert res["data"]["unknown_residuals"]["asset_class"] == 100000

    # 4. Confirm batch
    res = svc.confirm_exposure_batch("b1")
    assert res["success"]

    res = svc.get_exposure_batch("b1")
    assert res["data"]["status"] == "confirmed"

def test_weight_sum_validation(svc, sample_product):
    svc.create_exposure_batch({
        "batch_id": "b-val",
        "product_id": sample_product.product_id,
        "as_of": "2026-06-01",
        "known_at": "2026-06-02"
    })

    # Add 0.7
    res = svc.add_product_exposure("b-val", {
        "dimension": "currency",
        "bucket": "USD",
        "weight_ppm": 700000
    })
    assert res["success"]

    # Try to add 0.4 -> total 1.1 > 1.0 -> should fail
    res = svc.add_product_exposure("b-val", {
        "dimension": "currency",
        "bucket": "CNY",
        "weight_ppm": 400000
    })
    assert not res["success"]
    assert "exceed 1,000,000" in res["error"]

def test_confirm_batch_immutability(svc, sample_product):
    svc.create_exposure_batch({
        "batch_id": "b-fixed",
        "product_id": sample_product.product_id,
        "as_of": "2026-06-01",
        "known_at": "2026-06-02"
    })
    svc.confirm_exposure_batch("b-fixed")

    res = svc.add_product_exposure("b-fixed", {
        "dimension": "region",
        "bucket": "US",
        "weight_ppm": 1000000
    })
    assert not res["success"]
    assert "Cannot add to confirmed batch" in res["error"]

def test_exposure_batch_not_found(svc):
    res = svc.get_exposure_batch("non-existent")
    assert not res["success"]
    assert res["error_code"] == "NOT_FOUND"

def test_unknown_residual_is_not_a_fake_exposure(svc, sample_product):
    svc.create_exposure_batch({
        "batch_id": "b-residual",
        "product_id": sample_product.product_id,
        "as_of": "2026-06-01",
        "known_at": "2026-06-02"
    })
    svc.add_product_exposure("b-residual", {
        "dimension": "asset_class",
        "bucket": "equity",
        "weight_ppm": 500000
    })

    batch = svc.get_exposure_batch("b-residual")["data"]
    assert len(batch["exposures"]) == 1
    assert "asset_class" in batch["unknown_residuals"]
    assert batch["unknown_residuals"]["asset_class"] == 500000

def test_db_level_constraints(db, sample_product):
    db.create_exposure_batch("db-1", sample_product.product_id, "2026-06-01", "2026-06-01")

    # Check weight_ppm range constraint
    with pytest.raises(Exception): # sqlite3.IntegrityError
        db.add_product_exposure("db-1", "asset_class", "equity", 1000001)

    with pytest.raises(Exception):
        db.add_product_exposure("db-1", "asset_class", "equity", -1)

def test_cascade_delete(db, sample_product):
    db.create_exposure_batch("db-del", sample_product.product_id, "2026-06-01", "2026-06-01")
    db.add_product_exposure("db-del", "asset_class", "equity", 1000000)

    # Verify it exists
    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM product_exposures WHERE exposure_batch_id='db-del'").fetchone()[0] == 1

    # Delete batch
    conn.execute("DELETE FROM exposure_batches WHERE exposure_batch_id='db-del'")
    conn.commit()

    # Verify exposures are gone
    assert conn.execute("SELECT COUNT(*) FROM product_exposures WHERE exposure_batch_id='db-del'").fetchone()[0] == 0
    conn.close()
