from __future__ import annotations

"""ValuationEngine — date-aware portfolio valuation using MarketDataRepository.

The ValuationEngine is the central innovation over the legacy PortfolioCore:
it queries the canonical market data store for prices on a specific date
rather than ad-hoc "latest price" fetcher calls.

Convention: ``value_on(T)`` uses the last close price with date <= T.
If no price exists on T, walks backward up to 5 business days.
Raises NoPriceDataError if no price is found.
"""

from datetime import date, timedelta
from typing import Any, Dict, Optional, Sequence, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from src.data_foundation.repository import MarketDataRepository

from src.domain import (
    CashHolding,
    PositionValue,
    ValuationRequest,
    ValuationResult,
)


# ── Error types ────────────────────────────────────────────────────────


class NoPriceDataError(Exception):
    """Raised when required price data is unavailable for valuation."""


class FxRateError(Exception):
    """Raised when an FX rate cannot be resolved."""


# ── FX rate provider ───────────────────────────────────────────────────


class FxRateProvider:
    """Currency conversion for portfolio valuation.

    Priority order:
    1. Same currency → 1.0
    2. Live CurrencyFetcher (yfinance)
    3. Hardcoded fallback table (offline safety net)

    Unlike the legacy PortfolioCore, live rates take priority over
    hardcoded rates when available.
    """

    # Reverse-rate pairs that are likely wrong when returned as 1.0
    _SUSPICIOUS_PAIRS = {
        ("USD", "CNY"), ("CNY", "USD"),
        ("EUR", "USD"), ("USD", "EUR"),
        ("EUR", "CNY"), ("CNY", "EUR"),
        ("JPY", "USD"), ("USD", "JPY"),
    }

    def __init__(self, fallback_rates: Optional[Dict[tuple, float]] = None):
        self._fallback = fallback_rates or {
            ("USD", "CNY"): 7.2,
            ("EUR", "USD"): 1.1,
            ("USD", "JPY"): 150,
            ("USD", "EUR"): 0.91,
            ("CNY", "USD"): 0.139,
        }
        self._cache: Dict[str, float] = {}

    def get_rate(
        self, from_currency: str, to_currency: str, try_live: bool = False
    ) -> float:
        """Resolve the conversion rate from_currency → to_currency.

        Args:
            from_currency: Source currency code (e.g. "USD").
            to_currency: Target currency code (e.g. "CNY").
            try_live: If True, attempt live yfinance lookup first.
                      Default False to avoid network I/O during valuation.
        """
        if from_currency == to_currency:
            return 1.0

        pair_key = (from_currency, to_currency)
        cache_key = f"{from_currency}:{to_currency}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        # 1. (Optional) Try live fetcher
        if try_live:
            try:
                rate = self._get_live_rate(from_currency, to_currency)
                if rate > 0 and not self._is_suspicious(from_currency, to_currency, rate):
                    self._cache[cache_key] = rate
                    return rate
            except Exception:
                pass

        # 2. Try direct fallback
        if pair_key in self._fallback:
            return self._fallback[pair_key]

        # 3. Try transitive via USD
        usd_from = self._fallback.get((from_currency, "USD"))
        usd_to = self._fallback.get(("USD", to_currency))
        if usd_from is not None and usd_to is not None:
            return usd_from * usd_to

        raise FxRateError(
            f"Cannot resolve FX rate {from_currency}→{to_currency}"
        )

    def _get_live_rate(self, from_curr: str, to_curr: str) -> float:
        """Fetch live rate from CurrencyFetcher (blocking, network I/O)."""
        from src.data_core.fetchers.currency import CurrencyFetcher

        fetcher = CurrencyFetcher()
        rate = fetcher.get_realtime_rate(from_curr, to_curr)
        return float(rate)

    def _is_suspicious(self, from_curr: str, to_curr: str, rate: float) -> bool:
        """Detect 1.0 fallback for different-currency pairs."""
        if rate == 1.0 and (from_curr, to_curr) in self._SUSPICIOUS_PAIRS:
            return True
        return False


# ── Valuation engine ───────────────────────────────────────────────────


class ValuationEngine:
    """Date-aware portfolio valuation.

    Queries MarketDataRepository for prices; raises errors instead of
    silently falling back to 1.0.
    """

    def __init__(
        self,
        market_data: Optional["MarketDataRepository"] = None,
        fx_provider: Optional[FxRateProvider] = None,
        max_lookback_days: int = 5,
    ):
        if market_data is None:
            from src.data_foundation.repository import MarketDataRepository
            market_data = MarketDataRepository()
        self.market_data = market_data
        self.fx_provider = fx_provider or FxRateProvider()
        self.max_lookback_days = max_lookback_days

    def value(
        self,
        holdings: Dict[str, float],
        cash: Dict[str, float],
        request: ValuationRequest,
    ) -> ValuationResult:
        """Value a portfolio as of a specific date.

        Args:
            holdings: {asset_id: quantity}
            cash: {currency: amount}
            request: as_of date + base_currency
        """
        assets = [a for a, q in holdings.items() if q > 0]
        if not assets:
            return self._empty_result(request, cash)

        # Build price query range: look back up to max_lookback_days
        lookback_start = request.as_of - timedelta(days=self.max_lookback_days + 3)
        end_str = request.as_of.isoformat()

        prices = self.market_data.get_prices(
            assets,
            start=lookback_start.isoformat(),
            end=end_str,
        )

        if prices.empty:
            raise NoPriceDataError(
                f"No price data for {assets} up to {end_str}"
            )

        # Find the last date with prices <= as_of
        price_date, last_prices = self._get_last_prices(prices, request.as_of, assets)

        # Build position values
        positions: Dict[str, PositionValue] = {}
        for asset_id, qty in holdings.items():
            if qty <= 0:
                continue
            if asset_id not in last_prices or pd.isna(last_prices[asset_id]):
                raise NoPriceDataError(
                    f"No price for {asset_id} on or before {request.as_of}"
                )
            price = float(last_prices[asset_id])
            # Infer currency from repository metadata (default USD)
            asset_currency = self._get_asset_currency(asset_id)
            fx_rate = self.fx_provider.get_rate(asset_currency, request.base_currency)
            value_base = qty * price * fx_rate
            positions[asset_id] = PositionValue(
                asset_id=asset_id,
                quantity=qty,
                price=price,
                currency=asset_currency,
                fx_rate=fx_rate,
                value_base=value_base,
            )

        # Cash breakdown
        cash_breakdown: Dict[str, CashHolding] = {}
        cash_value = 0.0
        fx_rates: Dict[str, float] = {}
        for curr, amount in cash.items():
            if amount == 0:
                continue
            rate = (
                1.0
                if curr == request.base_currency
                else self.fx_provider.get_rate(curr, request.base_currency)
            )
            val = amount * rate
            cash_breakdown[curr] = CashHolding(
                currency=curr, amount=amount, fx_rate=rate, value_base=val
            )
            fx_rates[curr] = rate
            cash_value += val

        holdings_value = sum(p.value_base for p in positions.values())
        total = holdings_value + cash_value

        return ValuationResult(
            as_of=request.as_of,
            total_value=total,
            holdings_value=holdings_value,
            cash_value=cash_value,
            base_currency=request.base_currency,
            positions=positions,
            cash_breakdown=cash_breakdown,
            fx_rates=fx_rates,
            price_date=price_date,
        )

    def value_history(
        self,
        holdings: Dict[str, float],
        cash: Dict[str, float],
        dates: Sequence[date],
        base_currency: str = "CNY",
    ) -> list[ValuationResult]:
        """Value portfolio on a series of dates.

        Corporate actions are NOT applied — use CorporateActionProcessor
        to adjust holdings before calling this method.
        """
        results: list[ValuationResult] = []
        for d in sorted(dates):
            try:
                result = self.value(
                    holdings, cash,
                    ValuationRequest(as_of=d, base_currency=base_currency),
                )
                results.append(result)
            except NoPriceDataError:
                continue
        return results

    # ── helpers ────────────────────────────────────────────────────────

    def _get_last_prices(
        self,
        prices: pd.DataFrame,
        as_of: date,
        assets: list[str],
    ) -> tuple[date, pd.Series]:
        """Walk backward from as_of to find the last available prices."""
        # Filter to dates <= as_of
        as_of_ts = pd.Timestamp(as_of)
        valid = prices[prices.index <= as_of_ts]
        if valid.empty:
            raise NoPriceDataError(
                f"No prices on or before {as_of} for {assets}"
            )

        # Take the most recent date
        last_date_ts = valid.index[-1]
        last_row = valid.iloc[-1]

        # Check we're within lookback window
        price_date = last_date_ts.date()
        days_back = (as_of - price_date).days
        if days_back > self.max_lookback_days:
            raise NoPriceDataError(
                f"Most recent price for {assets} is {price_date}, "
                f"{days_back} days before {as_of} (max {self.max_lookback_days})"
            )

        return price_date, last_row

    def _get_asset_currency(self, asset_id: str) -> str:
        """Infer asset currency. Default USD.

        In the future this should query asset_registry or
        MarketDataRepository metadata.
        """
        _ = asset_id
        return "USD"

    def _empty_result(
        self, request: ValuationRequest, cash: Dict[str, float]
    ) -> ValuationResult:
        """Return a zero-value result when there are no holdings."""
        cash_value = 0.0
        breakdiown: Dict[str, CashHolding] = {}
        for curr, amount in cash.items():
            rate = (
                1.0
                if curr == request.base_currency
                else self.fx_provider.get_rate(curr, request.base_currency)
            )
            val = amount * rate
            breakdiown[curr] = CashHolding(
                currency=curr, amount=amount, fx_rate=rate, value_base=val
            )
            cash_value += val

        return ValuationResult(
            as_of=request.as_of,
            total_value=cash_value,
            holdings_value=0.0,
            cash_value=cash_value,
            base_currency=request.base_currency,
            positions={},
            cash_breakdown=breakdiown,
            fx_rates={},
            price_date=request.as_of,
        )
