"""FX exposure analysis — aggregate portfolio currency risk.

Groups positions and cash holdings by currency, computes the percentage exposure
to each currency relative to total portfolio value, and estimates the sensitivity
of the portfolio's base-currency value to a 1% move in each FX rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List

from src.domain import CashHolding, PositionValue


@dataclass
class FxExposureItem:
    """Exposure breakdown for a single currency."""

    currency: str
    value_base: float
    pct: float
    asset_ids: List[str]
    sensitivity_note: str

    def to_dict(self) -> dict:
        return {
            "currency": self.currency,
            "value_base": self.value_base,
            "pct": round(self.pct, 2),
            "asset_ids": self.asset_ids,
            "sensitivity_note": self.sensitivity_note,
        }


@dataclass
class FxExposureReport:
    """Aggregated FX exposure view for a portfolio."""

    as_of: date
    base_currency: str
    total_value: float
    exposures: List[FxExposureItem]
    net_non_base_pct: float
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of.isoformat(),
            "base_currency": self.base_currency,
            "total_value": self.total_value,
            "exposures": [e.to_dict() for e in self.exposures],
            "net_non_base_pct": round(self.net_non_base_pct, 2),
            "warnings": self.warnings,
        }


class FxExposureAnalyzer:
    """Level 0 FX exposure — aggregates by position quote currency ONLY.

    IMPORTANT LIMITATION: This is a LABEL-LEVEL analysis. It groups by
    the position's declared currency (e.g., a QDII fund shows as CNY
    even though it holds USD assets). It does NOT look through to
    fund/wealth-product underlying currency exposures or hedges.

    For accurate FX exposure decomposition, Level 1 (holdings-based)
    or Level 2 (look-through) analysis is required. See
    docs/FINANCIAL_LOGIC_AND_MODULE_DESIGN.md for the look-through levels.

    This Level 0 view is useful as a FIRST APPROXIMATION but should
    NEVER be presented as complete FX risk analysis without the
    limitation visible.

    Usage::

        analyzer = FxExposureAnalyzer()
        report = analyzer.analyze(
            positions=valuation_result.positions,
            cash_breakdown=valuation_result.cash_breakdown,
            base_currency="CNY",
            total_value=valuation_result.total_value,
        )
    """

    DEFAULT_WARNING_THRESHOLD_PCT: float = 20.0

    def analyze(
        self,
        positions: Dict[str, PositionValue],
        cash_breakdown: Dict[str, CashHolding],
        base_currency: str,
        total_value: float,
        as_of: date,
    ) -> FxExposureReport:
        """Aggregate positions and cash into per-currency exposure items.

        Args:
            positions: Per-asset position values (from ValuationResult).
            cash_breakdown: Per-currency cash holdings (from ValuationResult).
            base_currency: The portfolio's reporting currency (e.g. "CNY").
            total_value: Total portfolio value in base currency.
            as_of: Valuation date for the report.
        """
        if total_value <= 0:
            return FxExposureReport(
                as_of=as_of,
                base_currency=base_currency,
                total_value=0.0,
                exposures=[],
                net_non_base_pct=0.0,
            )

        # Aggregate by currency: {currency: {"value_base": float, "asset_ids": List[str]}}
        currency_groups: Dict[str, dict] = {}

        # 1. Positions
        for pos in positions.values():
            cur = pos.currency
            if cur not in currency_groups:
                currency_groups[cur] = {"value_base": 0.0, "asset_ids": []}
            currency_groups[cur]["value_base"] += pos.value_base
            currency_groups[cur]["asset_ids"].append(pos.asset_id)

        # 2. Cash holdings
        for cash in cash_breakdown.values():
            cur = cash.currency
            if cur not in currency_groups:
                currency_groups[cur] = {"value_base": 0.0, "asset_ids": []}
            currency_groups[cur]["value_base"] += cash.value_base

        # Build exposure items (sorted by value descending)
        exposures: List[FxExposureItem] = []
        for cur in sorted(currency_groups, key=lambda c: currency_groups[c]["value_base"], reverse=True):
            group = currency_groups[cur]
            pct = (group["value_base"] / total_value) * 100.0

            if cur == base_currency:
                note = f"{cur} 为本币，无汇率波动风险"
            else:
                delta = group["value_base"] * 0.01
                note = f"{cur}/{base_currency} ±1% → 净值波动约 ¥{delta:,.2f}"

            exposures.append(FxExposureItem(
                currency=cur,
                value_base=group["value_base"],
                pct=pct,
                asset_ids=sorted(group["asset_ids"]),
                sensitivity_note=note,
            ))

        # Net non-base-currency percentage
        net_non_base_pct = sum(
            e.pct for e in exposures if e.currency != base_currency
        )

        # Warnings
        warnings: List[str] = []
        if net_non_base_pct > self.DEFAULT_WARNING_THRESHOLD_PCT:
            warnings.append(
                f"非本币敞口 {net_non_base_pct:.1f}% 超过 {self.DEFAULT_WARNING_THRESHOLD_PCT:.0f}% 目标区间"
            )
        for e in exposures:
            if e.currency != base_currency and e.pct > self.DEFAULT_WARNING_THRESHOLD_PCT:
                warnings.append(
                    f"单一货币 {e.currency} 敞口 {e.pct:.1f}% 超过 {self.DEFAULT_WARNING_THRESHOLD_PCT:.0f}% 目标区间"
                )

        return FxExposureReport(
            as_of=as_of,
            base_currency=base_currency,
            total_value=total_value,
            exposures=exposures,
            net_non_base_pct=net_non_base_pct,
            warnings=warnings,
        )
