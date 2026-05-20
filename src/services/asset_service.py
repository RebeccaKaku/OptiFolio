"""Asset service methods for UI and HTTP adapters."""

from typing import Any, Dict, Optional

from src.api.enhanced_api_service import EnhancedAPIService

from .response import failure, normalize_response


class AssetService:
    def __init__(self, api_service: EnhancedAPIService):
        self.api_service = api_service

    def get_overview(self) -> Dict[str, Any]:
        try:
            return normalize_response(
                self.api_service.get_asset_overview(),
                default_message="Asset overview loaded",
            )
        except Exception as exc:
            return failure(str(exc), "ASSET_OVERVIEW_ERROR")

    def list_assets(
        self,
        filter_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        try:
            return normalize_response(
                self.api_service.list_assets(filter_type, page, page_size),
                default_message="Assets loaded",
            )
        except Exception as exc:
            return failure(
                str(exc),
                "ASSET_LIST_ERROR",
                {"filter_type": filter_type, "page": page, "page_size": page_size},
            )

    def search_assets(self, query: str, limit: int = 50) -> Dict[str, Any]:
        try:
            return normalize_response(
                self.api_service.search_assets(query, limit),
                default_message="Asset search completed",
            )
        except Exception as exc:
            return failure(str(exc), "ASSET_SEARCH_ERROR", {"query": query, "limit": limit})

    def get_asset_info(self, symbol: str) -> Dict[str, Any]:
        try:
            return normalize_response(
                self.api_service.get_asset_info(symbol),
                default_message="Asset info loaded",
            )
        except Exception as exc:
            return failure(str(exc), "ASSET_INFO_ERROR", {"symbol": symbol})
