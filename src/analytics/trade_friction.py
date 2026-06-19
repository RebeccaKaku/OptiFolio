"""Trade friction and no-trade bands analysis.

This module provides pure functions to calculate trading costs and define no-trade bands
to avoid trades for small deviations or high friction.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Literal


@dataclass(frozen=True)
class AllocationFrictionInput:
    """Friction parameters for a specific product allocation."""
    buy_fee_rate: Optional[Decimal] = None
    sell_fee_rate: Optional[Decimal] = None
    mgmt_fee_diff_rate: Optional[Decimal] = None
    fixed_fees: Optional[Decimal] = None
    fx_spread_rate: Optional[Decimal] = None
    min_trade_amount: Optional[Decimal] = None
    lock_up_days: Optional[int] = None
    no_trade_band_pct: Optional[Decimal] = None


@dataclass(frozen=True)
class TradeFrictionRequest:
    """Request for trade friction analysis."""
    amount_reporting: Decimal
    total_portfolio_value_reporting: Decimal
    expected_holding_period_years: Decimal
    reporting_currency: str
    friction_input: AllocationFrictionInput
    monetized_benefit_annual_rate: Optional[Decimal] = None
    fx_rate_to_reporting: Decimal = Decimal("1.0")


@dataclass(frozen=True)
class TradeFrictionResult:
    """Result of trade friction analysis."""
    gap_improvement_weight: Decimal
    total_known_cost_amount: Decimal
    one_time_costs: Decimal
    holding_costs: Decimal
    reporting_currency: str
    unknown_costs: List[str]
    no_trade: bool
    reasons: List[str]
    eligible_allocations: Decimal  # In reporting currency
    fx_evidence: str
    monetized_benefit: Optional[Decimal] = None
    net_monetized_benefit: Optional[Decimal] = None
    break_even_horizon: Optional[Decimal] = None


def calculate_trade_friction(request: TradeFrictionRequest) -> TradeFrictionResult:
    """
    Calculate trading costs and determine if a trade should be avoided.
    """
    fi = request.friction_input
    amount = request.amount_reporting
    total_val = request.total_portfolio_value_reporting
    holding_period = request.expected_holding_period_years

    gap_improvement_weight = amount / total_val if total_val > 0 else Decimal("0")

    unknown_costs = []
    if fi.buy_fee_rate is None: unknown_costs.append("buy_fee_rate")
    if fi.sell_fee_rate is None: unknown_costs.append("sell_fee_rate")
    if fi.fixed_fees is None: unknown_costs.append("fixed_fees")
    if fi.fx_spread_rate is None: unknown_costs.append("fx_spread_rate")
    if fi.mgmt_fee_diff_rate is None: unknown_costs.append("mgmt_fee_diff_rate")

    # One-time costs
    one_time_costs = Decimal("0")
    if fi.buy_fee_rate is not None: one_time_costs += fi.buy_fee_rate * amount
    if fi.sell_fee_rate is not None: one_time_costs += fi.sell_fee_rate * amount
    if fi.fx_spread_rate is not None: one_time_costs += fi.fx_spread_rate * amount
    if fi.fixed_fees is not None: one_time_costs += fi.fixed_fees

    # Holding costs
    holding_costs = Decimal("0")
    if fi.mgmt_fee_diff_rate is not None:
        holding_costs = fi.mgmt_fee_diff_rate * holding_period * amount

    total_known_cost_amount = one_time_costs + holding_costs

    # Benefit
    monetized_benefit = None
    net_monetized_benefit = None
    break_even_horizon = None

    if request.monetized_benefit_annual_rate is not None:
        monetized_benefit = request.monetized_benefit_annual_rate * holding_period * amount
        net_monetized_benefit = monetized_benefit - total_known_cost_amount

        # Break-even horizon (years)
        # one_time_costs + (mgmt_diff * t * amount) = benefit_rate * t * amount
        # t = one_time_costs / (benefit_rate - mgmt_diff) / amount
        denom = (request.monetized_benefit_annual_rate - (fi.mgmt_fee_diff_rate or Decimal("0"))) * amount
        if denom > 0:
            break_even_horizon = one_time_costs / denom
        elif one_time_costs == 0:
            break_even_horizon = Decimal("0")

    # no-trade logic
    no_trade = False
    reasons = []

    # 1. Band deviation
    if fi.no_trade_band_pct is not None:
        if gap_improvement_weight <= fi.no_trade_band_pct:
            no_trade = True
            reasons.append(f"Weight deviation {gap_improvement_weight:.2%} within no-trade band {fi.no_trade_band_pct:.2%}")

    # 2. Min amount
    if fi.min_trade_amount is not None:
        if amount < fi.min_trade_amount:
            no_trade = True
            reasons.append(f"Trade amount {amount} below minimum {fi.min_trade_amount}")

    # 3. Economics
    if monetized_benefit is not None:
        if net_monetized_benefit <= 0:
            no_trade = True
            reasons.append(f"Monetized benefit {monetized_benefit} does not exceed costs {total_known_cost_amount}")
    else:
        # no_trade_due_to_economics=unknown case mentioned in spec.
        # For the boolean no_trade, we don't force True just because benefit is unknown.
        pass

    # 4. Lock-up
    if fi.lock_up_days is not None:
        if Decimal(fi.lock_up_days) > holding_period * Decimal("365"):
            no_trade = True
            reasons.append(f"Lock-up period {fi.lock_up_days} days exceeds expected holding period {holding_period * 365:.1f} days")

    # 5. Unknown critical costs
    critical_missing = [c for c in unknown_costs if c != "mgmt_fee_diff_rate"]
    if critical_missing:
        no_trade = True
        reasons.append(f"Critical costs unknown: {', '.join(critical_missing)}")

    eligible_allocations = Decimal("0") if no_trade else amount

    fx_evidence = f"1.0 (Direct reporting)" if request.fx_rate_to_reporting == 1 else f"{request.fx_rate_to_reporting}"

    return TradeFrictionResult(
        gap_improvement_weight=gap_improvement_weight,
        total_known_cost_amount=total_known_cost_amount,
        one_time_costs=one_time_costs,
        holding_costs=holding_costs,
        reporting_currency=request.reporting_currency,
        unknown_costs=unknown_costs,
        no_trade=no_trade,
        reasons=reasons,
        eligible_allocations=eligible_allocations,
        fx_evidence=fx_evidence,
        monetized_benefit=monetized_benefit,
        net_monetized_benefit=net_monetized_benefit,
        break_even_horizon=break_even_horizon
    )
