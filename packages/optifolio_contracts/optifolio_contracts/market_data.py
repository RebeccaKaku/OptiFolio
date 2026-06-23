"""Canonical market data column definitions and schemas.

These column names define the contract between data producers (adapters)
and data consumers (store, valuation, analytics).  All FinData adapters
MUST produce DataFrames with these columns before storage.
"""

from __future__ import annotations

# Canonical OHLCV market data columns
CANONICAL_MARKET_COLUMNS: tuple[str, ...] = (
    "asset_id",
    "date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "currency",
    "source",
    "timezone",
)

# Canonical observation (non-price) columns
CANONICAL_OBSERVATION_COLUMNS: tuple[str, ...] = (
    "series_id",
    "effective_date",
    "value",
    "known_at",
    "released_at",
    "observed_at",
    "source",
    "revision",
    "quality_flags",
    "unit",
    "currency",
)

# Store version — increment when schema changes
STORE_VERSION: str = "2.0"

# Dataset ID naming convention constants
DATASET_DOMAIN_SEPARATOR: str = "."
DATASET_TABLE_SEPARATOR: str = "_"
