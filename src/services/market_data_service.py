"""Service for ingesting market data from various providers into the repository."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from fetchers.cn_fund import CnFundFetcher
from fetchers.yahoo_fetcher import YahooFinanceFetcher
from src.data_foundation import MarketDataRepository


class MarketDataIngestionService:
    """Adapter that takes provider output and calls MarketDataRepository.save_raw."""

    # Provider → IANA timezone mapping
    PROVIDER_TIMEZONES: dict[str, str] = {
        "yahoo": "America/New_York",
        "akshare": "Asia/Shanghai",
        "crypto": "UTC",
        "bosc": "Asia/Shanghai",
        "boc": "Asia/Shanghai",
        "icbc": "Asia/Shanghai",
        "manual": "UTC",
    }

    def __init__(self, market_data: Optional[MarketDataRepository] = None) -> None:
        self.market_data = market_data or MarketDataRepository()

    async def ingest_asset(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        provider: str,
        currency: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch data from a provider and save it to the repository.

        Args:
            symbol: Asset symbol (e.g., 'AAPL' or '510300').
            start_date: Start date for fetching.
            end_date: End date for fetching.
            provider: Data provider key ('yahoo' or 'akshare').
            currency: Optional currency for the asset.
            timezone: Optional IANA timezone. Auto-detected from provider if None.

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

        tz = timezone or self.PROVIDER_TIMEZONES.get(provider, "UTC")
        return self.market_data.save_raw(
            df, asset_id=symbol, source=provider, currency=currency, timezone=tz,
        )
