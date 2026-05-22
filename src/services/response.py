"""Small helpers for stable service response dictionaries."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def success(data: Any = None, message: str = "OK") -> Dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "message": message,
        "error": None,
        "timestamp": utc_timestamp(),
    }


def failure(
    error: str,
    error_code: str = "SERVICE_ERROR",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "success": False,
        "data": None,
        "message": None,
        "error": error,
        "error_code": error_code,
        "timestamp": utc_timestamp(),
    }
    if details:
        response["details"] = details
    return response


def normalize_response(result: Dict[str, Any], default_message: str = "OK") -> Dict[str, Any]:
    """Add common keys without changing the existing payload shape."""
    if not isinstance(result, dict):
        return success(result, default_message)

    normalized = result.copy()
    normalized.setdefault("success", True)
    normalized.setdefault("data", None)
    normalized.setdefault("message", default_message if normalized["success"] else None)
    normalized.setdefault("error", None)
    normalized.setdefault("timestamp", utc_timestamp())
    return normalized
