"""FinData Orchestrator — COMMAND department. Decides WHAT to fetch and WHEN.

Exports:
    Orchestrator  — scheduler + dispatcher for all asset types
    UpdateCadence — update frequency rules per asset type
    FetchTask     — a single fetch job
    RateLimiter   — per-provider call-rate throttle
"""

from .cadence import UpdateCadence, CADENCE_TABLE, get_cadence, is_update_due
from .rate_limiter import RateLimiter, PROVIDER_LIMITS
from .fallback import FALLBACK_CHAINS, get_fallback_chain
from .orchestrator import Orchestrator, FetchTask

__all__ = [
    "CADENCE_TABLE",
    "FALLBACK_CHAINS",
    "FetchTask",
    "Orchestrator",
    "PROVIDER_LIMITS",
    "RateLimiter",
    "UpdateCadence",
    "get_cadence",
    "get_fallback_chain",
    "is_update_due",
]
