import pytest
import pandas as pd
from datetime import datetime
from FinData.store.ingestion_log import IngestionLog, IngestionRun
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from src.api.fastapi_app import app

def test_ingestion_run_creation():
    run = IngestionRun.create("yahoo", "AAPL")
    assert run.provider == "yahoo"
    assert run.asset_id == "AAPL"
    assert run.status == "started"
    assert isinstance(run.started_at, datetime)
    assert run.run_id is not None

def test_ingestion_log_save_load(tmp_path):
    log_file = tmp_path / "test_log.parquet"
    log = IngestionLog(log_path=log_file)

    run = IngestionRun.create("yahoo", "AAPL")
    log.log_run(run)

    runs = log.get_runs()
    assert len(runs) == 1
    assert runs[0].run_id == run.run_id
    assert runs[0].status == "started"

    # Update run
    run.status = "success"
    run.finished_at = datetime.now()
    log.log_run(run)

    runs = log.get_runs()
    assert len(runs) == 1
    assert runs[0].status == "success"

def test_ingestion_runs_api():
    from src.services.application import IngestionService
    service = IngestionService()
    response = service.get_runs()
    assert response["success"] is True
    assert "records" in response["data"]

def test_ingestion_runs_endpoint():
    client = TestClient(app)
    response = client.get("/api/data/ingestion/runs")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "records" in data["data"]
