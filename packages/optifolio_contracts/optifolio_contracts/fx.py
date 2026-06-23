"""FX rate provider protocol and a hardcoded fallback implementation.

FinData and OptiFolio both need FX rates, but from different sources.
The protocol separates the "what" (get a rate) from the "how" (yfinance,
hardcoded table, database lookup).
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Protocol, Tuple


class FxRateProviderProtocol(Protocol):
    """Protocol for resolving FX conversion rates.

    OptiFolio's ValuationEngine and FinData's DataProvider both need FX rates.
    This protocol lets each side provide its own implementation while agreeing
    on the interface.
    """

    def get_rate(
        self, from_currency: str, to_currency: str, *, as_of: date | None = None
    ) -> float:
        """Resolve the conversion rate from_currency → to_currency.

        Args:
            from_currency: Source currency (e.g. 'USD').
            to_currency: Target currency (e.g. 'CNY').
            as_of: If provided, look for rate on this date. When None,
                   use the latest available rate.

        Returns:
            Exchange rate as a float. Must return 1.0 when from_currency == to_currency.

        Raises:
            FxRateError: If no rate can be resolved (implementations may choose
                         to fall back to a hardcoded table instead of raising).
        """
        ...


#: Default hardcoded FX rates used as an offline safety net.
#: Rates are expressed as "1 unit of from_currency = X units of to_currency".
DEFAULT_FALLBACK_RATES: Dict[Tuple[str, str], float] = {
    ("USD", "CNY"): 7.2,
    ("CNY", "USD"): 0.139,
    ("EUR", "USD"): 1.1,
    ("USD", "EUR"): 0.91,
    ("EUR", "CNY"): 7.92,
    ("CNY", "EUR"): 0.1263,
    ("USD", "JPY"): 150.0,
    ("JPY", "USD"): 0.0067,
    ("GBP", "USD"): 1.27,
    ("USD", "GBP"): 0.79,
}


class HardcodedFxRateProvider:
    """Offline FX rate provider backed by a static fallback table.

    This provider is intended as the last-resort fallback in environments
    without network access or when all live/repository sources fail. It
    never raises; unknown pairs fall back to 1.0 for identical currencies
    and raise ``FxRateError`` otherwise.
    """

    def __init__(
        self, fallback_rates: Dict[Tuple[str, str], float] | None = None
    ) -> None:
        self._fallback = fallback_rates or DEFAULT_FALLBACK_RATES.copy()

    def get_rate(
        self, from_currency: str, to_currency: str, *, as_of: date | None = None
    ) -> float:
        """Return a hardcoded FX rate or raise if no fallback exists."""
        if from_currency == to_currency:
            return 1.0

        pair = (from_currency, to_currency)
        if pair in self._fallback:
            return float(self._fallback[pair])

        # Try the inverse pair
        inverse = (to_currency, from_currency)
        if inverse in self._fallback:
            rate = self._fallback[inverse]
            if rate != 0:
                return 1.0 / rate

        raise FxRateError(
            f"No hardcoded FX rate for {from_currency} → {to_currency}"
        )


class FxRateError(Exception):
    """Raised when an FX rate cannot be resolved."""
