"""Observation contract — a single data point in a time series."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class Observation:
    """A single data point observed for a series.

    effective_date — the date to which this value pertains (e.g. the
      trading day for a close price).

    known_at — the earliest wall-clock time at which the system may use
      this value.  Must not be earlier than effective_date in a live
      system, but the dataclass deliberately does NOT enforce this — it
      is a business rule enforced by repository / service layers.
    """

    series_id: str
    effective_date: date  # the date the value refers to
    value: float
    known_at: Optional[datetime] = None  # earliest time the system may use this value
    released_at: Optional[datetime] = None
    observed_at: Optional[datetime] = None
    source: str = "manual"
    revision: int = 0
    quality_flags: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["effective_date"] = self.effective_date.isoformat()
        d["known_at"] = self.known_at.isoformat() if self.known_at else None
        d["released_at"] = self.released_at.isoformat() if self.released_at else None
        d["observed_at"] = self.observed_at.isoformat() if self.observed_at else None
        d["quality_flags"] = list(self.quality_flags)
        return d
