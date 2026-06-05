"""Fee and tax rule types for portfolio valuation.

Fees are frozen dataclasses implementing the ``FeeRule`` ABC.
All logic is correct stubs; automatic fee detection from broker
statements is deferred.

Default behavior: no fees applied (empty FeeSchedule).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class FeeRule(ABC):
    """Abstract base for all fee/tax rules.

    Each rule's ``calculate()`` receives a context dict with keys like:
    - trade_value: float — notional value of the trade
    - aum: float — assets under management
    - days: int — number of days for accrual
    - asset_id: str
    - action: str — "buy", "sell", "hold"
    - taxable_amount: float — base for tax calculation
    """

    name: str = "fee_rule"
    applies_to: str = "all"  # "all", "buy", "sell", or an asset_id

    @abstractmethod
    def calculate(self, context: Dict[str, Any]) -> float:
        """Calculate fee given context. Returns fee in base currency."""
        ...

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TransactionFee(FeeRule):
    """Flat-rate or proportional per-trade commission."""

    rate: float = 0.0            # e.g. 0.001 = 0.1%
    fixed_per_trade: float = 0.0
    minimum: float = 0.0
    maximum: float = float("inf")

    def calculate(self, context: Dict[str, Any]) -> float:
        trade_value = abs(float(context.get("trade_value", 0.0)))
        if trade_value <= 0:
            return 0.0
        fee = trade_value * self.rate + self.fixed_per_trade
        return max(self.minimum, min(fee, self.maximum))


@dataclass(frozen=True)
class ManagementFee(FeeRule):
    """Recurring AUM-based management fee, accrued daily."""

    annual_rate: float = 0.0  # e.g. 0.01 = 1% per year

    def calculate(self, context: Dict[str, Any]) -> float:
        aum = float(context.get("aum", 0.0))
        if aum <= 0:
            return 0.0
        days = max(int(context.get("days", 1)), 1)
        # Daily accrual: (1 + annual)^(days/365) - 1, approximated
        daily_rate = (1.0 + self.annual_rate) ** (days / 365.0) - 1.0
        return aum * daily_rate


@dataclass(frozen=True)
class TaxRule(FeeRule):
    """Tax on gains, dividends, or interest."""

    rate: float = 0.0          # e.g. 0.20 = 20%
    tax_on: str = "gains"      # "gains", "dividends", "interest"

    def calculate(self, context: Dict[str, Any]) -> float:
        base = float(context.get("taxable_amount", 0.0))
        if base <= 0:
            return 0.0
        return base * self.rate


@dataclass(frozen=True)
class FeeSchedule:
    """Collection of fee rules applied in order."""

    rules: Tuple[FeeRule, ...] = field(default_factory=tuple)
    name: str = "default"

    def calculate_total(self, context: Dict[str, Any]) -> float:
        """Sum of all matching rules for this context."""
        total = 0.0
        action = str(context.get("action", "all"))
        for rule in self.rules:
            if rule.applies_to in ("all", action, context.get("asset_id", "")):
                total += rule.calculate(context)
        return total

    def with_rule(self, rule: FeeRule) -> "FeeSchedule":
        """Return a new schedule with one additional rule."""
        return FeeSchedule(rules=self.rules + (rule,), name=self.name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "rules": [rule.to_dict() for rule in self.rules],
        }
