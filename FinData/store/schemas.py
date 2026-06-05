"""Canonical market data schemas and normalization helpers.

Re-exports from the authoritative source in src/data_foundation/schemas.py.
"""

from __future__ import annotations

from src.data_foundation.schemas import (  # noqa: F401
    _COLUMN_ALIASES,
    _canonical_column_name,
    CANONICAL_MARKET_COLUMNS,
    normalize_market_frame,
    STORE_VERSION,
    validate_market_frame,
)

CANONICAL_COLUMNS = CANONICAL_MARKET_COLUMNS  # alias for backward compat
