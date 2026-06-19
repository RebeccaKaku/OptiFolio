"""API for the "My Money" summary home page.

Provides aggregated views of assets and performance for the personal book.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from src.api.portfolio_book_api import _json_response


router = APIRouter(prefix="/api/book", tags=["portfolio book"])


def _get_service():
    """Lazy-import the my money service from the application service graph."""
    from src.services.application import get_application_services
    return get_application_services().my_money


@router.get("/summary")
def get_summary(
    as_of: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    reporting_currency: str = Query("CNY", min_length=3, max_length=3),
    svc=Depends(_get_service)
):
    """Get the "My Money" aggregated summary."""
    target_date = date.fromisoformat(as_of) if as_of else None
    result = svc.get_summary(as_of=target_date, reporting_currency=reporting_currency.upper())
    return _json_response(result)
