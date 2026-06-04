"""Lazy application service graph."""

from dataclasses import dataclass
from functools import lru_cache

from src.api.enhanced_api_service import get_enhanced_api_service

from .asset_service import AssetService
from .dashboard_service import DashboardService
from .portfolio_service import PortfolioService
from .portfolio_service_v2 import PortfolioServiceV2
from .research_service import ResearchService
from .system_service import SystemService


@dataclass(frozen=True)
class ApplicationServices:
    system: SystemService
    dashboard: DashboardService
    portfolio: PortfolioService
    portfolio_v2: PortfolioServiceV2
    assets: AssetService
    research: ResearchService


@lru_cache(maxsize=1)
def get_application_services() -> ApplicationServices:
    api_service = get_enhanced_api_service()
    return ApplicationServices(
        system=SystemService(api_service),
        dashboard=DashboardService(api_service),
        portfolio=PortfolioService(api_service),
        portfolio_v2=PortfolioServiceV2(api_service),
        assets=AssetService(api_service),
        research=ResearchService(),
    )
