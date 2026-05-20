"""
核心业务逻辑模块 - 与UI框架完全解耦
"""

from .asset_manager import AssetManager
from .portfolio_core import PortfolioCore
from .dashboard_engine import DashboardEngine

__all__ = [
    'AssetManager',
    'PortfolioCore', 
    'DashboardEngine'
]