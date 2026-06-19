"""Target allocation ranges and gap analysis.

This module provides pure functions to compare current portfolio exposures
against target allocation ranges (min/max weights) and identify gaps.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Literal


@dataclass(frozen=True)
class TargetRange:
    """A target allocation range for a specific bucket."""
    dimension: str  # purpose_bucket, currency, asset_class, issuer, product
    bucket: str
    min_weight: Decimal
    max_weight: Decimal
    priority: int = 0

    def __post_init__(self):
        if not (Decimal("0") <= self.min_weight <= self.max_weight <= Decimal("1")):
            raise ValueError(
                f"Invalid range for {self.bucket}: 0 <= {self.min_weight} <= {self.max_weight} <= 1 must hold."
            )


@dataclass(frozen=True)
class TargetSet:
    """A collection of target ranges for a specific scope."""
    scope: str  # e.g., 'total_assets', 'core_reserve'
    denominator_value: Decimal
    reporting_currency: str
    exhaustive: bool  # Whether the ranges should cover all possible buckets in the dimension
    mutually_exclusive: bool  # Whether the buckets are non-overlapping
    ranges: List[TargetRange]

    def validate(self):
        """Validate the consistency of the target set."""
        if not self.ranges:
            return

        # Check that all ranges share the same dimension
        dimensions = {r.dimension for r in self.ranges}
        if len(dimensions) > 1:
            raise ValueError(f"TargetSet must have a single dimension, found: {dimensions}")

        if self.mutually_exclusive and self.exhaustive:
            sum_min = sum(r.min_weight for r in self.ranges)
            sum_max = sum(r.max_weight for r in self.ranges)
            if sum_min > Decimal("1"):
                raise ValueError(f"Sum of min_weights ({sum_min}) exceeds 1.0 in exhaustive/exclusive set.")
            if sum_max < Decimal("1"):
                raise ValueError(f"Sum of max_weights ({sum_max}) is less than 1.0 in exhaustive/exclusive set.")


@dataclass(frozen=True)
class AllocationGapItem:
    """Analysis result for a single target range."""
    bucket: str
    current_weight: Decimal
    min: Decimal
    max: Decimal
    status: Literal["below", "within", "above", "unknown"]
    gap_to_min: Decimal
    gap_to_max: Decimal
    amount_range: tuple[Decimal, Decimal]
    quality: str
    reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class AllocationGapReport:
    """Complete gap analysis report."""
    scope: str
    dimension: str
    items: List[AllocationGapItem]
    unknown_pct: Decimal
    warnings: List[str] = field(default_factory=list)


def calculate_allocation_gaps(
    target_set: TargetSet,
    current_exposures: Dict[str, Decimal],
    unknown_pct: Decimal = Decimal("0")
) -> AllocationGapReport:
    """
    Compare current exposures against targets and calculate gaps.

    Args:
        target_set: The targets to compare against.
        current_exposures: Map of bucket name to its current weight (0-1).
        unknown_pct: Percentage of total value with unknown classification (0-1).
    """
    if any(v < 0 for v in current_exposures.values()):
        raise ValueError("Current exposures cannot contain negative values.")
    if unknown_pct < 0:
        raise ValueError("Unknown percentage cannot be negative.")
    if target_set.denominator_value < 0:
        raise ValueError("Denominator value cannot be negative.")

    target_set.validate()

    items = []
    dimension = target_set.ranges[0].dimension if target_set.ranges else "unknown"

    for tr in target_set.ranges:
        current_weight = current_exposures.get(tr.bucket, Decimal("0"))

        # min_possible is when all unknown exposure belongs to OTHER buckets
        min_possible = current_weight
        # max_possible is when all unknown exposure belongs to THIS bucket
        max_possible = current_weight + unknown_pct

        status: Literal["below", "within", "above", "unknown"]
        reasons = []

        if max_possible < tr.min_weight:
            status = "below"
            reasons.append(f"Even with unknown exposure, maximum possible ({max_possible:.2%}) is below target min ({tr.min_weight:.2%}).")
        elif min_possible > tr.max_weight:
            status = "above"
            reasons.append(f"Current exposure ({min_possible:.2%}) is already above target max ({tr.max_weight:.2%}).")
        elif min_possible >= tr.min_weight and max_possible <= tr.max_weight:
            status = "within"
            reasons.append(f"Current exposure range [{min_possible:.2%}, {max_possible:.2%}] is fully within target range.")
        else:
            status = "unknown"
            reasons.append(f"Current exposure range [{min_possible:.2%}, {max_possible:.2%}] overlaps target boundary; classification is ambiguous due to unknown data.")

        gap_to_min = max(Decimal("0"), tr.min_weight - max_possible)
        gap_to_max = max(Decimal("0"), min_possible - tr.max_weight)

        amount_min = tr.min_weight * target_set.denominator_value
        amount_max = tr.max_weight * target_set.denominator_value

        quality = "exact" if unknown_pct == 0 else "estimated"

        items.append(
            AllocationGapItem(
                bucket=tr.bucket,
                current_weight=current_weight,
                min=tr.min_weight,
                max=tr.max_weight,
                status=status,
                gap_to_min=gap_to_min,
                gap_to_max=gap_to_max,
                amount_range=(amount_min, amount_max),
                quality=quality,
                reasons=reasons
            )
        )

    # Stable sort by priority (desc) then bucket name
    items.sort(key=lambda x: x.bucket)
    # Since TargetRange has priority but AllocationGapItem doesn't explicitly,
    # let's map it back or include it in AllocationGapItem.
    # Spec says priority is optional in TargetRange.
    # Let's include priority in AllocationGapItem to allow stable sorting as required.

    # Actually, let's re-sort based on the original range priorities if needed.
    priority_map = {tr.bucket: tr.priority for tr in target_set.ranges}
    items.sort(key=lambda x: (-priority_map.get(x.bucket, 0), x.bucket))

    return AllocationGapReport(
        scope=target_set.scope,
        dimension=dimension,
        items=items,
        unknown_pct=unknown_pct
    )
