"""Tests for data quality API endpoint."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.fastapi_app import app
from src.core.paths import PROJECT_ROOT

client = TestClient(app)

QUALITY_FILE = PROJECT_ROOT / "metadata" / "data_quality_issues.parquet"


@pytest.fixture
def clean_quality_file():
    """Ensure the quality file is cleaned up after each test."""
    backup = None
    if QUALITY_FILE.exists():
        backup = pd.read_parquet(QUALITY_FILE)
    yield
    if backup is not None:
        backup.to_parquet(QUALITY_FILE, index=False)
    elif QUALITY_FILE.exists():
        QUALITY_FILE.unlink()


def test_api_quality_endpoint_no_data(clean_quality_file):
    # Make sure file does not exist
    if QUALITY_FILE.exists():
        QUALITY_FILE.unlink()

    response = client.get("/api/data/quality")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["reports"] == []


def test_api_quality_endpoint_with_data(clean_quality_file):
    QUALITY_FILE.parent.mkdir(parents=True, exist_ok=True)

    issues = pd.DataFrame(
        {
            "asset_id": ["ASSET1", "ASSET2"],
            "issue_type": ["stale_price", "missing_data"],
            "details": ["detail1", "detail2"],
            "timestamp": [datetime(2023, 1, 1), datetime(2023, 1, 2)],
        }
    )
    issues.to_parquet(QUALITY_FILE, index=False)

    # Test getting all reports
    response = client.get("/api/data/quality")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]["reports"]) == 2

    # Test filtering by asset_id
    response = client.get("/api/data/quality?asset_id=ASSET1")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["reports"]) == 1
    assert data["data"]["reports"][0]["asset_id"] == "ASSET1"
    assert data["data"]["reports"][0]["timestamp"] == "2023-01-01 00:00:00"
