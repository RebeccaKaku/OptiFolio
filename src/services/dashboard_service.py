"""Dashboard service methods composed from existing API adapters."""

from typing import Any, Dict, Optional

from src.api.enhanced_api_service import EnhancedAPIService

from .response import failure, normalize_response, success


class DashboardService:
    def __init__(self, api_service: EnhancedAPIService):
        self.api_service = api_service

    def get_summary(self, base_currency: Optional[str] = None) -> Dict[str, Any]:
        try:
            sections = {
                "system": normalize_response(self.api_service.get_system_status()),
                "portfolio_value": normalize_response(
                    self.api_service.get_portfolio_value(base_currency)
                ),
                "cash": normalize_response(self.api_service.get_cash_balances()),
                "asset_overview": normalize_response(self.api_service.get_asset_overview()),
                "asset_type_distribution": normalize_response(
                    self.api_service.get_asset_type_distribution()
                ),
            }
            errors = {
                key: value.get("error")
                for key, value in sections.items()
                if not value.get("success")
            }
            return success(
                data={
                    "sections": sections,
                    "errors": errors,
                    "is_partial": bool(errors),
                },
                message="Dashboard summary loaded",
            )
        except Exception as exc:
            return failure(str(exc), "DASHBOARD_SUMMARY_ERROR")

    def get_asset_type_distribution(self) -> Dict[str, Any]:
        try:
            return normalize_response(
                self.api_service.get_asset_type_distribution(),
                default_message="Asset type distribution loaded",
            )
        except Exception as exc:
            return failure(str(exc), "ASSET_TYPE_DISTRIBUTION_ERROR")
