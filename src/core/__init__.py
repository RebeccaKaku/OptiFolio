"""
核心业务逻辑模块 — 与UI框架完全解耦
"""

"""
核心业务逻辑模块 — 与UI框架完全解耦

Import note: modules that depend on src.data_foundation (calendars,
valuation, etc.) are NOT re-exported here to avoid circular imports.
Import them directly from their submodules:

    from src.core.calendars import ExchangeCalendar, get_calendar
    from src.core.valuation import ValuationEngine
"""

from .asset_manager import AssetManager
from .corporate_actions import CorporateActionProcessor
from .dashboard_engine import DashboardEngine
from .fees import FeeProcessor
from .portfolio_core import PortfolioCore
from .portfolio_history import PortfolioHistoryTracker

__all__ = [
    "AssetManager",
    "CorporateActionProcessor",
    "DashboardEngine",
    "FeeProcessor",
    "PortfolioCore",
    "PortfolioHistoryTracker",
]
