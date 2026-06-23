"""OptiFolio Contracts — pure types, protocols, and enums.

This package MUST NOT import from src/, findata/, or any package
with external dependencies (requests, akshare, fastapi, sqlite3, duckdb,
yfinance, pandas, numpy, etc.).

Allowed dependencies: stdlib only (dataclasses, datetime, enum, re, typing).
"""

from optifolio_contracts.calendars import ExchangeCalendarProtocol
from optifolio_contracts.datasets import (
    EQUITIES_OHLCV_DAILY,
    FX_SPOT_DAILY,
    FUNDS_NAV_DAILY,
    MACRO_CPI_MONTHLY,
    RATES_POLICY_EVENT,
    RATES_SHIBOR_DAILY,
    RATES_SOFR_DAILY,
    WMP_NAV_IRREGULAR,
)
from optifolio_contracts.fx import (
    DEFAULT_FALLBACK_RATES,
    FxRateError,
    FxRateProviderProtocol,
    HardcodedFxRateProvider,
)
from optifolio_contracts.identifiers import (
    AmbiguousInstrumentIdError,
    InstrumentIdParts,
    InvalidInstrumentIdError,
    normalize_instrument_id,
    parse_instrument_id,
    validate_instrument_id,
)
from optifolio_contracts.market_data import (
    CANONICAL_MARKET_COLUMNS,
    CANONICAL_OBSERVATION_COLUMNS,
    STORE_VERSION,
)
from optifolio_contracts.quality import ValuationFreshness, ValuationQuality
from optifolio_contracts.sources import (
    AKSHARE,
    ALL_SOURCES,
    ARCHIVE,
    BOC_WEB,
    BOSC_WEB,
    EASTMONEY,
    FRED,
    ICBC_WEB,
    MANUAL,
    YFINANCE,
)
from optifolio_contracts.symbols import (
    CN_EXCHANGE_PREFIXES,
    _infer_exchange_prefix,
    normalize_cn_symbol,
)

__all__ = [
    # identifiers
    "AmbiguousInstrumentIdError",
    "InstrumentIdParts",
    "InvalidInstrumentIdError",
    "normalize_instrument_id",
    "parse_instrument_id",
    "validate_instrument_id",
    # sources
    "AKSHARE",
    "ALL_SOURCES",
    "ARCHIVE",
    "BOC_WEB",
    "BOSC_WEB",
    "EASTMONEY",
    "FRED",
    "ICBC_WEB",
    "MANUAL",
    "YFINANCE",
    # datasets
    "EQUITIES_OHLCV_DAILY",
    "FX_SPOT_DAILY",
    "FUNDS_NAV_DAILY",
    "MACRO_CPI_MONTHLY",
    "RATES_POLICY_EVENT",
    "RATES_SHIBOR_DAILY",
    "RATES_SOFR_DAILY",
    "WMP_NAV_IRREGULAR",
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
    "DEFAULT_FALLBACK_RATES",
    "FxRateError",
    "FxRateProviderProtocol",
    "HardcodedFxRateProvider",
    # market_data
    "CANONICAL_MARKET_COLUMNS",
    "CANONICAL_OBSERVATION_COLUMNS",
    "STORE_VERSION",
]
