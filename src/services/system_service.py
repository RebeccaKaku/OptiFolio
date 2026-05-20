"""System-level service methods."""

from typing import Any, Dict

from src.api.enhanced_api_service import EnhancedAPIService

from .response import failure, normalize_response


class SystemService:
    def __init__(self, api_service: EnhancedAPIService):
        self.api_service = api_service

    def get_status(self) -> Dict[str, Any]:
        try:
            return normalize_response(
                self.api_service.get_system_status(),
                default_message="System status loaded",
            )
        except Exception as exc:
            return failure(str(exc), "SYSTEM_STATUS_ERROR")
