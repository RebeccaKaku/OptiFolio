import pytest
import pandas as pd
from unittest.mock import patch, AsyncMock
from src.data_foundation import MarketDataRepository
from src.services.market_data_service import MarketDataIngestionService

@pytest.mark.asyncio
async def test_ingestion_adapter_saves_to_repository(tmp_path):
    # Setup temporary repository and service
    repo = MarketDataRepository(tmp_path)
    service = MarketDataIngestionService(repo)

    # Fake data for Yahoo (US Equity)
    yahoo_data = pd.DataFrame({
        "close": [150.0, 155.0],
        "open": [149.0, 151.0],
        "high": [152.0, 156.0],
        "low": [148.0, 150.0],
        "volume": [1000000, 1100000]
    }, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    yahoo_data.index.name = "timestamp"

    # Fake data for Akshare (CN Fund)
    akshare_data = pd.DataFrame({
        "close": [1.2, 1.25],
        "open": [1.2, 1.25],
        "high": [1.2, 1.25],
        "low": [1.2, 1.25],
        "volume": [0, 0]
    }, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    akshare_data.index.name = "timestamp"

    # Mock fetchers
    with patch("src.services.market_data_service.YahooFinanceFetcher.fetch", new_callable=AsyncMock) as mock_yahoo, \
         patch("src.services.market_data_service.CnFundFetcher.fetch", new_callable=AsyncMock) as mock_akshare:

        mock_yahoo.return_value = yahoo_data
        mock_akshare.return_value = akshare_data

        # Ingest assets
        await service.ingest_asset("AAPL", "2024-01-01", "2024-01-02", "yahoo", currency="USD")
        await service.ingest_asset("510300", "2024-01-01", "2024-01-02", "akshare", currency="CNY")

        # Verify repository content
        assets = repo.list_assets()
        assert "AAPL" in assets
        assert "510300" in assets

        # Verify price matrix retrieval
        prices = repo.get_prices(["AAPL", "510300"])
        assert not prices.empty
        assert "AAPL" in prices.columns
        assert "510300" in prices.columns
        assert len(prices) == 2

        # Specific value checks
        assert prices.loc["2024-01-01", "AAPL"] == 150.0
        assert prices.loc["2024-01-02", "510300"] == 1.25
