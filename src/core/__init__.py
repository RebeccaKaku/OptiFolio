"""
核心业务逻辑模块 — 与UI框架完全解耦
"""

from .asset_manager import AssetManager
from .corporate_actions import CorporateActionProcessor
from .dashboard_engine import DashboardEngine
from .fees import FeeProcessor
from .portfolio_core import PortfolioCore
from .portfolio_history import PortfolioHistoryTracker
from .valuation import (
    FxRateError,
    FxRateProvider,
    NoPriceDataError,
    ValuationEngine,
)

__all__ = [
    "AssetManager",
    "CorporateActionProcessor",
    "DashboardEngine",
    "FeeProcessor",
    "FxRateError",
    "FxRateProvider",
    "NoPriceDataError",
    "PortfolioCore",
    "PortfolioHistoryTracker",
    "ValuationEngine",
]
