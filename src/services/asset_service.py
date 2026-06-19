"""Asset service methods for UI and HTTP adapters."""

from typing import Any, Dict, Optional

from src.core.enhanced_asset_manager import EnhancedAssetManager
from .response import failure, normalize_response


class AssetService:
    def __init__(self, asset_manager: EnhancedAssetManager):
        self.asset_manager = asset_manager

    def get_overview(self) -> Dict[str, Any]:
        try:
            return normalize_response(
                {"success": True, "data": self.asset_manager.get_asset_overview_data()},
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
            all_assets = self.asset_manager.list_assets(filter_type)

            # Pagination logic
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_assets = all_assets[start_idx:end_idx]

            data = {
                "assets": paginated_assets,
                "total": len(all_assets),
                "page": page,
                "page_size": page_size,
                "total_pages": (len(all_assets) + page_size - 1) // page_size
            }

            return normalize_response(
                {"success": True, "data": data},
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
            results = self.asset_manager.search_assets(query, limit)
            data = {
                "assets": results,
                "query": query,
                "count": len(results)
            }
            return normalize_response(
                {"success": True, "data": data},
                default_message="Asset search completed",
            )
        except Exception as exc:
            return failure(str(exc), "ASSET_SEARCH_ERROR", {"query": query, "limit": limit})

    def get_asset_info(self, symbol: str) -> Dict[str, Any]:
        try:
            asset_info = self.asset_manager.get_asset_info(symbol)
            return normalize_response(
                {"success": True, "data": asset_info},
                default_message="Asset info loaded",
            )
        except Exception as exc:
            return failure(str(exc), "ASSET_INFO_ERROR", {"symbol": symbol})
