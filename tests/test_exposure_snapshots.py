import pytest
import sqlite3
from decimal import Decimal
from pathlib import Path
from src.core.portfolio_book_db import PortfolioBookDatabase, PortfolioBookError
from src.domain.products import ProductDefinition
from src.domain.exposures import ExposureBatch, ExposureEntry, ExposureDimension, ExposureMethod, ExposureStatus, ExposureQuality
from src.services.portfolio_book_service import PortfolioBookService

@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_exposures.sqlite"
    db = PortfolioBookDatabase(db_path)
    db.initialize()
    # Create a test product
    db.create_product(ProductDefinition(product_id="P1", name="Test Product", product_type="bank_wmp"))
    return db

def test_exposure_batch_validation():
    # 1. Reject weight > 100%
    with pytest.raises(ValueError, match="exceeds 1.0"):
        ExposureBatch(
            batch_id="B1", product_id="P1", as_of="2026-06-01", known_at="2026-06-01",
            entries=[
                ExposureEntry(dimension=ExposureDimension.ASSET_CLASS, bucket="equity", weight=Decimal("0.7")),
                ExposureEntry(dimension=ExposureDimension.ASSET_CLASS, bucket="fixed_income", weight=Decimal("0.4"))
            ]
        )

    # 2. Accept weight == 100%
    batch = ExposureBatch(
        batch_id="B2", product_id="P1", as_of="2026-06-01", known_at="2026-06-01",
        entries=[
            ExposureEntry(dimension=ExposureDimension.ASSET_CLASS, bucket="equity", weight=Decimal("0.6")),
            ExposureEntry(dimension=ExposureDimension.ASSET_CLASS, bucket="fixed_income", weight=Decimal("0.4"))
        ]
    )
    assert batch.get_residual(ExposureDimension.ASSET_CLASS) == Decimal("0")

    # 3. Independent sums for different dimensions
    batch = ExposureBatch(
        batch_id="B3", product_id="P1", as_of="2026-06-01", known_at="2026-06-01",
        entries=[
            ExposureEntry(dimension=ExposureDimension.ASSET_CLASS, bucket="equity", weight=Decimal("1.0")),
            ExposureEntry(dimension=ExposureDimension.CURRENCY, bucket="USD", weight=Decimal("1.0"))
        ]
    )
    assert batch.get_residual(ExposureDimension.ASSET_CLASS) == Decimal("0")
    assert batch.get_residual(ExposureDimension.CURRENCY) == Decimal("0")

def test_exposure_crud(db):
    batch = ExposureBatch(
        batch_id="B1", product_id="P1", as_of="2026-06-01", known_at="2026-06-01",
        entries=[
            ExposureEntry(dimension=ExposureDimension.ASSET_CLASS, bucket="equity", weight=Decimal("0.6"), method=ExposureMethod.REPORTED),
            ExposureEntry(dimension=ExposureDimension.ASSET_CLASS, bucket="fixed_income", weight=Decimal("0.3"), method=ExposureMethod.REPORTED)
        ],
        notes="Test Batch"
    )

    db.create_exposure_batch(batch)
    fetched = db.get_exposure_batch("B1")

    assert fetched.batch_id == "B1"
    assert len(fetched.entries) == 2
    assert fetched.get_residual(ExposureDimension.ASSET_CLASS) == Decimal("0.1")
    assert fetched.notes == "Test Batch"

def test_exposure_immutability(db):
    db.create_exposure_batch(ExposureBatch(
        batch_id="B1", product_id="P1", as_of="2026-06-01", known_at="2026-06-01"
    ))
    db.confirm_exposure_batch("B1")

    # Try to confirm again
    with pytest.raises(PortfolioBookError, match="Cannot confirm confirmed batch"):
        db.confirm_exposure_batch("B1")

    # In SQLite, the table is not strictly immutable but the business logic prevents modification
    # Actually, the DB layer should prevent re-confirmation or modification if we had update_exposure_batch.
    # Currently we only have create_exposure_batch.

def test_effective_exposure_point_in_time(db):
    # Batch 1: Earlier as_of, earlier known_at
    db.create_exposure_batch(ExposureBatch(
        batch_id="B1", product_id="P1", as_of="2026-01-01", known_at="2026-01-01",
        status=ExposureStatus.CONFIRMED
    ))

    # Batch 2: Later as_of, later known_at
    db.create_exposure_batch(ExposureBatch(
        batch_id="B2", product_id="P1", as_of="2026-02-01", known_at="2026-02-01",
        status=ExposureStatus.CONFIRMED
    ))

    # Batch 3: Same as_of as B2, but later known_at (correction)
    db.create_exposure_batch(ExposureBatch(
        batch_id="B3", product_id="P1", as_of="2026-02-01", known_at="2026-02-15",
        status=ExposureStatus.CONFIRMED
    ))

    # 1. Query for 2026-01-15 known at 2026-01-15 -> Should get B1
    eff = db.get_effective_exposure("P1", "2026-01-15", "2026-01-15")
    assert eff.batch_id == "B1"

    # 2. Query for 2026-02-15 known at 2026-02-05 -> Should get B2 (B3 not known yet)
    eff = db.get_effective_exposure("P1", "2026-02-15", "2026-02-05")
    assert eff.batch_id == "B2"

    # 3. Query for 2026-02-15 known at 2026-02-20 -> Should get B3 (Correction)
    eff = db.get_effective_exposure("P1", "2026-02-15", "2026-02-20")
    assert eff.batch_id == "B3"

def test_exposure_batch_cascade_delete(db):
    db.create_exposure_batch(ExposureBatch(
        batch_id="B1", product_id="P1", as_of="2026-06-01", known_at="2026-06-01",
        entries=[ExposureEntry(dimension="asset_class", bucket="equity", weight=Decimal("1.0"))]
    ))

    conn = db.connect()
    count = conn.execute("SELECT COUNT(*) FROM product_exposures WHERE exposure_batch_id='B1'").fetchone()[0]
    assert count == 1

    conn.execute("DELETE FROM exposure_batches WHERE exposure_batch_id='B1'")
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM product_exposures WHERE exposure_batch_id='B1'").fetchone()[0]
    assert count == 0
    conn.close()

def test_ppm_roundtrip():
    # Test precision
    entry = ExposureEntry.from_ppm(123456, "dim", "buck")
    assert entry.weight == Decimal("0.123456")
    assert entry.to_ppm() == 123456

    # Test rounding
    entry2 = ExposureEntry(dimension="dim", bucket="buck", weight=Decimal("0.1234567"))
    assert entry2.to_ppm() == 123457 # Round to nearest PPM

def test_exposure_service(db):
    service = PortfolioBookService(db)

    # 1. Create Exposure Batch via service
    batch_data = {
        'exposure_batch_id': 'B_SERVICE',
        'product_id': 'P1',
        'as_of': '2026-06-01',
        'known_at': '2026-06-01T12:00:00',
        'entries': [
            {'dimension': 'asset_class', 'bucket': 'equity', 'weight': 0.6, 'method': 'reported'},
            {'dimension': 'asset_class', 'bucket': 'fixed_income', 'weight': 0.3, 'method': 'reported'}
        ],
        'quality': 'reported',
        'notes': 'Service Batch'
    }

    res = service.create_exposure_batch(batch_data)
    assert res["success"] is True
    assert res["data"]["unknown_residuals"]["asset_class"] == 0.1

    # 2. Get batch
    res = service.get_exposure_batch('B_SERVICE')
    assert res["success"] is True
    assert res["data"]["notes"] == 'Service Batch'

    # 3. Confirm
    res = service.confirm_exposure_batch('B_SERVICE')
    assert res["success"] is True

    # 4. Effective exposure
    res = service.get_effective_exposure('P1', '2026-06-05')
    assert res["success"] is True
    assert res["data"]["exposure_batch_id"] == 'B_SERVICE'

    # 5. Invalid data validation
    invalid_data = batch_data.copy()
    invalid_data['exposure_batch_id'] = 'B_INVALID'
    invalid_data['entries'] = [{'dimension': 'asset_class', 'bucket': 'equity', 'weight': 1.1}]

    res = service.create_exposure_batch(invalid_data)
    assert res["success"] is False
    assert res["error_code"] == "VALIDATION_ERROR"

def test_exposure_service_pii(db):
    service = PortfolioBookService(db)
    batch_data = {
        'exposure_batch_id': 'B_PII',
        'product_id': 'P1',
        'as_of': '2026-06-01',
        'known_at': '2026-06-01T12:00:00',
        'entries': [],
        'password': 'secret_password' # PII
    }
    res = service.create_exposure_batch(batch_data)
    assert res["success"] is False
    assert res["error_code"] == "PII_REJECTED"
