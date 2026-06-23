"""findata FX rate provider — queries the canonical store for FX rates.

This is a minimal implementation. OptiFolio-specific fallback rates
(hardcoded USD/CNY, EUR/USD tables) live in src/core/valuation.py.
"""

from __future__ import annotations

from datetime import date as date_t, timedelta
from typing import TYPE_CHECKING

from optifolio_contracts.identifiers import normalize_instrument_id

if TYPE_CHECKING:
    from findata.store.market_repo import MarketDataRepository


class FindataFxProvider:
    """Resolve FX rates from the findata canonical store.

    Unlike OptiFolio's FxRateProvider, this does NOT have hardcoded
    fallback rates — it only queries the data store. Callers should
    handle missing rates themselves.
    """

    def __init__(self, market_data: MarketDataRepository | None = None) -> None:
        self._market_data = market_data

    def get_rate(
        self,
        from_currency: str,
        to_currency: str,
        *,
        as_of: date_t | None = None,
        max_lookback_days: int = 5,
    ) -> float | None:
        """Resolve FX rate from store, or None if unavailable.

        Walks back up to *max_lookback_days* business days from *as_of*.
        """
        if from_currency == to_currency:
            return 1.0

        if self._market_data is None:
            return None

        target = as_of or date_t.today()
        fx_id = normalize_instrument_id(
            f"{from_currency}{to_currency}", asset_type="forex"
        )
        for days_back in range(max_lookback_days + 3):
            d = target - timedelta(days=days_back)
            try:
                prices = self._market_data.get_prices(
                    [fx_id], start=d.isoformat(), end=target.isoformat()
                )
                if not prices.empty and fx_id in prices.columns:
                    col = prices[fx_id].dropna()
                    if not col.empty:
                        rate = float(col.iloc[-1])
                        if rate > 0:
                            return rate
            except Exception:
                pass

        return None
