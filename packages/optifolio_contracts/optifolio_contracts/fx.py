"""FX rate provider protocol.

FinData and OptiFolio both need FX rates, but from different sources.
The protocol separates the "what" (get a rate) from the "how" (yfinance,
hardcoded table, database lookup).
"""

from __future__ import annotations

from datetime import date
from typing import Protocol


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
