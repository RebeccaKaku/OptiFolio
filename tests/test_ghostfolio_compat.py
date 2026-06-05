"""Tests for Ghostfolio-compatible API adapter."""

import os
from datetime import date, datetime
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from src.api.fastapi_app import app
from src.services import get_application_services
from FinData.store.portfolio_ledger import PortfolioLedgerStore, PortfolioLedger

client = TestClient(app)


@pytest.fixture
def mock_ghostfolio_data():
    services = get_application_services()

    # 1. Record a dividend
    services.portfolio_v2.record_dividend(
        asset_id="TEST_ASSET",
        ex_date=date(2025, 1, 1),
        amount_per_share=1.5,
        currency="USD"
    )

    # 2. Add ledger entries for investments
    real_path = "data/gold/portfolio_ledger.parquet"
    backup_path = "data/gold/portfolio_ledger.parquet.bak"
    has_backup = False
    if os.path.exists(real_path):
        os.rename(real_path, backup_path)
        has_backup = True

    os.makedirs(os.path.dirname(real_path), exist_ok=True)
    entries = [
        PortfolioLedger(
            account_id="acc1",
            asset_id="TEST_ASSET",
            quantity=100.0,
            cost_basis=1000.0,
            currency="USD",
            as_of=datetime(2025, 1, 1)
        ),
        PortfolioLedger(
            account_id="acc1",
            asset_id="TEST_ASSET",
            quantity=100.0,
            cost_basis=1100.0,
            currency="USD",
            as_of=datetime(2025, 2, 1)
        )
    ]
    pd.DataFrame([vars(e) for e in entries]).to_parquet(real_path)

    yield

    # Cleanup
    if os.path.exists(real_path):
        os.remove(real_path)
    if has_backup:
        os.rename(backup_path, real_path)

    ca_path = "local/corporate_actions.yaml"
    if os.path.exists(ca_path):
        os.remove(ca_path)


def test_ghostfolio_details():
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
