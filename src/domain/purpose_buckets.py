"""Purpose buckets domain models — categorizing assets by intent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class PurposeBucket:
    """A bucket representing a specific financial purpose (e.g. core, reserve, learning)."""

    bucket_id: str
    name: str
    bucket_type: str  # core | purpose_reserve | learning
    base_currency: str = "CNY"
    benchmark_id: Optional[str] = None
    liquidity_horizon_days: Optional[int] = None
    risk_notes: str = ""
    status: str = "active"  # active | inactive
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(frozen=True)
class PositionBucketAllocation:
    """An allocation of a specific position to a purpose bucket.

    The allocation is tied to a confirmed snapshot batch.
    allocation_ppm is an integer from 0 to 1,000,000.
    """

    allocation_id: str
    batch_id: str
    account_id: str
    product_id: str
    bucket_id: str
    allocation_ppm: int
    notes: str = ""
