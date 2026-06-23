"""findata calendars — lightweight timezone registry for market data.

This is a minimal implementation that maps asset_type strings to IANA
timezone strings. The full holiday/business-day logic lives in
src/core/calendars.py (OptiFolio-specific).

FinData only needs timezone for canonical storage timestamps, so this
thin registry satisfies that need without the src/ dependency.
"""

from __future__ import annotations

from optifolio_contracts.calendars import ExchangeCalendarProtocol


# Default timezone per asset type — used when no richer calendar is available
_ASSET_TYPE_TIMEZONES: dict[str, str] = {
    "us_equity": "America/New_York",
    "us_etf": "America/New_York",
    "hk_equity": "Asia/Hong_Kong",
    "cn_stock": "Asia/Shanghai",
    "cn_stock_sh": "Asia/Shanghai",
    "cn_stock_sz": "Asia/Shanghai",
    "cn_fund": "Asia/Shanghai",
    "cn_fund_open": "Asia/Shanghai",
    "cn_fund_etf": "Asia/Shanghai",
    "cn_fund_money": "Asia/Shanghai",
    "cn_fund_qdii": "Asia/Shanghai",
    "cn_money_market_fund": "Asia/Shanghai",
    "bank_wmp": "Asia/Shanghai",
    "bank_wm_bosc": "Asia/Shanghai",
    "bank_wm_boc": "Asia/Shanghai",
    "bank_wm_icbc": "Asia/Shanghai",
    "forex": "UTC",
    "currency": "UTC",
    "crypto": "UTC",
}

_DEFAULT_TIMEZONE = "America/New_York"


def get_timezone(asset_type: str) -> str:
    """Return IANA timezone string for an asset type.

    This is the minimal contract FinData needs from calendars.
    For full holiday/business-day support, use src.core.calendars.
    """
    return _ASSET_TYPE_TIMEZONES.get(asset_type, _DEFAULT_TIMEZONE)
