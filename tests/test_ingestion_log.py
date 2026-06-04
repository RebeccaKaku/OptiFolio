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

@pytest.mark.skip(reason="MarketDataIngestionService was deleted — test needs rewrite for FinData orchestration")
@pytest.mark.asyncio
async def test_ingestion_service_logs_runs(tmp_path):
    repo_dir = tmp_path / "repo"
    log_file = tmp_path / "log.parquet"

    repo = MarketDataRepository(root_dir=repo_dir)
    log = IngestionLog(log_path=log_file)
    service = MarketDataIngestionService(market_data=repo, ingestion_log=log)

    fake_df = pd.DataFrame({
        "close": [100.0],
        "open": [99.0],
        "high": [101.0],
        "low": [98.0],
        "volume": [1000]
    }, index=pd.to_datetime(["2024-01-01"]))
    fake_df.index.name = "timestamp"

    with patch("src.services.market_data_service.YahooFinanceFetcher.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = fake_df

        await service.ingest_asset("AAPL", "2024-01-01", "2024-01-01", "yahoo")

        runs = log.get_runs()
        assert len(runs) == 1
        assert runs[0].asset_id == "AAPL"
        assert runs[0].status == "success"
        assert runs[0].rows == 1

@pytest.mark.skip(reason="API depends on deleted MarketDataIngestionService")
def test_ingestion_runs_api():
    client = TestClient(app)
    response = client.get("/api/data/ingestion/runs")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "records" in data["data"]
