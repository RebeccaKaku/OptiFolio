import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.api.fastapi_app import create_app
from src.services.application import ApplicationServices

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_get_summary_endpoint(client, monkeypatch):
    mock_my_money = MagicMock()
    mock_my_money.get_summary.return_value = {
        "success": True,
        "data": {
            "has_data": True,
            "total_assets_reporting": 1234.56,
            "reporting_currency": "CNY",
            "return_status": "available",
            "by_currency": {}
        }
    }

    # Mock the service graph
    mock_services = MagicMock(spec=ApplicationServices)
    mock_services.my_money = mock_my_money

    # The actual import is in _get_service() inside src/api/my_money_api.py
    monkeypatch.setattr("src.services.application.get_application_services", lambda: mock_services)

    response = client.get("/api/book/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["total_assets_reporting"] == 1234.56
