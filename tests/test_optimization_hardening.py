import pytest
from fastapi.testclient import TestClient
from src.api.fastapi_app import create_app
from unittest.mock import MagicMock
import pandas as pd
from types import SimpleNamespace

@pytest.fixture
def client(monkeypatch):
    app = create_app()
    return TestClient(app)

def test_optimize_invalid_method(client, monkeypatch):
    response = client.post("/api/research/optimize", json={
        "assets": ["AAPL"],
        "method": "invalid_method"
    })
    assert response.status_code == 400
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "INVALID_OPTIMIZATION_METHOD"
    assert "Unknown method" in response.json()["error"]

def test_optimize_invalid_objective(client, monkeypatch):
    response = client.post("/api/research/optimize", json={
        "assets": ["AAPL"],
        "objective": "invalid_objective"
    })
    assert response.status_code == 400
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "INVALID_OPTIMIZATION_OBJECTIVE"
    assert "Invalid objective" in response.json()["error"]

def test_optimize_empty_assets(client):
    # Pydantic validation (min_length=1)
    response = client.post("/api/research/optimize", json={
        "assets": []
    })
    assert response.status_code == 422

def test_optimize_unknown_assets(client, monkeypatch):
    class FakeMarketData:
        def get_prices(self, assets, **kwargs):
            # Simulate unknown assets by returning empty DF if none of requested assets found
            return pd.DataFrame()

    from src.services.research_service import ResearchService
    research_service = ResearchService(market_data=FakeMarketData())
    fake_services = SimpleNamespace(research=research_service)
    monkeypatch.setattr("src.api.fastapi_app.get_application_services", lambda: fake_services)

    response = client.post("/api/research/optimize", json={
        "assets": ["UNKNOWN"]
    })
    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "OPTIMIZATION_NO_DATA"

def test_optimize_insufficient_assets(client, monkeypatch):
    class FakeMarketData:
        def get_prices(self, assets, **kwargs):
            # Return data for only some assets
            return pd.DataFrame({"AAPL": [100.0, 101.0]}, index=pd.date_range("2023-01-01", periods=2))

    from src.services.research_service import ResearchService
    research_service = ResearchService(market_data=FakeMarketData())
    fake_services = SimpleNamespace(research=research_service)
    monkeypatch.setattr("src.api.fastapi_app.get_application_services", lambda: fake_services)

    response = client.post("/api/research/optimize", json={
        "assets": ["AAPL", "UNKNOWN"]
    })
    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "OPTIMIZATION_INSUFFICIENT_ASSETS"
    assert "UNKNOWN" in response.json()["error"]

def test_optimize_insufficient_history(client, monkeypatch):
    class FakeMarketData:
        def get_prices(self, assets, **kwargs):
            # Only 1 day of data
            return pd.DataFrame([[100.0]], index=[pd.Timestamp("2023-01-01")], columns=assets)

    from src.services.research_service import ResearchService
    research_service = ResearchService(market_data=FakeMarketData())
    fake_services = SimpleNamespace(research=research_service)
    monkeypatch.setattr("src.api.fastapi_app.get_application_services", lambda: fake_services)

    response = client.post("/api/research/optimize", json={
        "assets": ["AAPL"]
    })
    assert response.status_code == 400
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "OPTIMIZATION_INSUFFICIENT_HISTORY"

def test_optimize_success_fake_data(client, monkeypatch):
    class FakeMarketData:
        def get_prices(self, assets, **kwargs):
            return pd.DataFrame({
                "AAPL": [100.0, 101.0, 102.0],
                "MSFT": [200.0, 202.0, 201.0]
            }, index=pd.date_range("2023-01-01", periods=3))

    from src.services.research_service import ResearchService
    research_service = ResearchService(market_data=FakeMarketData())
    fake_services = SimpleNamespace(research=research_service)
    monkeypatch.setattr("src.api.fastapi_app.get_application_services", lambda: fake_services)

    response = client.post("/api/research/optimize", json={
        "assets": ["AAPL", "MSFT"]
    })
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "weights" in response.json()["data"]
    assert "AAPL" in response.json()["data"]["weights"]
