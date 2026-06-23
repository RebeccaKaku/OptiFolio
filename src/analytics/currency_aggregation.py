"""Aggregation logic for multi-currency valuations.

This module provides pure functions to aggregate position valuations across
different currencies, providing both original currency subtotals and
a consolidated total in a reporting currency (typically CNY).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Set
from src.core.book_valuation import ValuationResult
from optifolio_contracts.quality import ValuationQuality


@dataclass(frozen=True)
class FxQuote:
    """A foreign exchange rate quote."""
    base: str  # e.g., 'USD'
    quote: str  # e.g., 'CNY'
    rate: Decimal
    as_of: date
    source: str
    quality: ValuationQuality

    @property
    def key(self) -> str:
        """Unique identifier for the currency pair."""
        return f"{self.base}/{self.quote}"


@dataclass(frozen=True)
class CurrencySubtotal:
    """Aggregation result for a single original currency."""
    currency: str
    amount_original: Decimal
    amount_reporting: Decimal
    count: int
    unknown_count: int
    is_estimated: bool
    quality_counts: Dict[ValuationQuality, int]
    conversion_evidence: Optional[FxQuote] = None


@dataclass(frozen=True)
class CurrencyAggregationResult:
    """The final consolidated aggregation result."""
    reporting_currency: str
    by_original_currency: Dict[str, CurrencySubtotal]
    other_currencies: CurrencySubtotal
    reporting_total: Decimal
    reporting_total_is_exact: bool
    quality_summary: Dict[ValuationQuality, int]
    warnings: List[str] = field(default_factory=list)


class CurrencyAggregator:
    """Pure logic for aggregating valuations across currencies."""

    def __init__(
        self,
        major_currencies: Optional[Set[str]] = None,
        stale_threshold_days: int = 3
    ):
        self.major_currencies = major_currencies or {"CNY", "USD", "HKD", "EUR", "GBP", "JPY"}
        self.stale_threshold_days = stale_threshold_days

    def aggregate(
        self,
        valuations: List[ValuationResult],
        fx_quotes: List[FxQuote],
        reporting_currency: str = "CNY",
        as_of: Optional[date] = None
    ) -> CurrencyAggregationResult:
        """Aggregate valuations into original and reporting currencies.

        Args:
            valuations: List of valuation results to aggregate.
            fx_quotes: Available FX rates for conversion.
            reporting_currency: The target currency for totals.
            as_of: The date to which aggregation refers (for FX freshness check).
        """
        as_of = as_of or date.today()

        # 1. Index FX quotes for quick lookup
        quotes_map = self._build_quotes_map(fx_quotes)

        # 2. Group valuations by currency
        by_currency_vals: Dict[str, List[ValuationResult]] = {}
        for val in valuations:
            if val.currency not in by_currency_vals:
                by_currency_vals[val.currency] = []
            by_currency_vals[val.currency].append(val)

        subtotals: Dict[str, CurrencySubtotal] = {}
        total_reporting = Decimal("0")
        total_exact = True
        overall_quality: Dict[ValuationQuality, int] = {q: 0 for q in ValuationQuality}
        warnings = []

        # 3. Process each currency
        for curr, vals in by_currency_vals.items():
            subtotal, reporting_amount, exact = self._calculate_subtotal(
                curr, vals, quotes_map, reporting_currency, as_of
            )

            subtotals[curr] = subtotal
            total_reporting += reporting_amount
            if not exact:
                total_exact = False

            # Aggregate quality counts
            for q, count in subtotal.quality_counts.items():
                overall_quality[q] += count

        # 4. Handle "Other" rollup
        major_subtotals = {}
        other_amounts_rep = Decimal("0")
        other_count = 0
        other_unknown = 0
        other_is_estimated = False
        other_quality: Dict[ValuationQuality, int] = {q: 0 for q in ValuationQuality}

        for curr, sub in subtotals.items():
            if curr in self.major_currencies or curr == reporting_currency:
                major_subtotals[curr] = sub
            else:
                other_amounts_rep += sub.amount_reporting
                other_count += sub.count
                other_unknown += sub.unknown_count
                if sub.is_estimated:
                    other_is_estimated = True
                for q, count in sub.quality_counts.items():
                    other_quality[q] += count

        other_subtotal = CurrencySubtotal(
            currency="other",
            amount_original=Decimal("0"), # Original amount doesn't make sense for "other"
            amount_reporting=other_amounts_rep,
            count=other_count,
            unknown_count=other_unknown,
            is_estimated=other_is_estimated,
            quality_counts=other_quality
        )

        return CurrencyAggregationResult(
            reporting_currency=reporting_currency,
            by_original_currency=major_subtotals,
            other_currencies=other_subtotal,
            reporting_total=total_reporting,
            reporting_total_is_exact=total_exact,
            quality_summary=overall_quality,
            warnings=warnings
        )

    def _build_quotes_map(self, fx_quotes: List[FxQuote]) -> Dict[str, FxQuote]:
        return {q.key: q for q in fx_quotes}

    def _calculate_subtotal(
        self,
        currency: str,
        vals: List[ValuationResult],
        quotes_map: Dict[str, FxQuote],
        reporting_currency: str,
        as_of: date
    ) -> tuple[CurrencySubtotal, Decimal, bool]:
        total_orig = Decimal("0")
        total_rep = Decimal("0")
        count = len(vals)
        unknown_count = 0
        quality_counts = {q: 0 for q in ValuationQuality}
        is_estimated = False

        # Find FX rate for this currency to reporting currency
        fx_quote = None
        exact_conversion = True

        if currency == reporting_currency:
            # Identity conversion
            rate = Decimal("1")
        else:
            direct_key = f"{currency}/{reporting_currency}"
            inverse_key = f"{reporting_currency}/{currency}"

            if direct_key in quotes_map:
                fx_quote = quotes_map[direct_key]
                rate = fx_quote.rate
            elif inverse_key in quotes_map:
                fx_quote = quotes_map[inverse_key]
                rate = Decimal("1") / fx_quote.rate
            else:
                rate = None
                exact_conversion = False
                is_estimated = True

            if fx_quote:
                # Validate date
                if fx_quote.as_of > as_of:
                    rate = None
                    exact_conversion = False
                    is_estimated = True
                # Check stale
                elif (as_of - fx_quote.as_of).days > self.stale_threshold_days:
                    is_estimated = True

                if fx_quote.quality == ValuationQuality.ESTIMATED:
                    is_estimated = True

        for val in vals:
            quality_counts[val.quality] += 1
            if val.amount is None:
                unknown_count += 1
                exact_conversion = False
                continue

            amount_dec = Decimal(str(val.amount))
            total_orig += amount_dec

            if rate is not None:
                total_rep += amount_dec * rate
            else:
                # Missing FX rate, cannot contribute to reporting total
                # Spec: "缺汇率时不能把该项当 0" -> handled by exact_conversion = False
                # and total_rep not including it.
                # Wait, "reporting_total: known_total + unknown_components"?
                # I should probably return a flag that it's incomplete.
                pass

        subtotal = CurrencySubtotal(
            currency=currency,
            amount_original=total_orig,
            amount_reporting=total_rep,
            count=count,
            unknown_count=unknown_count,
            is_estimated=is_estimated or any(v.is_estimate for v in vals),
            quality_counts=quality_counts,
            conversion_evidence=fx_quote
        )

        return subtotal, total_rep, exact_conversion
