"""Service for ingesting market data from various providers into the repository."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from fetchers.cn_fund import CnFundFetcher
from fetchers.yahoo_fetcher import YahooFinanceFetcher
from FinData.store.ingestion_log import IngestionLog, IngestionRun
from src.data_foundation import MarketDataRepository

from .response import success


class MarketDataIngestionService:
    """Adapter that takes provider output and calls MarketDataRepository.save_raw."""

    def __init__(
        self,
        market_data: Optional[MarketDataRepository] = None,
        ingestion_log: Optional[IngestionLog] = None,
    ) -> None:
        self.market_data = market_data or MarketDataRepository()
        self.ingestion_log = ingestion_log or IngestionLog()

    async def ingest_asset(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        provider: str,
        currency: Optional[str] = None,
    ) -> pd.DataFrame:
        run = IngestionRun.create(provider=provider, asset_id=symbol)
        self.ingestion_log.log_run(run)

        try:
            df = await self._fetch_and_save(symbol, start_date, end_date, provider, currency, run)
            run.status = "success"
            run.finished_at = datetime.now()
            run.rows = len(df)
            run.raw_path = "api_response"
            if hasattr(self.market_data, "price_path"):
                run.canonical_path = str(self.market_data.price_path)
            self.ingestion_log.log_run(run)
            return df
        except Exception as exc:
            run.status = "failed"
            run.finished_at = datetime.now()
            run.errors = str(exc)
            self.ingestion_log.log_run(run)
            raise

    async def _fetch_and_save(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        provider: str,
        currency: Optional[str],
        run: IngestionRun,
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

        return self.market_data.save_raw(df, asset_id=symbol, source=provider, currency=currency)

    def get_runs(self) -> Dict[str, Any]:
        runs = self.ingestion_log.get_runs()
        return success(
            {"records": [self._run_to_dict(run) for run in runs]}, "Ingestion runs loaded"
        )

    def _run_to_dict(self, run: IngestionRun) -> Dict[str, Any]:
        data = {
            "run_id": run.run_id,
            "provider": run.provider,
            "asset_id": run.asset_id,
            "rows": run.rows,
            "raw_path": run.raw_path,
            "canonical_path": run.canonical_path,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "errors": run.errors,
        }
        return data
