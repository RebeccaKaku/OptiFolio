import pytest
from datetime import datetime
from FinData.store.portfolio_ledger import PortfolioLedger, PortfolioLedgerStore
import pandas as pd
import os
from fastapi.testclient import TestClient
from src.api.fastapi_app import app

def test_ledger_dataclass():
    now = datetime.now()
    ledger = PortfolioLedger(
        account_id="test_account",
        asset_id="AAPL",
        quantity=10.0,
        cost_basis=150.0,
        currency="USD",
        as_of=now
    )
    assert ledger.account_id == "test_account"
    assert ledger.asset_id == "AAPL"
    assert ledger.quantity == 10.0
    assert ledger.cost_basis == 150.0
    assert ledger.currency == "USD"
    assert ledger.as_of == now

def test_ledger_store_save_load(tmp_path):
    storage_path = tmp_path / "test_ledger.parquet"
    store = PortfolioLedgerStore(storage_path=str(storage_path))

    now = datetime.now()
    entries = [
        PortfolioLedger("acc1", "AAPL", 10, 150, "USD", now),
        PortfolioLedger("acc1", "MSFT", 5, 300, "USD", now)
    ]

    store.save_entries(entries)
    assert storage_path.exists()

    loaded_df = store.load_entries()
    assert len(loaded_df) == 2
    assert "AAPL" in loaded_df['asset_id'].values
    assert "MSFT" in loaded_df['asset_id'].values

def test_ledger_api_endpoint():
    client = TestClient(app)
    # Ensure ledger is recorded first
    from tools.scheduler import record_portfolio_ledger
    record_portfolio_ledger()

    response = client.get("/api/portfolio/v2/ledger")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    assert isinstance(data["data"], list)
