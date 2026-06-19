"""Tests for DS-008: Snapshot draft and confirm API."""

import pytest
from fastapi.testclient import TestClient
from src.api.fastapi_app import create_app

@pytest.fixture
def client(tmp_path, monkeypatch):
    # Ensure a fresh database for each test
    monkeypatch.setenv("OPTIFOLIO_DB_PATH", str(tmp_path / "test_api.sqlite"))
    from src.services.application import get_application_services
    get_application_services.cache_clear()

    app = create_app()
    return TestClient(app)

def test_snapshot_workflow(client):
    # 1. Create draft batch
    batch_data = {
        "batch_id": "api_batch_001",
        "as_of": "2025-06-19",
        "notes": "API test batch"
    }
    resp = client.post("/api/book/snapshot-batches", json=batch_data)
    assert resp.status_code == 201
    assert resp.json()["data"]["batch_id"] == "api_batch_001"
    assert resp.json()["data"]["status"] == "draft"

    # 2. Create account and product for testing
    client.post("/api/book/accounts", json={"account_id": "acc_api", "name": "API Account"})
    client.post("/api/book/products", json={"product_id": "prod_api", "name": "API Product", "product_type": "fund"})

    # 3. Set coverage
    cov_data = {"coverage": "partial", "notes": "Work in progress"}
    resp = client.put("/api/book/snapshot-batches/api_batch_001/accounts/acc_api/coverage", json=cov_data)
    assert resp.status_code == 200

    # 4. Add position
    pos_data = {
        "account_id": "acc_api",
        "product_id": "prod_api",
        "market_value": 1000.0,
        "currency": "USD"
    }
    resp = client.post("/api/book/snapshot-batches/api_batch_001/positions", json=pos_data)
    assert resp.status_code == 201

    # 5. Validate
    resp = client.post("/api/book/snapshot-batches/api_batch_001/validate")
    assert resp.status_code == 200
    val = resp.json()["data"]
    assert val["is_confirmable"] is True
    assert val["is_complete"] is False # because partial
    assert len(val["warnings"]) > 0

    # 6. Confirm
    resp = client.post("/api/book/snapshot-batches/api_batch_001/confirm")
    assert resp.status_code == 200

    # 7. Verify immutable
    resp = client.post("/api/book/snapshot-batches/api_batch_001/positions", json=pos_data)
    assert resp.status_code == 500 # Database raises PortfolioBookError which we map to INTERNAL_ERROR for snapshots atm, but service says DATABASE_ERROR
    # Actually service maps it to failure(str(exc), error_code="DATABASE_ERROR")
    # And API maps DATABASE_ERROR to 500. Correct.

    # 8. Check progress
    resp = client.get("/api/book/snapshot-batches/api_batch_001")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "confirmed"
    assert resp.json()["data"]["progress"]["is_complete"] is False

def test_validate_empty_batch(client):
    client.post("/api/book/snapshot-batches", json={"batch_id": "empty_batch", "as_of": "2025-06-19"})
    resp = client.post("/api/book/snapshot-batches/empty_batch/validate")
    assert resp.status_code == 200
    assert resp.json()["data"]["is_confirmable"] is False
    assert "coverage" in resp.json()["data"]["errors"][0]

def test_confirm_already_confirmed(client):
    client.post("/api/book/snapshot-batches", json={"batch_id": "dup_confirm", "as_of": "2025-06-19"})
    client.post("/api/book/accounts", json={"account_id": "acc_dup", "name": "Dup Account"})
    client.put("/api/book/snapshot-batches/dup_confirm/accounts/acc_dup/coverage", json={"coverage": "complete"})

    resp = client.post("/api/book/snapshot-batches/dup_confirm/confirm")
    assert resp.status_code == 200

    resp = client.post("/api/book/snapshot-batches/dup_confirm/confirm")
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "ALREADY_CONFIRMED"
