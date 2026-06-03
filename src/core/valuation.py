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


# ── Currency resolution ────────────────────────────────────────────────


def _resolve_currency(asset_id: str) -> str:
    """Resolve an asset's native currency from config files.

    Checks asset_registry.yaml first, then candidates.yaml,
    then falls back to heuristic inference.
    """
    import yaml
    from pathlib import Path
    from src.core.paths import PROJECT_ROOT

    # 1. asset_registry.yaml
    registry_path = PROJECT_ROOT / "config" / "asset_registry.yaml"
    if registry_path.exists():
        with open(registry_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for entry in data.get("assets", []):
            if entry.get("symbol") == asset_id:
                cur = entry.get("currency")
                if cur:
                    return str(cur)

    # 2. candidates.yaml
    candidates_path = PROJECT_ROOT / "config" / "candidates.yaml"
    if candidates_path.exists():
        with open(candidates_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for entry in data.get("assets", []):
            if entry.get("symbol") == asset_id:
                cur = entry.get("currency")
                if cur:
                    return str(cur)

    # 3. Heuristic
    if asset_id.startswith(("sh", "sz")):
        return "CNY"
    if asset_id.isdigit() and len(asset_id) == 6:
        return "CNY"
    if asset_id.isupper() and any(c.isdigit() for c in asset_id) and len(asset_id) > 8:
        return "USD"  # BOC-style codes like AMHQLXTTUSD01B
    if asset_id.isdigit() and len(asset_id) == 8:
        return "CNY"  # ICBC-style codes like 23GS8125

    return "USD"


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

        # Find last available price for each asset (may differ by asset)
        price_dates, last_prices = self._get_last_prices(prices, request.as_of, assets)

        # Build position values
        positions: Dict[str, PositionValue] = {}
        for asset_id, qty in holdings.items():
            if qty <= 0:
                continue
            if asset_id not in last_prices or pd.isna(last_prices.get(asset_id)):
                raise NoPriceDataError(
                    f"No price for {asset_id} on or before {request.as_of}"
                )
            price = float(last_prices[asset_id])
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

        # Use the earliest price_date among all assets as the valuation date
        price_date = min(price_dates.values()) if price_dates else request.as_of

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
    ) -> tuple[Dict[str, date], Dict[str, float]]:
        """Get the last available price for each asset on or before as_of.

        Each asset may have a different last-trading date.
        Returns ({asset_id: price_date}, {asset_id: close_price}).
        """
        as_of_ts = pd.Timestamp(as_of)
        valid = prices[prices.index <= as_of_ts]
        if valid.empty:
            raise NoPriceDataError(
                f"No prices on or before {as_of} for {assets}"
            )

        price_dates: Dict[str, date] = {}
        last_prices: Dict[str, float] = {}

        for asset_id in assets:
            if asset_id not in valid.columns:
                continue
            # Find last non-NaN row for this asset
            asset_prices = valid[asset_id].dropna()
            if asset_prices.empty:
                continue
            last_date_ts = asset_prices.index[-1]
            price_date = last_date_ts.date()
            days_back = (as_of - price_date).days
            if days_back > self.max_lookback_days:
                continue  # Too old
            price_dates[asset_id] = price_date
            last_prices[asset_id] = float(asset_prices.iloc[-1])

        if not price_dates:
            raise NoPriceDataError(
                f"No prices within {self.max_lookback_days} days of {as_of} for {assets}"
            )

        return price_dates, last_prices

    def _get_asset_currency(self, asset_id: str) -> str:
        """Resolve asset currency from asset_registry.yaml or candidates.yaml.

        Falls back to heuristic inference, then USD.
        """
        return _resolve_currency(asset_id)

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
