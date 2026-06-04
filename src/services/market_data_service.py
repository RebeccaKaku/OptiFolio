"""Service for ingesting market data from various providers into the repository."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from fetchers.boc import BocFetcher
from fetchers.bosc import BoscFetcher
from fetchers.cn_fund import CnFundFetcher
from fetchers.icbc import IcbcFetcher
from fetchers.yahoo_fetcher import YahooFinanceFetcher
from src.data_foundation import MarketDataRepository


class MarketDataIngestionService:
    """Adapter that takes provider output and calls MarketDataRepository.save_raw."""

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
            provider: Data provider key ('yahoo', 'akshare', 'boc', 'bosc', 'icbc').
            currency: Optional currency for the asset.

        Returns:
            The canonicalized DataFrame that was saved.
        """
        if provider == "yahoo":
            fetcher = YahooFinanceFetcher()
        elif provider == "akshare":
            fetcher = CnFundFetcher()
        elif provider == "boc":
            fetcher = BocFetcher()
        elif provider == "bosc":
            fetcher = BoscFetcher()
        elif provider == "icbc":
            fetcher = IcbcFetcher()
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        df = await fetcher.fetch(symbol, start_date, end_date)
        if df.empty:
            return df

        # Route to the correct save method based on provider/data
        if provider in ["boc", "bosc", "icbc"]:
            return self.market_data.save_wealth_nav(df, asset_id=symbol, source=provider, currency=currency)
        elif provider == "akshare":
            # For akshare, we need to distinguish between ETF (OHLCV) and regular funds (NAV)
            cols = [str(c).lower() for c in df.columns]
            if "open" in cols and "close" in cols and "volume" in cols:
                return self.market_data.save_raw(df, asset_id=symbol, source=provider, currency=currency)
            else:
                return self.market_data.save_fund_nav(df, asset_id=symbol, source=provider, currency=currency)
        else:
            return self.market_data.save_raw(df, asset_id=symbol, source=provider, currency=currency)
