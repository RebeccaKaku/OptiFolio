import pytest
import pandas as pd
from unittest.mock import patch, AsyncMock
from src.data_foundation import MarketDataRepository
from src.services.market_data_service import MarketDataIngestionService
from FinData.store.ingestion_log import IngestionLog

@pytest.mark.asyncio
async def test_ingestion_logs_metadata(tmp_path):
    # Setup temporary repository and service
    repo = MarketDataRepository(tmp_path)
    service = MarketDataIngestionService(repo)

    # Use a custom log path for testing
    test_log_path = tmp_path / "ingestion_runs.parquet"
    service.log.FILE_PATH = test_log_path

    # Fake data for Yahoo
    yahoo_data = pd.DataFrame({
        "close": [150.0, 155.0],
        "open": [149.0, 151.0],
        "high": [152.0, 156.0],
        "low": [148.0, 150.0],
        "volume": [1000000, 1100000]
    }, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    yahoo_data.index.name = "timestamp"

    # Mock fetcher
    with patch("src.services.market_data_service.YahooFinanceFetcher.fetch", new_callable=AsyncMock) as mock_yahoo:
        mock_yahoo.return_value = yahoo_data

        # Ingest asset
        await service.ingest_asset("AAPL", "2024-01-01", "2024-01-02", "yahoo", currency="USD")

        # Verify log exists
        assert test_log_path.exists()

        # Verify log content
        runs = service.get_ingestion_runs()
        assert runs["success"]
        assert len(runs["data"]["runs"]) == 1

        run = runs["data"]["runs"][0]
        assert run["asset_id"] == "AAPL"
        assert run["provider"] == "yahoo"
        assert run["status"] == "success"
        assert run["rows"] == 2
        assert "market_prices.parquet" in run["canonical_path"]

@pytest.mark.asyncio
async def test_ingestion_logs_failure(tmp_path):
    # Setup temporary repository and service
    repo = MarketDataRepository(tmp_path)
    service = MarketDataIngestionService(repo)

    # Use a custom log path for testing
    test_log_path = tmp_path / "ingestion_runs.parquet"
    service.log.FILE_PATH = test_log_path

    # Mock fetcher to raise error
    with patch("src.services.market_data_service.YahooFinanceFetcher.fetch", new_callable=AsyncMock) as mock_yahoo:
        mock_yahoo.side_effect = Exception("Fetch failed")

        # Ingest asset (should raise)
        with pytest.raises(Exception):
            await service.ingest_asset("FAIL", "2024-01-01", "2024-01-02", "yahoo")

        # Verify log exists
        assert test_log_path.exists()

        # Verify log content
        runs = service.get_ingestion_runs()
        assert runs["success"]
        assert len(runs["data"]["runs"]) == 1

        run = runs["data"]["runs"][0]
        assert run["asset_id"] == "FAIL"
        assert run["status"] == "failed"
        assert "Fetch failed" in run["errors"]
