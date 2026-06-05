"""Instrument definition contract — tradable/marketable financial instruments."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class InstrumentDefinition:
    """A financial instrument that underlies one or more products.

    instrument_type is one of:
      equity, fund, bank_wealth_product, bond, cash, fx_pair,
      crypto_spot, derivative

    valuation_method is one of:
      ohlcv_close, published_nav, mark_to_market, amortized_cost
    """

    instrument_id: str
    symbol: str
    name: str = ""
    instrument_type: str = "equity"  # equity, fund, bank_wealth_product, bond, cash, fx_pair, crypto_spot, derivative
    quote_currency: str = "CNY"
    exchange_id: Optional[str] = None
    calendar_id: str = "SSE"
    timezone: str = "Asia/Shanghai"
    tradable: bool = True
    valuation_method: str = "ohlcv_close"  # ohlcv_close, published_nav, mark_to_market, amortized_cost
    contract_multiplier: float = 1.0
    settlement_lag_days: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
