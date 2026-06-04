"""Canonical market data schemas and normalization helpers.

Re-exports from the authoritative source in src/data_foundation/schemas.py.
"""

from __future__ import annotations

from src.data_foundation.schemas import (  # noqa: F401
    CANONICAL_MARKET_COLUMNS,
    normalize_market_frame,
    validate_market_frame,
)

CANONICAL_COLUMNS = CANONICAL_MARKET_COLUMNS  # alias for backward compat

store_version: str = "1.0"
