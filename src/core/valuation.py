from __future__ import annotations

from typing import Dict, Optional, Sequence

import pandas as pd

from src.data_foundation.repository import MarketDataRepository


class ValuationEngine:
    """Engine for retrieving asset valuations from multiple standardized storage backends.

    It abstracts away the underlying storage details (OHLCV vs NAV) and provides
    a unified interface for price discovery.
    """

    def __init__(self, repository: MarketDataRepository | None = None) -> None:
        self.repository = repository or MarketDataRepository()

    def get_latest_price(self, symbol: str) -> float | None:
        """Get the most recent price for a single asset."""
        prices = self.get_latest_prices([symbol])
        return prices.get(symbol)

    def get_latest_prices(self, symbols: Sequence[str]) -> Dict[str, float]:
        """Get the most recent prices for a collection of assets.

        Automatically routes to OHLCV, Fund NAV, or Wealth NAV storage
        depending on where the asset data is found.
        """
        # MarketDataRepository.get_prices is updated to aggregate from all sources
        df = self.repository.get_prices(symbols, fields=["adj_close"])
        if df.empty:
            return {}

        latest_prices = {}
        for symbol in symbols:
            if symbol in df.columns:
                series = df[symbol].dropna()
                if not series.empty:
                    latest_prices[symbol] = float(series.iloc[-1])

        return latest_prices

    def get_price_history(
        self,
        symbols: Sequence[str],
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Get historical price matrix for a collection of assets."""
        return self.repository.get_prices(symbols, start=start, end=end, fields=["adj_close"])
