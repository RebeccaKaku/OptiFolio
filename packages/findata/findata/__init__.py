"""findata — local-first financial data layer.

This package MUST NOT import from src/.
It MAY import from optifolio_contracts.

Public API:
    from findata import FinDataConfig
    from findata.store import MarketDataRepository
"""

from findata.config import FinDataConfig, get_default_config

__all__ = ["FinDataConfig", "get_default_config"]
