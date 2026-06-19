"""OptiFolio Contracts — pure types, protocols, and enums.

This package MUST NOT import from src/, findata/, or any package
with external dependencies (requests, akshare, fastapi, sqlite3, duckdb,
yfinance, pandas, numpy, etc.).

Allowed dependencies: stdlib only (dataclasses, datetime, enum, re, typing).
"""

from optifolio_contracts.calendars import ExchangeCalendarProtocol
from optifolio_contracts.fx import FxRateProviderProtocol
from optifolio_contracts.market_data import (
    CANONICAL_MARKET_COLUMNS,
    CANONICAL_OBSERVATION_COLUMNS,
    STORE_VERSION,
)
from optifolio_contracts.quality import ValuationFreshness, ValuationQuality
from optifolio_contracts.symbols import (
    CN_EXCHANGE_PREFIXES,
    _infer_exchange_prefix,
    normalize_cn_symbol,
)

__all__ = [
    # symbols
    "CN_EXCHANGE_PREFIXES",
    "_infer_exchange_prefix",
    "normalize_cn_symbol",
    # quality
    "ValuationFreshness",
    "ValuationQuality",
    # calendars
    "ExchangeCalendarProtocol",
    # fx
    "FxRateProviderProtocol",
    # market_data
    "CANONICAL_MARKET_COLUMNS",
    "CANONICAL_OBSERVATION_COLUMNS",
    "STORE_VERSION",
]
