"""Portfolio service methods for UI and HTTP adapters."""

from typing import Any, Dict, Optional

from src.api.enhanced_api_service import EnhancedAPIService

from .response import failure, normalize_response


class PortfolioService:
    def __init__(self, api_service: EnhancedAPIService):
        self.api_service = api_service

    def get_value(self, base_currency: Optional[str] = None) -> Dict[str, Any]:
        try:
            return normalize_response(
                self.api_service.get_portfolio_value(base_currency),
                default_message="Portfolio value loaded",
            )
        except Exception as exc:
            return failure(str(exc), "PORTFOLIO_VALUE_ERROR", {"base_currency": base_currency})

    def get_cash(self) -> Dict[str, Any]:
        try:
            return normalize_response(
                self.api_service.get_cash_balances(),
                default_message="Cash balances loaded",
            )
        except Exception as exc:
            return failure(str(exc), "CASH_BALANCE_ERROR")

    def get_holdings(self) -> Dict[str, Any]:
        try:
            return normalize_response(
                self.api_service.get_current_holdings(),
                default_message="Holdings loaded",
            )
        except Exception as exc:
            return failure(str(exc), "HOLDINGS_ERROR")
