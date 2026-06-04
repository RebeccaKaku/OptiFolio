import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from FinData.store.quality import QualityGate, QualityReport
from src.api.fastapi_app import app
from src.data_foundation import MarketDataRepository


@pytest.fixture
def temp_repo(tmp_path):
    repo_dir = tmp_path / "data" / "foundation"
    repo_dir.mkdir(parents=True)
    return MarketDataRepository(root_dir=tmp_path / "data" / "foundation")


@pytest.fixture
def mock_quality_report_file(tmp_path, monkeypatch):
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir(parents=True)
    file_path = metadata_dir / "data_quality_issues.parquet"
    monkeypatch.setattr(QualityReport, "FILE_PATH", file_path)
    return file_path


def test_stale_price_check(temp_repo):
    # Setup mock data
    now = datetime.now()
    df = pd.DataFrame(
        {
            "asset_id": ["STALE", "FRESH"],
            "date": [now - timedelta(days=10), now - timedelta(days=1)],
            "open": [100.0, 200.0],
            "high": [105.0, 205.0],
            "low": [95.0, 195.0],
            "close": [102.0, 202.0],
            "adj_close": [102.0, 202.0],
            "volume": [1000, 2000],
            "currency": ["USD", "USD"],
            "source": ["test", "test"],
        }
    )
    temp_repo.save_raw(df)

    gate = QualityGate(repository=temp_repo)
    report = gate.stale_price_check(n_days=5)

    assert len(report.issues) == 1
    assert report.issues.iloc[0]["asset_id"] == "STALE"
    assert report.issues.iloc[0]["issue_type"] == "stale_price"


def test_quality_report_save(mock_quality_report_file):
    issues = pd.DataFrame(
        {
            "asset_id": ["TEST1"],
            "issue_type": ["stale_price"],
            "details": ["Last update: 2023-01-01"],
            "timestamp": [datetime.now()],
        }
    )
    report = QualityReport(issues)
    report.save()

    assert mock_quality_report_file.exists()
    saved_df = pd.read_parquet(mock_quality_report_file)
    assert len(saved_df) == 1
    assert saved_df.iloc[0]["asset_id"] == "TEST1"


def test_api_quality_endpoint(mock_quality_report_file):
    # Setup mock quality data
    issues = pd.DataFrame(
        {
            "asset_id": ["ASSET1", "ASSET2"],
            "issue_type": ["stale_price", "missing_data"],
            "details": ["detail1", "detail2"],
            "timestamp": [datetime(2023, 1, 1), datetime(2023, 1, 2)],
        }
    )
    QualityReport(issues).save()

    client = TestClient(app)

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
