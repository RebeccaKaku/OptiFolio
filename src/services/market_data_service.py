"""Service for ingesting market data from various providers into the repository."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from fetchers.cn_fund import CnFundFetcher
from fetchers.yahoo_fetcher import YahooFinanceFetcher
from src.data_foundation import MarketDataRepository


class MarketDataIngestionService:
    """Adapter that takes provider output and calls MarketDataRepository.save_canonical."""

    def __init__(self, market_data: Optional[MarketDataRepository] = None) -> None:
        self.market_data = market_data or MarketDataRepository()

    async def ingest_asset(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        provider: str,
        currency: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch data from a provider and save it to the repository.

        Args:
            symbol: Asset symbol (e.g., 'AAPL' or '510300').
            start_date: Start date for fetching.
            end_date: End date for fetching.
            provider: Data provider key ('yahoo' or 'akshare').
            currency: Optional currency for the asset.

        Returns:
            The canonicalized DataFrame that was saved.
        """
        if provider == "yahoo":
            fetcher = YahooFinanceFetcher()
        elif provider == "akshare":
            fetcher = CnFundFetcher()
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        df = await fetcher.fetch(symbol, start_date, end_date)
        if df.empty:
            return df

        # Step 1: Save as-is to bronze layer
        self.market_data.save_bronze(df, asset_id=symbol, provider=provider)

        # Step 2: Save cleaned/normalized to canonical layer
        return self.market_data.save_canonical(df, asset_id=symbol, source=provider, currency=currency)
