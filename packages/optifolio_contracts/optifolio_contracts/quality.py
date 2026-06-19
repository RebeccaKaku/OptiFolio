"""Quality and freshness enums for financial data.

See docs/GLOSSARY.md for the financial semantics of each level.
"""

from __future__ import annotations

from enum import Enum


class ValuationQuality(str, Enum):
    """Subjective quality of a valuation or data point.

    Financial semantics (see GLOSSARY.md#valuation-quality):
        CONFIRMED — explicitly verified by human or authoritative source
        REPORTED  — reported by third party but not yet confirmed
        ESTIMATED — calculated via interpolation, carry-forward, or proxy
        UNKNOWN   — no reliable data available
    """

    CONFIRMED = "confirmed"
    REPORTED = "reported"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class ValuationFreshness(str, Enum):
    """Temporal relevance of a valuation or data point.

    Financial semantics (see GLOSSARY.md#valuation-freshness):
        CURRENT — matches the requested valuation date
        STALE   — older than the requested date or stale threshold
        UNKNOWN — no date information available
    """

    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"
