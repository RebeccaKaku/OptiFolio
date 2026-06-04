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

# Private helpers kept locally for quality.py compatibility
_COLUMN_ALIASES = {
    "asset": "asset_id",
    "symbol": "asset_id",
    "ticker": "asset_id",
    "datetime": "date",
    "time": "date",
    "timestamp": "date",
    "adj close": "adj_close",
    "adjusted_close": "adj_close",
    "adjusted close": "adj_close",
}


def _canonical_column_name(name: object) -> str:
    normalized = str(name).strip().replace("_", " ").lower()
    return _COLUMN_ALIASES.get(normalized, normalized.replace(" ", "_"))
