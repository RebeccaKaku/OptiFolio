"""
API层 - 为UI层提供统一的接口
"""

from .asset_api import AssetAPI
from .portfolio_api import PortfolioAPI
from .dashboard_api import DashboardAPI

__all__ = [
    'AssetAPI',
    'PortfolioAPI',
    'DashboardAPI'
]
