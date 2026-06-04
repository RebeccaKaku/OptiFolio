"""Service for ingesting market data from various providers into the repository."""

from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

import pandas as pd

from fetchers.boc import BocFetcher
from fetchers.bosc import BoscFetcher
from fetchers.cn_fund import CnFundFetcher
from fetchers.icbc import IcbcFetcher
from fetchers.yahoo_fetcher import YahooFinanceFetcher
from FinData.store.ingestion_log import IngestionLog, IngestionRun
from src.data_foundation import MarketDataRepository


class MarketDataIngestionService:
    """Adapter that takes provider output and calls MarketDataRepository.save_raw."""

    def __init__(self, market_data: Optional[MarketDataRepository] = None) -> None:
        self.market_data = market_data or MarketDataRepository()
        self.log = IngestionLog()

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

        started_at = datetime.datetime.now()
        status = "success"
        errors = None
        rows = 0
        raw_path = "N/A"
        canonical_path = "N/A"

        try:
            df = await fetcher.fetch(symbol, start_date, end_date)
            if df.empty:
                status = "empty"
                return df

            rows = len(df)

            # Route to the correct save method based on provider/data
            if provider in ["boc", "bosc", "icbc"]:
                self.market_data.save_wealth_nav(df, asset_id=symbol, source=provider, currency=currency)
                canonical_path = str(self.market_data.wealth_path)
            elif provider == "akshare":
                # For akshare, we need to distinguish between ETF (OHLCV) and regular funds (NAV)
                cols = [str(c).lower() for c in df.columns]
                if "open" in cols and "close" in cols and "volume" in cols:
                    self.market_data.save_raw(df, asset_id=symbol, source=provider, currency=currency)
                    canonical_path = str(self.market_data.price_path)
                else:
                    self.market_data.save_fund_nav(df, asset_id=symbol, source=provider, currency=currency)
                    canonical_path = str(self.market_data.fund_path)
            else:
                self.market_data.save_raw(df, asset_id=symbol, source=provider, currency=currency)
                canonical_path = str(self.market_data.price_path)

            return df

        except Exception as e:
            status = "failed"
            errors = str(e)
            raise e
        finally:
            run = IngestionRun(
                provider=provider,
                asset_id=symbol,
                rows=rows,
                raw_path=raw_path,
                canonical_path=canonical_path,
                status=status,
                started_at=started_at,
                errors=errors,
            )
            self.log.log_run(run)

    def get_ingestion_runs(self, limit: int = 100) -> Dict[str, Any]:
        """Retrieve historical ingestion runs."""
        from src.services.response import failure, success

        try:
            df = self.log.get_runs(limit)
            # Convert timestamps to strings for JSON serialization
            if not df.empty:
                for col in ["started_at", "finished_at"]:
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col]).dt.strftime("%Y-%m-%d %H:%M:%S")

            return success({"runs": df.to_dict(orient="records")}, "Ingestion runs loaded")
        except Exception as e:
            return failure(str(e), "INGESTION_RUNS_ERROR")
