"""Canonical source identifiers for financial data adapters.

These are source-independent labels used in ``source`` fields across findata.
Adapter-specific provider strings should map to one of these constants.
"""

from __future__ import annotations

AKSHARE: str = "akshare"
YFINANCE: str = "yfinance"
EASTMONEY: str = "eastmoney"
FRED: str = "fred"
BOC_WEB: str = "boc_web"
ICBC_WEB: str = "icbc_web"
BOSC_WEB: str = "bosc_web"
MANUAL: str = "manual"
ARCHIVE: str = "archive"

ALL_SOURCES: tuple[str, ...] = (
    AKSHARE,
    YFINANCE,
    EASTMONEY,
    FRED,
    BOC_WEB,
    ICBC_WEB,
    BOSC_WEB,
    MANUAL,
    ARCHIVE,
)
