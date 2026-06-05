"""FeeProcessor — applies fee schedules to portfolio valuations.

Default: empty schedule (no fees). Users configure fees via YAML or
by building FeeSchedule objects programmatically.

Stub implementation: all logic is correct, but automated detection
from broker statements is deferred.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.domain import (
    FeeSchedule,
    ValuationResult,
)


class FeeProcessor:
    """Applies fee schedules to portfolio valuations."""

    def __init__(self, schedule: Optional[FeeSchedule] = None):
        self.schedule = schedule or FeeSchedule(rules=(), name="no_fees")

    def apply_to_valuation(
        self,
        result: ValuationResult,
        context: Optional[Dict[str, Any]] = None,
    ) -> ValuationResult:
        """Calculate fees and return a new ValuationResult with fee_adjustments set.

        The ``context`` dict can carry trade_value, aum, days, etc.
        When empty, no fees are applied (stub behavior).
        """
        if not context or not self.schedule.rules:
            return result

        fee_total = self.schedule.calculate_total(context)
        if fee_total == 0:
            return result

        # Create a new result with the fee deducted
        return ValuationResult(
            as_of=result.as_of,
            total_value=result.total_value - fee_total,
            holdings_value=result.holdings_value,
            cash_value=result.cash_value - fee_total,
            base_currency=result.base_currency,
            positions=result.positions,
            cash_breakdown=result.cash_breakdown,
            fx_rates=result.fx_rates,
            price_date=result.price_date,
            corporate_action_adjustments=result.corporate_action_adjustments,
            fee_adjustments=result.fee_adjustments + fee_total,
        )

    def estimate_transaction_cost(
        self, trade_value: float, action: str = "buy"
    ) -> float:
        """Estimate fee for a planned trade."""
        return self.schedule.calculate_total(
            {"trade_value": trade_value, "action": action}
        )
