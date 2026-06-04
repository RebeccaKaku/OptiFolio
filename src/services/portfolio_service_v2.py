"""Portfolio service V2 for advanced risk analytics."""

from typing import Any, Dict, Optional
from dataclasses import asdict

from src.api.enhanced_api_service import EnhancedAPIService
from src.analytics.exposure import ExposureAnalyzer
from .response import success, failure


class PortfolioServiceV2:
    def __init__(self, api_service: EnhancedAPIService):
        self.api_service = api_service
        self.exposure_analyzer = ExposureAnalyzer()

    def get_exposure_report(self, base_currency: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a Level 0 exposure report for the current portfolio.
        """
        try:
            # 1. Get current portfolio value and holdings
            # EnhancedAPIService.get_portfolio_value returns the result of PortfolioAPI.get_portfolio_value
            # which returns a dict containing 'positions' and 'total_value'.
            portfolio_res = self.api_service.get_portfolio_value(base_currency)

            # The API response is normalized in PortfolioService,
            # but here we are using api_service (EnhancedAPIService) directly.
            # EnhancedAPIService.get_portfolio_value returns the raw dict from PortfolioAPI.

            positions = portfolio_res.get('positions', {})
            total_value = portfolio_res.get('total_value', 0.0)

            # 2. Analyze exposure using product labels
            # We pass the asset_manager from api_service as the product_registry
            report = self.exposure_analyzer.analyze(
                positions=positions,
                product_registry=self.api_service.asset_manager,
                total_value=total_value
            )

            return success(
                asdict(report),
                "Exposure report generated successfully"
            )
        except Exception as exc:
            return failure(
                str(exc),
                "EXPOSURE_REPORT_ERROR",
                {"base_currency": base_currency}
            )
