"""Core valuation logic for portfolio book positions.

This module implements the valuation source priority engine. It ensures that
every asset valuation has a clear audit trail (source, date, quality).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any


class ValuationQuality(str, Enum):
    """Subjective quality of a valuation."""
    CONFIRMED = "confirmed"    # Explicitly verified by human or authoritative source
    REPORTED = "reported"     # Reported by a third party but not yet 'confirmed'
    ESTIMATED = "estimated"   # Calculated via interpolation, carry-forward, or proxy
    UNKNOWN = "unknown"       # No reliable data available


class ValuationFreshness(str, Enum):
    """Temporal relevance of a valuation."""
    CURRENT = "current"       # Matches the requested valuation date
    STALE = "stale"           # Older than the requested date or stale threshold
    UNKNOWN = "unknown"       # No date information available


@dataclass(frozen=True)
class ValuationCandidate:
    """A potential value for a position from a specific source."""
    amount: Optional[float] = None
    price: Optional[float] = None
    quantity: Optional[float] = None
    currency: str = "CNY"
    effective_date: Optional[date] = None
    known_at: Optional[date] = None
    source_id: str = "unknown"
    source_type: str = "unknown"  # manual, public, etc.
    quality: ValuationQuality = ValuationQuality.UNKNOWN

    def get_amount(self) -> Optional[float]:
        """Calculate amount from price and quantity if direct amount is missing."""
        if self.amount is not None:
            return self.amount
        if self.price is not None and self.quantity is not None:
            return self.price * self.quantity
        return None


@dataclass(frozen=True)
class ValuationResult:
    """The final selected valuation for a position."""
    amount: Optional[float]
    currency: str
    valuation_date: Optional[date]
    known_at: Optional[date]
    source_type: str
    source_id: str
    quality: ValuationQuality
    freshness: ValuationFreshness
    is_estimate: bool
    age_days: int
    warnings: List[str] = field(default_factory=list)


class ValuationEngine:
    """Pure logic for selecting the best valuation from multiple candidates."""

    @staticmethod
    def select_best(
        candidates: List[ValuationCandidate],
        as_of: date,
        target_currency: str = "CNY",
        freshness_thresholds: Optional[Dict[str, int]] = None
    ) -> ValuationResult:
        """Select the best valuation candidate based on priority rules.

        Priority:
        1. Manual confirmed (effective_date == as_of)
        2. Public NAV/Price (effective_date <= as_of, within threshold)
        3. Last known (stale carry-forward, effective_date < as_of)
        4. Unknown

        Rules:
        - Future dates are rejected.
        - Quantity is required for public price candidates.
        - Zero amount is a valid value, None is unknown.
        - Currency mismatch returns unknown with a warning.
        """
        thresholds = freshness_thresholds or {}
        # Default threshold is 3 days unless specified
        default_threshold = thresholds.get("default", 3)

        # 1. Filter usable candidates (no future dates)
        usable = [c for c in candidates if c.effective_date and c.effective_date <= as_of]

        best_candidate: Optional[ValuationCandidate] = None
        best_priority = 99

        for c in usable:
            amount = c.get_amount()
            if amount is None:
                continue

            # Check currency mismatch
            if c.currency != target_currency:
                # Per spec: "币种不符返回 unknown/warning"
                # But if we have no other choice, we might still evaluate it?
                # Actually, the spec says "不得假设 price currency 等于 position currency；币种不符返回 unknown/warning"
                continue

            priority = 99
            if c.source_type == "manual" and c.quality == ValuationQuality.CONFIRMED and c.effective_date == as_of:
                priority = 1
            elif c.source_type == "public":
                # Check freshness
                age = (as_of - c.effective_date).days
                threshold = thresholds.get(c.source_id, default_threshold)
                if age <= threshold:
                    priority = 2
            elif c.source_type == "manual" and c.effective_date < as_of:
                priority = 3
            elif c.source_type == "manual" and c.quality == ValuationQuality.REPORTED and c.effective_date == as_of:
                # Giving manual reported at as_of a higher priority than carry-forward but lower than public?
                # The spec says: manual_confirmed > public_nav > last_known > unknown
                # Let's group reported at as_of with priority 1 but lower sub-priority or just priority 2?
                # Actually, "同一 as_of 的人工确认 market_value" is priority 1.
                # If it's reported but not confirmed, maybe priority 2.5?
                # Let's stick to the 4 levels in the goal description:
                # manual_confirmed > public_nav × quantity > last_known > unknown
                priority = 3 # Grouped with last_known for now

            if priority < best_priority:
                best_priority = priority
                best_candidate = c
            elif priority == best_priority and best_candidate:
                # Tie-break: latest effective date, then latest known_at, then source_id
                if c.effective_date > best_candidate.effective_date:
                    best_candidate = c
                elif c.effective_date == best_candidate.effective_date:
                    c_known = c.known_at or date.min
                    b_known = best_candidate.known_at or date.min
                    if c_known > b_known:
                        best_candidate = c
                    elif c_known == b_known:
                        if c.source_id < best_candidate.source_id:
                            best_candidate = c

        if best_candidate is None:
            # Fallback to unknown
            # Check if there were any candidates with currency mismatch to add warning
            mismatched = [c for c in usable if c.currency != target_currency]
            warnings = []
            if mismatched:
                warnings.append(f"Excluded {len(mismatched)} candidates due to currency mismatch")

            return ValuationResult(
                amount=None,
                currency=target_currency,
                valuation_date=None,
                known_at=None,
                source_type="none",
                source_id="none",
                quality=ValuationQuality.UNKNOWN,
                freshness=ValuationFreshness.UNKNOWN,
                is_estimate=True,
                age_days=0,
                warnings=warnings
            )

        # 2. Build result from best candidate
        amount = best_candidate.get_amount()
        age = (as_of - best_candidate.effective_date).days

        freshness = ValuationFreshness.CURRENT if age == 0 else ValuationFreshness.STALE

        # is_estimate logic: True if stale or quality is estimated
        is_estimate = (freshness == ValuationFreshness.STALE) or (best_candidate.quality == ValuationQuality.ESTIMATED)

        # If it was a carry-forward, ensure quality reflects that if it wasn't already estimated
        quality = best_candidate.quality
        if freshness == ValuationFreshness.STALE and quality == ValuationQuality.CONFIRMED:
            # Stale confirmed is still an estimate in terms of current value
            quality = ValuationQuality.ESTIMATED

        return ValuationResult(
            amount=amount,
            currency=best_candidate.currency,
            valuation_date=best_candidate.effective_date,
            known_at=best_candidate.known_at,
            source_type=best_candidate.source_type,
            source_id=best_candidate.source_id,
            quality=quality,
            freshness=freshness,
            is_estimate=is_estimate,
            age_days=age,
            warnings=[]
        )
