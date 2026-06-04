"""Exchange calendar registry for cross-market time alignment.

Each asset type maps to an ExchangeCalendar that defines its local
timezone, market close time, and holiday schedule.

For bank wealth-management products (BOSC/BOC/ICBC): net values are
published in Beijing time regardless of the underlying asset's domicile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Callable, Dict, FrozenSet, Optional

import pandas as pd


@dataclass(frozen=True)
class ExchangeCalendar:
    """Defines the trading calendar for a market or asset type.

    Attributes:
        name: Human-readable name (e.g. "NYSE").
        timezone: IANA timezone string (e.g. "America/New_York").
        close_time: Local wall-clock time of the market close.
        holidays: Known non-trading weekdays for this market.
        is_business_day: Optional callable for complex calendars.
            When None, defaults to Mon-Fri minus holidays.
    """

    name: str
    timezone: str
    close_time: time = time(16, 0)
    holidays: FrozenSet[date] = field(default_factory=frozenset)
    is_business_day: Optional[Callable[[date], bool]] = None

    def local_date(self, utc_timestamp: pd.Timestamp) -> date:
        """Convert a UTC timestamp to the exchange's local calendar date.

        Example:
            ts = pd.Timestamp("2024-01-08 21:00:00+00:00")  # US close in UTC
            nyse_cal.local_date(ts)  # → date(2024, 1, 8)  (still Monday in NY)
            sse_cal.local_date(ts)   # → date(2024, 1, 9)  (already Tuesday in Shanghai)
        """
        if utc_timestamp.tz is None:
            # Assume UTC for naive timestamps
            utc_ts = utc_timestamp.tz_localize("UTC")
        else:
            utc_ts = utc_timestamp.tz_convert("UTC")
        local_ts = utc_ts.tz_convert(self.timezone)
        return local_ts.date()

    def is_trading_day(self, d: date) -> bool:
        """Return True if ``d`` is a trading day for this exchange."""
        if self.is_business_day is not None:
            return self.is_business_day(d)
        if d.weekday() >= 5:  # Saturday or Sunday
            return False
        if d in self.holidays:
            return False
        return True

    def previous_trading_day(self, d: date) -> date:
        """Return the most recent trading day <= d."""
        cursor = d
        while not self.is_trading_day(cursor):
            cursor = cursor - timedelta(days=1)
        return cursor

    def next_trading_day(self, d: date) -> date:
        """Return the earliest trading day >= d."""
        cursor = d
        while not self.is_trading_day(cursor):
            cursor = cursor + timedelta(days=1)
        return cursor

    def has_closed(self, utc_moment: Optional[pd.Timestamp] = None) -> bool:
        """Check if the market has closed for the current trading day.

        Args:
            utc_moment: The UTC moment to check. If None, uses now.
        """
        if utc_moment is None:
            utc_moment = pd.Timestamp.now(tz="UTC")
        elif utc_moment.tz is None:
            utc_moment = utc_moment.tz_localize("UTC")

        local_ts = utc_moment.tz_convert(self.timezone)
        local_close = datetime.combine(local_ts.date(), self.close_time)
        local_close = pd.Timestamp(local_close).tz_localize(self.timezone)

        return local_ts >= local_close


# ── Pre-built calendars ────────────────────────────────────────────────

# US market holidays 2024-2026 (common NYSE closures)
_US_HOLIDAYS = frozenset({
    date(2024, 1, 1), date(2024, 1, 15), date(2024, 2, 19),
    date(2024, 3, 29), date(2024, 5, 27), date(2024, 6, 19),
    date(2024, 7, 4), date(2024, 9, 2), date(2024, 11, 28),
    date(2024, 12, 25),
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17),
    date(2025, 4, 18), date(2025, 5, 26), date(2025, 6, 19),
    date(2025, 7, 4), date(2025, 9, 1), date(2025, 11, 27),
    date(2025, 12, 25),
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16),
    date(2026, 4, 3), date(2026, 5, 25), date(2026, 6, 19),
    date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26),
    date(2026, 12, 25),
})

# China market holidays 2024-2026 (SSE/SZSE common closures)
_CN_HOLIDAYS = frozenset({
    date(2024, 1, 1), date(2024, 2, 9), date(2024, 2, 12),
    date(2024, 2, 13), date(2024, 2, 14), date(2024, 2, 15),
    date(2024, 2, 16), date(2024, 4, 4), date(2024, 4, 5),
    date(2024, 5, 1), date(2024, 5, 2), date(2024, 5, 3),
    date(2024, 6, 10), date(2024, 9, 16), date(2024, 9, 17),
    date(2024, 10, 1), date(2024, 10, 2), date(2024, 10, 3),
    date(2024, 10, 4), date(2024, 10, 7),
    date(2025, 1, 1), date(2025, 1, 28), date(2025, 1, 29),
    date(2025, 1, 30), date(2025, 1, 31), date(2025, 2, 3),
    date(2025, 2, 4), date(2025, 4, 4), date(2025, 4, 5),
    date(2025, 5, 1), date(2025, 5, 2), date(2025, 5, 5),
    date(2025, 6, 2), date(2025, 10, 1), date(2025, 10, 2),
    date(2025, 10, 3), date(2025, 10, 6), date(2025, 10, 7),
    date(2025, 10, 8),
    date(2026, 1, 1), date(2026, 2, 16), date(2026, 2, 17),
    date(2026, 2, 18), date(2026, 2, 19), date(2026, 2, 20),
    date(2026, 2, 23), date(2026, 4, 6), date(2026, 5, 1),
    date(2026, 5, 4), date(2026, 5, 5), date(2026, 6, 22),
    date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5),
    date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8),
})


NYSE = ExchangeCalendar(
    name="NYSE",
    timezone="America/New_York",
    close_time=time(16, 0),
    holidays=_US_HOLIDAYS,
)

SSE = ExchangeCalendar(
    name="SSE",
    timezone="Asia/Shanghai",
    close_time=time(15, 0),
    holidays=_CN_HOLIDAYS,
)

SEHK = ExchangeCalendar(
    name="SEHK",
    timezone="Asia/Hong_Kong",
    close_time=time(16, 0),
    holidays=frozenset(),  # HK holidays not yet populated
)

CRYPTO = ExchangeCalendar(
    name="CRYPTO",
    timezone="UTC",
    close_time=time(23, 59, 59),
    holidays=frozenset(),
    # Crypto trades 24/7, so every day is a trading day
    is_business_day=lambda d: True,
)

FOREX = ExchangeCalendar(
    name="FOREX",
    timezone="UTC",
    close_time=time(22, 0),  # Approximate forex close (5PM EST Friday)
    holidays=frozenset(),
)


# ── Asset-type → Exchange calendar mapping ─────────────────────────────

ASSET_CALENDAR_MAP: Dict[str, ExchangeCalendar] = {
    # US equities, ETFs
    "us_equity": NYSE,
    "us_etf": NYSE,
    # China stocks, funds, bank products
    "cn_stock": SSE,
    "cn_stock_sh": SSE,
    "cn_stock_sz": SSE,
    "cn_fund": SSE,
    "cn_fund_open": SSE,
    "cn_fund_etf": SSE,
    "cn_fund_money": SSE,
    "cn_fund_qdii": SSE,
    "cn_money_market_fund": SSE,
    # Bank wealth management — Beijing time for net value publication
    "bank_wm_bosc": SSE,
    "bank_wm_boc": SSE,
    "bank_wm_icbc": SSE,
    # HK
    "hk_equity": SEHK,
    # Crypto
    "crypto": CRYPTO,
    # Forex
    "currency": FOREX,
    "forex": FOREX,
}

# Assets that always have a "close price" (net value) available
# regardless of market hours, because they compute NAV once per day.
_NAV_ASSET_TYPES: FrozenSet[str] = frozenset({
    "cn_fund", "cn_fund_open", "cn_fund_etf", "cn_fund_money",
    "cn_fund_qdii", "cn_money_market_fund",
    "bank_wm_bosc", "bank_wm_boc", "bank_wm_icbc",
})


def get_calendar(asset_type: str) -> ExchangeCalendar:
    """Resolve the ExchangeCalendar for a given asset type string.

    Falls back to NYSE if the asset type is unknown. This is conservative:
    it avoids silent timezone mismatches for unknown types.
    """
    calendar = ASSET_CALENDAR_MAP.get(asset_type)
    if calendar is None:
        return NYSE
    return calendar


def is_nav_asset(asset_type: str) -> bool:
    """Return True for assets that publish a single daily NAV.

    These assets don't have real-time tick data; their "price" is a once-per-day
    net value publication. For valuation purposes, their NAV is considered
    available as soon as the publication date arrives (no intraday cutoff).
    """
    return asset_type in _NAV_ASSET_TYPES
