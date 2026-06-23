"""Trading calendar protocol for cross-market time alignment.

FinData uses calendars to infer timezone and business-day rules for each
asset type. The protocol is intentionally minimal — just what FinData needs
to timestamp data correctly.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol


class ExchangeCalendarProtocol(Protocol):
    """Minimal calendar interface required by FinData.

    FinData uses the timezone to set canonical timezone on stored data.
    It uses is_business_day to determine whether a given date is a
    trading day for freshness checks.

    Conforming implementations include src.core.calendars.ExchangeCalendar.
    """

    timezone: str
    """IANA timezone string (e.g. 'Asia/Shanghai', 'America/New_York')."""

    def is_business_day(self, d: date) -> bool:
        """Return True if *d* is a business/trading day for this market."""
        ...
