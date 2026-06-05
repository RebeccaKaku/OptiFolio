"""Tests for Ghostfolio-compatible API adapter."""

import pytest
from fastapi.testclient import TestClient
from src.api.fastapi_app import app

client = TestClient(app)


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


def test_ghostfolio_dividends():
    response = client.get("/api/v1/portfolio/dividends")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_ghostfolio_investments():
    response = client.get("/api/v1/portfolio/investments")
    assert response.status_code == 200
    data = response.json()
    assert "investments" in data
    assert "streaks" in data
    assert isinstance(data["investments"], list)


def test_ghostfolio_report():
    response = client.get("/api/v1/portfolio/report")
    assert response.status_code == 200
    data = response.json()
    assert "xRay" in data
