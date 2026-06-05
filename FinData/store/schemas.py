"""Canonical market data schemas and normalization helpers.

Re-exports from the authoritative source in src/data_foundation/schemas.py.
All FinData modules should import from here, not from src.data_foundation directly.
"""

from __future__ import annotations

from src.data_foundation.schemas import (  # noqa: F401
    CANONICAL_MARKET_COLUMNS,
    STORE_VERSION,
    _COLUMN_ALIASES,
    _canonical_column_name,
    normalize_market_frame,
    validate_market_frame,
)

CANONICAL_COLUMNS = CANONICAL_MARKET_COLUMNS  # alias for backward compat
store_version = STORE_VERSION                 # alias for backward compat
