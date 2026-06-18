"""Canonical market data foundation backed by Parquet and DuckDB."""

from .repository import MarketDataRepository
from .schemas import (
    CANONICAL_MARKET_COLUMNS,
    CANONICAL_OBSERVATION_COLUMNS,
    normalize_market_frame,
    normalize_observation_frame,
    validate_market_frame,
    validate_observation_frame,
)

__all__ = [
    "CANONICAL_MARKET_COLUMNS",
    "CANONICAL_OBSERVATION_COLUMNS",
    "MarketDataRepository",
    "normalize_market_frame",
    "normalize_observation_frame",
    "validate_market_frame",
    "validate_observation_frame",
]
