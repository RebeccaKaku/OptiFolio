"""Series definition contract — time-series data streams (macro, index, signals)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class SeriesDefinition:
    """A time-series data stream definition.

    series_type is one of:
      index_level, macro_indicator, yield_curve, factor_signal,
      benchmark_return, risk_free_rate, fee_or_friction

    revision_policy:
      append_only — each new value is appended, earlier values are never replaced
      overwrite   — latest value replaces any prior value for the same date
    """

    series_id: str
    series_type: str  # index_level, macro_indicator, yield_curve, factor_signal, benchmark_return, risk_free_rate, fee_or_friction
    subject_id: Optional[str] = None
    frequency: str = "D"
    unit: str = ""
    currency: Optional[str] = None
    calendar_id: Optional[str] = None
    source_priority: Tuple[str, ...] = ()
    revision_policy: str = "append_only"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source_priority"] = list(self.source_priority)
        return d
