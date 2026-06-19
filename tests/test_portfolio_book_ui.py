import pytest
from fastapi.testclient import TestClient
from src.api.fastapi_app import app

client = TestClient(app)

def test_onboarding_ui_accessible():
    """Verify that the /book route is accessible and returns the onboarding UI."""
    response = client.get("/book")
    assert response.status_code == 200
    assert "OptiFolio 建账向导" in response.text
    assert "wizard-steps" in response.text

def test_static_resource_accessible():
    """Verify that the static directory is mounted and resources are accessible."""
    response = client.get("/static/book.html")
    assert response.status_code == 200
    assert "OptiFolio 建账向导" in response.text

def test_api_health_check():
    """Verify API is still responsive."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["success"] is True

def test_book_api_endpoints_exist():
    """Verify that key book API endpoints used by the UI exist."""
    # List accounts
    response = client.get("/api/book/accounts")
    assert response.status_code == 200
    assert response.json()["success"] is True

    # List products
    response = client.get("/api/book/products")
    assert response.status_code == 200
    assert response.json()["success"] is True
