"""Cashflow event contract — a monetary movement related to a product."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class CashflowEvent:
    """A cashflow event such as purchase, redemption, coupon, dividend, etc.

    event_type is one of:
      purchase, redemption, coupon, interest, dividend, fee, tax,
      maturity, fx_conversion
    """

    event_id: str
    product_id: str
    event_type: str  # purchase, redemption, coupon, interest, dividend, fee, tax, maturity, fx_conversion
    trade_date: date
    account_id: Optional[str] = None
    settle_date: Optional[date] = None
    amount: float = 0.0
    currency: str = "CNY"
    units: Optional[float] = None
    known_at: Optional[datetime] = None
    source: str = "manual"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["trade_date"] = self.trade_date.isoformat()
        d["settle_date"] = (
            self.settle_date.isoformat() if self.settle_date else None
        )
        d["known_at"] = (
            self.known_at.isoformat() if self.known_at else None
        )
        return d
