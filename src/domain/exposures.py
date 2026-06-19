"""Product exposure domain models.

This module defines the models for tracking what products are actually exposed to
(underlying assets, currencies, regions, etc.), separate from the product wrapper.
Weights are handled as Decimal (0 to 1) in the domain layer and PPM in the database.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Dict, Set


class ExposureDimension:
    ASSET_CLASS = "asset_class"
    CURRENCY = "currency"
    REGION = "region"
    DURATION = "duration"
    CREDIT_QUALITY = "credit_quality"
    COMMODITY = "commodity"

    ALL: Set[str] = {
        ASSET_CLASS,
        CURRENCY,
        REGION,
        DURATION,
        CREDIT_QUALITY,
        COMMODITY,
    }


class ExposureMethod:
    ACTUAL = "actual"
    REPORTED = "reported"
    ESTIMATED = "estimated"
    PROXY = "proxy"
    UNKNOWN = "unknown"

    ALL: Set[str] = {ACTUAL, REPORTED, ESTIMATED, PROXY, UNKNOWN}


class ExposureQuality:
    REPORTED = "reported"
    ESTIMATED = "estimated"
    STALE = "stale"
    UNKNOWN = "unknown"

    ALL: Set[str] = {REPORTED, ESTIMATED, STALE, UNKNOWN}


class ExposureStatus:
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"

    ALL: Set[str] = {DRAFT, CONFIRMED, SUPERSEDED}


@dataclass(frozen=True)
class ExposureEntry:
    """A single exposure data point (e.g., 40% in 'equity' via 'reported' method)."""

    dimension: str
    bucket: str
    weight: Decimal  # Range: [0, 1]
    method: str = ExposureMethod.UNKNOWN
    source_ref: Optional[str] = None
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        if self.weight < Decimal("0") or self.weight > Decimal("1"):
            raise ValueError(f"Weight must be between 0 and 1, got {self.weight}")
        if self.method not in ExposureMethod.ALL:
            raise ValueError(f"Invalid exposure method: {self.method}")

    def to_ppm(self) -> int:
        """Convert weight to parts-per-million integer."""
        return int((self.weight * Decimal("1000000")).quantize(Decimal("1")))

    @classmethod
    def from_ppm(
        cls,
        ppm: int,
        dimension: str,
        bucket: str,
        method: str = ExposureMethod.UNKNOWN,
        source_ref: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ExposureEntry:
        """Create an entry from a parts-per-million integer."""
        weight = Decimal(ppm) / Decimal("1000000")
        return cls(
            dimension=dimension,
            bucket=bucket,
            weight=weight,
            method=method,
            source_ref=source_ref,
            notes=notes,
        )


@dataclass(frozen=True)
class ExposureBatch:
    """A batch of exposure entries for a product as of a specific date."""

    batch_id: str
    product_id: str
    as_of: str
    known_at: str
    entries: List[ExposureEntry] = field(default_factory=list)
    source: str = "manual"
    quality: str = ExposureQuality.UNKNOWN
    status: str = ExposureStatus.DRAFT
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        if self.quality not in ExposureQuality.ALL:
            raise ValueError(f"Invalid exposure quality: {self.quality}")
        if self.status not in ExposureStatus.ALL:
            raise ValueError(f"Invalid exposure status: {self.status}")

        # Validate weight sums by dimension
        sums: Dict[str, Decimal] = {}
        for entry in self.entries:
            sums[entry.dimension] = (
                sums.get(entry.dimension, Decimal("0")) + entry.weight
            )

        for dim, total in sums.items():
            if total > Decimal("1"):
                raise ValueError(
                    f"Total weight for dimension {dim} exceeds 1.0: {total}"
                )

    def get_residual(self, dimension: str) -> Decimal:
        """Calculate the unknown residual for a given dimension."""
        total = sum(
            (e.weight for e in self.entries if e.dimension == dimension), Decimal("0")
        )
        return Decimal("1") - total
