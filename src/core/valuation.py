from __future__ import annotations

"""ValuationEngine — date-aware portfolio valuation using FinDataProvider.

The ValuationEngine is the central innovation over the legacy PortfolioCore:
it queries the canonical market data store for prices on a specific date
rather than ad-hoc "latest price" fetcher calls.

Convention: ``value_on(T)`` uses the last close price with date <= T.
If no price exists on T, walks backward up to 5 business days.
Raises NoPriceDataError if no price is found.

Also implements single-asset priority-based valuation:
manual confirmed > public market_price / NAV > carried_forward > unknown.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from src.infrastructure import HttpMarketDataClient, MarketDataGateway

from optifolio_contracts.quality import ValuationFreshness, ValuationQuality
from src.domain import (
    CashHolding,
    PositionValue,
    ValuationRequest,
    ValuationResult,
)


# ── Error types ────────────────────────────────────────────────────────


class NoPriceDataError(Exception):
    """Raised when required price data is unavailable for valuation."""


from optifolio_contracts.fx import (
    FxRateError,
    HardcodedFxRateProvider,
)


# ── FX rate provider ───────────────────────────────────────────────────


class FxRateProvider:
    """Currency conversion for portfolio valuation.

    Priority order:
    1. Same currency → 1.0
    2. FinDataProvider gateway (dated historical FX rates)
    3. Live CurrencyFetcher (yfinance)
    """

    # Reverse-rate pairs that are likely wrong when returned as 1.0
    _SUSPICIOUS_PAIRS = {
        ("USD", "CNY"), ("CNY", "USD"),
        ("EUR", "USD"), ("USD", "EUR"),
        ("EUR", "CNY"), ("CNY", "EUR"),
        ("JPY", "USD"), ("USD", "JPY"),
    }

    def __init__(
        self,
        fallback_rates: Optional[Dict[tuple, float]] = None,
        market_data: Optional["MarketDataGateway"] = None,
    ):
        self._hardcoded = HardcodedFxRateProvider(fallback_rates)
        self._cache: Dict[str, float] = {}
        self.market_data = market_data

    def get_rate_from_repository(
        self,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
        max_lookback_days: int = 5,
    ) -> Optional[float]:
        """Resolve the conversion rate using dated FX data from the repository.

        Queries the configured market-data gateway for canonical FX asset id on or
        before *as_of_date*, walking back up to *max_lookback_days*.
        Returns None when the repository is unavailable or no matching
        data exists.

        Args:
            from_currency: Source currency code (e.g. "USD").
            to_currency: Target currency code (e.g. "CNY").
            as_of_date: The valuation date.
            max_lookback_days: Maximum days to look back for a rate.
        """
        if from_currency == to_currency:
            return 1.0

        if self.market_data is None:
            return None

        from optifolio_contracts.identifiers import normalize_instrument_id

        asset_id = normalize_instrument_id(
            f"{from_currency}{to_currency}", asset_type="forex"
        )
        lookback_start = as_of_date - timedelta(days=max_lookback_days + 3)

        try:
            prices = self.market_data.get_prices(
                [asset_id],
                start=lookback_start.isoformat(),
                end=as_of_date.isoformat(),
            )
            if not prices.empty and asset_id in prices.columns:
                col = prices[asset_id].dropna()
                if not col.empty:
                    rate = float(col.iloc[-1])
                    if rate > 0:
                        return rate
        except Exception:
            pass

        return None

    def get_rate(
        self, from_currency: str, to_currency: str, try_live: bool = False,
        as_of: "date | None" = None,
    ) -> float:
        """Resolve the conversion rate from_currency → to_currency.

        Args:
            from_currency: Source currency code (e.g. "USD").
            to_currency: Target currency code (e.g. "CNY").
            try_live: If True, attempt live yfinance lookup first.
                      Default False to avoid network I/O during valuation.
            as_of: If provided, look for FX rate on this date in repository
                   first. Prevents price/FX date mismatches (06-18 close ×
                   06-20 FX → spurious CNY P&L).
        """
        if from_currency == to_currency:
            return 1.0

        cache_key = f"{from_currency}:{to_currency}:{as_of}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        # 1. Try dated repository lookup
        target_date = as_of or date.today()
        rate = self.get_rate_from_repository(from_currency, to_currency, target_date, max_lookback_days=3)
        if rate is not None and rate > 0:
            self._cache[cache_key] = rate
            return rate

        # 2. (Optional) Try live fetcher
        if try_live:
            try:
                rate = self._get_live_rate(from_currency, to_currency)
                if rate > 0 and not self._is_suspicious(from_currency, to_currency, rate):
                    self._cache[cache_key] = rate
                    return rate
            except Exception:
                pass

        # 3. User-provided hardcoded fallback table (no global defaults)
        try:
            rate = self._hardcoded.get_rate(from_currency, to_currency)
            self._cache[cache_key] = rate
            return rate
        except FxRateError:
            raise FxRateError(
                f"Cannot resolve FX rate {from_currency}→{to_currency}"
            )

    def _get_live_rate(self, from_curr: str, to_curr: str) -> float:
        """Fetch via the configured remote data gateway."""
        if self.market_data is None or not hasattr(self.market_data, "fx_rate"):
            from src.infrastructure import HttpMarketDataClient
            gateway = HttpMarketDataClient()
        else:
            gateway = self.market_data
        return float(gateway.fx_rate(from_curr, to_curr, mode="fast"))

    def _is_suspicious(self, from_curr: str, to_curr: str, rate: float) -> bool:
        """Detect 1.0 fallback for different-currency pairs."""
        if rate == 1.0 and (from_curr, to_curr) in self._SUSPICIOUS_PAIRS:
            return True
        return False


# ── Currency resolution ────────────────────────────────────────────────

_currency_cache: Dict[str, str] = {}


def _resolve_currency(asset_id: str) -> str:
    """Resolve an asset's native currency from config files.

    Checks asset_registry.yaml first, then candidates.yaml,
    then falls back to heuristic inference.

    Results are cached in _currency_cache to avoid repeated YAML I/O.
    """
    if asset_id in _currency_cache:
        return _currency_cache[asset_id]

    import yaml
    from pathlib import Path
    from src.core.paths import PROJECT_ROOT

    result: str = "USD"

    # 1. asset_registry.yaml
    registry_path = PROJECT_ROOT / "config" / "asset_registry.yaml"
    if registry_path.exists():
        with open(registry_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for entry in data.get("assets", []):
            if entry.get("symbol") == asset_id:
                cur = entry.get("currency")
                if cur:
                    result = str(cur)
                    _currency_cache[asset_id] = result
                    return result

    # 2. candidates.yaml
    candidates_path = PROJECT_ROOT / "config" / "candidates.yaml"
    if candidates_path.exists():
        with open(candidates_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for entry in data.get("assets", []):
            if entry.get("symbol") == asset_id:
                cur = entry.get("currency")
                if cur:
                    result = str(cur)
                    _currency_cache[asset_id] = result
                    return result

    # 3. Canonical-id heuristics
    if asset_id.startswith("equity.cn.") or asset_id.startswith("fund.cn.") or asset_id.startswith("wmp.cn."):
        result = "CNY"
    elif asset_id.startswith("equity.us."):
        result = "USD"
    # 4. Legacy/raw heuristics
    elif asset_id.startswith(("sh", "sz")):
        result = "CNY"
    elif asset_id.isdigit() and len(asset_id) == 6:
        result = "CNY"
    elif asset_id.isupper() and any(c.isdigit() for c in asset_id) and len(asset_id) > 8:
        result = "USD"  # BOC-style codes like AMHQLXTTUSD01B
    elif asset_id.isdigit() and len(asset_id) == 8:
        result = "CNY"  # ICBC-style codes like 23GS8125

    _currency_cache[asset_id] = result
    return result


# ── Valuation candidate ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ValuationCandidate:
    """A potential value for a position from a specific source.

    Used by the single-asset priority-based valuation path (select_best /
    value_single). The portfolio-level value() method does NOT use this class.
    """

    amount: Optional[float] = None
    price: Optional[float] = None
    quantity: Optional[float] = None
    currency: str = "CNY"
    effective_date: Optional[date] = None
    known_at: Optional[date] = None
    source_id: str = "unknown"
    source_type: str = "unknown"  # manual, public, etc.
    quality: ValuationQuality = ValuationQuality.UNKNOWN

    def get_amount(self) -> Optional[float]:
        """Calculate amount from price and quantity if direct amount is missing."""
        if self.amount is not None:
            return self.amount
        if self.price is not None and self.quantity is not None:
            return self.price * self.quantity
        return None


# ── Valuation engine ───────────────────────────────────────────────────


class ValuationEngine:
    """Date-aware portfolio valuation.

    Queries the configured market-data gateway for prices; raises errors instead of
    silently falling back to 1.0.
    """

    def __init__(
        self,
        market_data: Optional["MarketDataGateway"] = None,
        fx_provider: Optional[FxRateProvider] = None,
        max_lookback_days: int = 5,
    ):
        if market_data is None:
            from src.infrastructure import HttpMarketDataClient, MarketDataGateway
            market_data = HttpMarketDataClient()
        self.market_data = market_data
        self.fx_provider = fx_provider or FxRateProvider(market_data=market_data)
        self.max_lookback_days = max_lookback_days

    def value(
        self,
        holdings: Dict[str, float],
        cash: Dict[str, float],
        request: ValuationRequest,
        *,
        strict: bool = True,
    ) -> ValuationResult:
        """Value a portfolio as of a specific date.

        Args:
            holdings: {asset_id: quantity}
            cash: {currency: amount}
            request: as_of date + base_currency
            strict: If True, raise NoPriceDataError on any missing price.
                    If False (default for dashboard), skip unpriced assets
                    and return them in ``unpriced`` list.

        Financial invariants:
            total_value = holdings_value + cash_value
            positions[].value_base = quantity × price × fx_rate
            fx_rate must use the same date as price_date (not today).
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

        if prices.empty and strict:
            raise NoPriceDataError(
                f"No price data for {assets} up to {end_str}"
            )

        # Find last available price for each asset (may differ by asset)
        price_dates, last_prices = self._get_last_prices(prices, request.as_of, assets, strict=strict)

        # Build position values — skip unpriced when not strict
        positions: Dict[str, PositionValue] = {}
        unpriced: list[str] = []
        for asset_id, qty in holdings.items():
            if qty <= 0:
                continue
            if asset_id not in last_prices or pd.isna(last_prices.get(asset_id)):
                if strict:
                    raise NoPriceDataError(
                        f"No price for {asset_id} on or before {request.as_of}"
                    )
                unpriced.append(asset_id)
                continue
            price = float(last_prices[asset_id])
            asset_currency = self._get_asset_currency(asset_id)
            # FX rate must use the same date as the price (not today)
            asset_price_date = price_dates.get(asset_id)
            fx_rate = self.fx_provider.get_rate(
                asset_currency, request.base_currency, as_of=asset_price_date
            )
            value_base = qty * price * fx_rate
            asset_stale_days = (request.as_of - asset_price_date).days if asset_price_date else 0
            positions[asset_id] = PositionValue(
                asset_id=asset_id,
                quantity=qty,
                price=price,
                currency=asset_currency,
                fx_rate=fx_rate,
                value_base=value_base,
                price_date=asset_price_date,
                stale_days=asset_stale_days,
            )

        # Use the earliest price_date among all assets as the valuation date
        price_date = min(price_dates.values()) if price_dates else request.as_of
        # Max staleness across all positions
        max_stale = max((p.stale_days for p in positions.values()), default=0)

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
                else self.fx_provider.get_rate(curr, request.base_currency, as_of=request.as_of)
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
            stale_days=max_stale,
            unpriced=unpriced,
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
        *,
        strict: bool = True,
    ) -> tuple[Dict[str, date], Dict[str, float]]:
        """Get the last available price for each asset on or before as_of.

        Each asset may have a different last-trading date.
        Returns ({asset_id: price_date}, {asset_id: close_price}).

        When strict=False, returns empty dicts instead of raising —
        the caller handles unpriced assets gracefully.
        """
        as_of_ts = pd.Timestamp(as_of)
        valid = prices[prices.index <= as_of_ts]
        if valid.empty and strict:
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

        if not price_dates and strict:
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
        breakdown: Dict[str, CashHolding] = {}
        for curr, amount in cash.items():
            rate = (
                1.0
                if curr == request.base_currency
                else self.fx_provider.get_rate(curr, request.base_currency, as_of=request.as_of)
            )
            val = amount * rate
            breakdown[curr] = CashHolding(
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
            cash_breakdown=breakdown,
            fx_rates={},
            price_date=request.as_of,
        )

    # ── Single-asset valuation methods ─────────────────────────────────

    @staticmethod
    def select_best(
        candidates: List[ValuationCandidate],
        as_of: date,
        target_currency: str = "CNY",
        freshness_thresholds: Optional[Dict[str, int]] = None,
    ) -> ValuationResult:
        """Select the best valuation candidate based on priority rules.

        Priority:
        1. Manual confirmed (effective_date == as_of)
        2. Public NAV/Price (effective_date <= as_of, within threshold)
        3. Last known (stale carry-forward, effective_date < as_of)
        4. Unknown

        Rules:
        - Future dates are rejected.
        - Quantity is required for public price candidates.
        - Zero amount is a valid value, None is unknown.
        - Currency mismatch returns unknown with a warning.
        """
        thresholds = freshness_thresholds or {}
        # Default threshold is 3 days unless specified
        default_threshold = thresholds.get("default", 3)

        # 1. Filter usable candidates (no future dates)
        usable = [c for c in candidates if c.effective_date and c.effective_date <= as_of]

        best_candidate: Optional[ValuationCandidate] = None
        best_priority = 99

        for c in usable:
            amount = c.get_amount()
            if amount is None:
                continue

            # Check currency mismatch
            if c.currency != target_currency:
                continue

            priority = 99
            if c.source_type == "manual" and c.quality == ValuationQuality.CONFIRMED and c.effective_date == as_of:
                priority = 1
            elif c.source_type == "public":
                # Check freshness
                age = (as_of - c.effective_date).days
                threshold = thresholds.get(c.source_id, default_threshold)
                if age <= threshold:
                    priority = 2
            elif c.source_type == "manual" and c.effective_date < as_of:
                priority = 3
            elif c.source_type == "manual" and c.quality == ValuationQuality.REPORTED and c.effective_date == as_of:
                priority = 3

            if priority < best_priority:
                best_priority = priority
                best_candidate = c
            elif priority == best_priority and best_candidate:
                # Tie-break: latest effective date, then latest known_at, then source_id
                if c.effective_date > best_candidate.effective_date:
                    best_candidate = c
                elif c.effective_date == best_candidate.effective_date:
                    c_known = c.known_at or date.min
                    b_known = best_candidate.known_at or date.min
                    if c_known > b_known:
                        best_candidate = c
                    elif c_known == b_known:
                        if c.source_id < best_candidate.source_id:
                            best_candidate = c

        if best_candidate is None:
            # Fallback to unknown
            mismatched = [c for c in usable if c.currency != target_currency]
            warnings = []
            if mismatched:
                warnings.append(f"Excluded {len(mismatched)} candidates due to currency mismatch")

            return ValuationResult(
                as_of=as_of,
                total_value=0.0,
                holdings_value=0.0,
                cash_value=0.0,
                base_currency=target_currency,
                amount=None,
                quality=ValuationQuality.UNKNOWN,
                freshness=ValuationFreshness.UNKNOWN,
                is_estimate=True,
                age_days=0,
                warnings=warnings,
            )

        # 2. Build result from best candidate
        amount = best_candidate.get_amount()
        age = (as_of - best_candidate.effective_date).days

        freshness = ValuationFreshness.CURRENT if age == 0 else ValuationFreshness.STALE

        # is_estimate logic: True if stale or quality is estimated
        is_estimate = (freshness == ValuationFreshness.STALE) or (best_candidate.quality == ValuationQuality.ESTIMATED)

        # If it was a carry-forward, ensure quality reflects that
        quality = best_candidate.quality
        if freshness == ValuationFreshness.STALE and quality == ValuationQuality.CONFIRMED:
            quality = ValuationQuality.ESTIMATED

        return ValuationResult(
            as_of=as_of,
            total_value=0.0,
            holdings_value=0.0,
            cash_value=0.0,
            base_currency=target_currency,
            amount=amount,
            currency=best_candidate.currency,
            valuation_date=best_candidate.effective_date,
            known_at=best_candidate.known_at,
            source_type=best_candidate.source_type,
            source_id=best_candidate.source_id,
            quality=quality,
            freshness=freshness,
            is_estimate=is_estimate,
            age_days=age,
            warnings=[],
        )

    def value_single(
        self,
        candidates: List[ValuationCandidate],
        as_of: date,
        target_currency: str = "CNY",
        freshness_thresholds: Optional[Dict[str, int]] = None,
    ) -> ValuationResult:
        """Select the best single-asset valuation from candidates.

        Convenience instance method — delegates to select_best().
        Implements the priority chain:
        manual confirmed > market_price > public_nav > carried_forward > unknown.
        """
        return self.select_best(candidates, as_of, target_currency, freshness_thresholds)
