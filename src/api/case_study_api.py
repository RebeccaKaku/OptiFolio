"""API router for USD Case Study Analysis."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field

from src.services import get_application_services, ApplicationServices

router = APIRouter(prefix="/api/case-study", tags=["case-study"])

class CaseStudyCashflowPayload(BaseModel):
    amount: float
    effective_date: str # YYYY-MM-DD
    event_type: str
    currency: str = "USD"

class CaseStudyAnalyzePayload(BaseModel):
    opening_value_usd: float
    closing_value_usd: float
    opening_fx: float
    closing_fx: float
    fee_usd: float = 0.0
    cny_benchmark_return: float = 0.0
    cashflows: List[CaseStudyCashflowPayload] = Field(default_factory=list)
    return_method: str = "TWR"
    caller_supplied_usd_return: Optional[float] = None
    data_quality: str = "confirmed"
    include_scenarios: bool = True

@router.post("/analyze")
def analyze_case_study(
    payload: CaseStudyAnalyzePayload,
    services: ApplicationServices = Depends(get_application_services)
):
    """Decomposes USD product returns and compares against CNY benchmarks."""
    return services.case_study.analyze(payload.dict())
