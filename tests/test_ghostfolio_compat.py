"""Tests for Ghostfolio-compatible API adapter."""

import os
# Isolate tests from local developer portfolio files
os.environ["OPTIFOLIO_PORTFOLIO_PATH"] = "nonexistent_portfolio_config_for_testing.yaml"

from datetime import date, datetime
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from src.api.fastapi_app import app
from src.services import get_application_services
client = TestClient(app)


@pytest.fixture
def mock_ghostfolio_data():
    """Seed the SQLite portfolio book so PortfolioServiceV2 can load holdings.

    The database MUST be seeded before ``get_application_services()`` is
    called, because ``PortfolioServiceV2._load_portfolio()`` runs during
    construction and reads the latest confirmed batch.

    Strategy: the *latest* batch contains only cash (no price lookup needed),
    so ``get_value()`` succeeds without market data.  Earlier batches carry
    TEST_ASSET snapshots for the dividend and investment timeline tests.
    """
    from src.core.portfolio_book_db import PortfolioBookDatabase
    from src.domain.products import ProductDefinition

    # 0. Clear cached service graph so PortfolioServiceV2 picks up our data
    get_application_services.cache_clear()

    # 1. Seed the database FIRST
    db = PortfolioBookDatabase()
    db.initialize()

    try:
        db.create_account(account_id="acc1", name="Test Account", base_currency="USD")
    except Exception:
        pass

    for pid, name, ptype, curr in [
        ("TEST_ASSET", "Test Asset", "stock", "USD"),
        ("CNY_CASH", "CNY Cash", "deposit", "CNY"),
    ]:
        try:
            db.create_product(ProductDefinition(
                product_id=pid, name=name, product_type=ptype,
                currency=curr, data_source="manual",
            ))
        except Exception:
            pass

    # Batch A (earlier) — TEST_ASSET for investments / dividends
    batch_a = "batch_20250101"
    try:
        db.create_snapshot_batch(batch_id=batch_a, as_of="2025-01-01")
        db.set_batch_account_coverage(batch_id=batch_a, account_id="acc1", coverage="complete")
        db.add_snapshot(
            batch_id=batch_a, account_id="acc1", product_id="TEST_ASSET",
            quantity=100.0, cost_basis=1000.0, currency="USD",
        )
        db.confirm_batch(batch_a)
    except Exception:
        pass

    # Batch B (earlier) — second data point for streak calculation
    batch_b = "batch_20250201"
    try:
        db.create_snapshot_batch(batch_id=batch_b, as_of="2025-02-01")
        db.set_batch_account_coverage(batch_id=batch_b, account_id="acc1", coverage="complete")
        db.add_snapshot(
            batch_id=batch_b, account_id="acc1", product_id="TEST_ASSET",
            quantity=100.0, cost_basis=1100.0, currency="USD",
        )
        db.confirm_batch(batch_b)
    except Exception:
        pass

    # Batch C (latest) — cash only, so get_value() succeeds without market data.
    # Use today's date so it sorts AFTER any pre-existing dev batches
    # and becomes the batch that PortfolioServiceV2._load_portfolio() picks up.
    from datetime import date as _date
    batch_c = "batch_test_latest"
    try:
        db.create_snapshot_batch(batch_id=batch_c, as_of=_date.today().isoformat())
        db.set_batch_account_coverage(batch_id=batch_c, account_id="acc1", coverage="complete")
        db.add_snapshot(
            batch_id=batch_c, account_id="acc1", product_id="CNY_CASH",
            quantity=10000.0, currency="CNY",
        )
        db.confirm_batch(batch_c)
    except Exception:
        pass

    # 2. NOW create services — PortfolioServiceV2 loads from seeded DB
    services = get_application_services()

    # 3. Record a dividend
    services.portfolio_v2.record_dividend(
        asset_id="TEST_ASSET",
        ex_date=date(2025, 1, 1),
        amount_per_share=1.5,
        currency="USD",
    )

    yield

    # Cleanup
    ca_path = "local/corporate_actions.yaml"
    if os.path.exists(ca_path):
        os.remove(ca_path)


def test_ghostfolio_details(mock_ghostfolio_data):
    response = client.get("/api/v1/portfolio/details")
    assert response.status_code == 200
    data = response.json()
    assert "accounts" in data
    assert "holdings" in data
    assert "summary" in data
    assert "hasError" in data
    assert data["hasError"] is False

    summary = data["summary"]
    assert "currentNetWorth" in summary
    assert "totalInvestment" in summary


def test_ghostfolio_performance():
    response = client.get("/api/v1/portfolio/performance")
    assert response.status_code == 200
    data = response.json()
    assert "chart" in data
    assert "performance" in data

    performance = data["performance"]
    assert "currentNetWorth" in performance
    assert "totalInvestment" in performance


def test_ghostfolio_holdings():
    response = client.get("/api/v1/portfolio/holdings")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        holding = data[0]
        assert "symbol" in holding
        assert "quantity" in holding
        assert "marketPrice" in holding
        assert "assetClass" in holding


def test_ghostfolio_dividends(mock_ghostfolio_data):
    response = client.get("/api/v1/portfolio/dividends")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    div = data[0]
    assert "symbol" in div
    assert "date" in div
    assert "amount" in div
    assert "currency" in div
    assert any(d["symbol"] == "TEST_ASSET" for d in data)


def test_ghostfolio_investments(mock_ghostfolio_data):
    response = client.get("/api/v1/portfolio/investments")
    assert response.status_code == 200
    data = response.json()
    assert "investments" in data
    assert "streaks" in data
    assert isinstance(data["investments"], list)
    assert len(data["investments"]) >= 2
    inv = data["investments"][0]
    assert "date" in inv
    assert "investment" in inv
    assert data["streaks"]["longestStreak"] >= 2


def test_ghostfolio_report():
    response = client.get("/api/v1/portfolio/report")
    assert response.status_code == 200
    data = response.json()
    assert "xRay" in data
    xray = data["xRay"]
    assert "categories" in xray
    assert "statistics" in xray
    if len(xray["categories"]) > 0:
        cat = xray["categories"][0]
        assert "name" in cat
        assert "value" in cat
        assert "percentage" in cat
        assert "assetIds" in cat
