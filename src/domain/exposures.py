"""Domain models for product exposures."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class ExposureBatch:
    """A batch of exposure data for a specific product at a point in time.

    status: draft, confirmed, superseded
    quality: reported, estimated, stale, unknown
    """
    batch_id: str
    product_id: str
    as_of: str
    known_at: str
    source: str = "manual"
    quality: str = "reported"
    status: str = "draft"
    notes: Optional[str] = None


@dataclass(frozen=True)
class ProductExposure:
    """A single exposure component (dimension/bucket) for a product.

    dimension: asset_class, currency, region, duration, credit_quality, commodity
    method: actual, reported, estimated, proxy, unknown
    weight_ppm: weight in parts per million (0 to 1,000,000)
    """
    batch_id: str
    dimension: str
    bucket: str
    weight_ppm: int
    method: str = "actual"
    source_ref: Optional[str] = None
    notes: Optional[str] = None

    @property
    def weight(self) -> Decimal:
        """The weight as a Decimal between 0 and 1."""
        return Decimal(self.weight_ppm) / Decimal(1_000_000)
