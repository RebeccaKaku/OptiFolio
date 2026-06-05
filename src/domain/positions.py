"""Position snapshot contract — a point-in-time holding in an account."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class PositionSnapshot:
    """A single position (product holding) in a specific account on a given date."""

    date: date
    account_id: str
    product_id: str
    quantity: Optional[float] = None
    market_value: float = 0.0
    cost_basis: Optional[float] = None
    currency: str = "CNY"
    available_amount: Optional[float] = None
    lockup_end_date: Optional[date] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        d["lockup_end_date"] = (
            self.lockup_end_date.isoformat() if self.lockup_end_date else None
        )
        return d
