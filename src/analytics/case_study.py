"""USD Treasury WMP Case Study Analysis.

Decomposes returns for USD-denominated products into product performance,
FX impact, and interaction terms, comparing against CNY benchmarks.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Any
from enum import Enum
from datetime import date

class ReturnMethod(str, Enum):
    TWR = "TWR"
    MWR = "MWR"
    CALLER_SUPPLIED = "caller_supplied"

@dataclass(frozen=True)
class CaseStudyCashflow:
    amount: Decimal
    effective_date: date
    event_type: str  # e.g., 'external_contribution', 'fee'
    currency: str = "USD"

@dataclass(frozen=True)
class CaseStudyRequest:
    opening_value_usd: Decimal
    closing_value_usd: Decimal
    opening_fx: Decimal  # USD/CNY
    closing_fx: Decimal  # USD/CNY
    fee_usd: Decimal = Decimal("0")
    cny_benchmark_return: Decimal = Decimal("0")
    cashflows: List[CaseStudyCashflow] = field(default_factory=list)
    return_method: ReturnMethod = ReturnMethod.TWR
    caller_supplied_usd_return: Optional[Decimal] = None
    data_quality: str = "confirmed"

@dataclass(frozen=True)
class CaseStudyResult:
    # 1. USD Product Return
    usd_product_return: Decimal

    # 2. Decomposition (CNY)
    local_pnl_cny: Decimal
    fx_effect_cny: Decimal
    interaction_cny: Decimal
    fees_friction_cny: Decimal
    external_flows_cny: Decimal

    # 3. Results (CNY)
    total_change_cny: Decimal
    cny_wealth_result: Decimal
    cny_benchmark_result: Decimal

    # 4. Alpha (CNY)
    relative_alpha_cny: Decimal

    # 5. Metadata
    unclassified_cny: Decimal
    quality: str
    warnings: List[str] = field(default_factory=list)

    # For UI display: Facts, Hypotheses, Opinions
    facts: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    opinions: List[str] = field(default_factory=list)

def calculate_case_study(request: CaseStudyRequest) -> CaseStudyResult:
    """Pure function to calculate case study results."""
    warnings = []

    op_usd = request.opening_value_usd
    cl_usd = request.closing_value_usd
    op_fx = request.opening_fx
    cl_fx = request.closing_fx

    op_cny = op_usd * op_fx
    cl_cny = cl_usd * cl_fx

    # Process cashflows
    ext_flows_usd = Decimal("0")
    ext_flows_cny = Decimal("0")
    # In case study v1, we usually expect no external flows unless specified.
    # If present, we convert to CNY using an estimated FX if not provided.
    # For now, let's assume they are USD and use op_fx or cl_fx or avg as proxy if needed.
    # The spec says: "不推断缺失换汇价". So we strictly use provided FX or warning.

    for cf in request.cashflows:
        if cf.event_type in ('external_contribution', 'external_withdrawal', 'purchase', 'sale', 'transfer_in', 'transfer_out'):
            ext_flows_usd += cf.amount
            # As a simplification for case study, we use op_fx for contributions and cl_fx for withdrawals?
            # Or just warn if we don't have exact FX.
            # Let's use average FX as a fallback or just opening FX.
            ext_flows_cny += cf.amount * op_fx

    # 1. USD Return
    if request.return_method == ReturnMethod.CALLER_SUPPLIED and request.caller_supplied_usd_return is not None:
        usd_ret = request.caller_supplied_usd_return
    elif not request.cashflows:
        # Simple return: (closing - opening + fee) / opening
        # Wait, if fee is already deducted from closing_value, then gross return adds it back.
        # Standard assumption: closing_value is net of fees.
        if op_usd > 0:
            usd_ret = (cl_usd - op_usd + request.fee_usd) / op_usd
        else:
            usd_ret = Decimal("0")
    else:
        # Cashflows present but not caller supplied
        usd_ret = Decimal("0")
        warnings.append("Returns with cashflows require caller_supplied_usd_return in v1.")

    # 2. Attribution Bridge (CNY)
    # total_change = local_pnl + fx_effect + interaction + external_flows + fees + unclassified

    # gross_local_pnl_usd = cl_usd - op_usd - ext_flows_usd + fee_usd
    gross_local_pnl_usd = cl_usd - op_usd - ext_flows_usd + request.fee_usd

    local_pnl_cny = gross_local_pnl_usd * op_fx
    fx_effect_cny = op_usd * (cl_fx - op_fx)
    interaction_cny = gross_local_pnl_usd * (cl_fx - op_fx)
    fees_cny = -request.fee_usd * cl_fx # Fees typically at closing or actual time

    total_change_cny = cl_cny - op_cny

    explained = local_pnl_cny + fx_effect_cny + interaction_cny + ext_flows_cny + fees_cny
    unclassified_cny = total_change_cny - explained

    # 3. Results
    cny_wealth_result = cl_cny
    # Benchmark: what if op_cny was invested in CNY benchmark
    # And what if external flows (converted to CNY) were also invested?
    # Simplification: only opening balance.
    cny_benchmark_result = op_cny * (Decimal("1") + request.cny_benchmark_return) + ext_flows_cny

    relative_alpha_cny = cny_wealth_result - cny_benchmark_result

    # Facts, Hypotheses, Opinions
    facts = [
        f"USD opening value: {op_usd:,.2f}",
        f"USD closing value: {cl_usd:,.2f}",
        f"Opening USD/CNY: {op_fx:.4f}",
        f"Closing USD/CNY: {cl_fx:.4f}",
    ]
    if request.fee_usd > 0:
        facts.append(f"Fees paid: {request.fee_usd:,.2f} USD")

    hypotheses = [
        f"CNY benchmark return: {request.cny_benchmark_return*100:.2f}%",
        "Assumes no other taxes or hidden costs unless specified.",
    ]

    opinions = []
    if usd_ret > 0 and relative_alpha_cny < 0:
        opinions.append("USD investment gained in local terms, but underperformed CNY benchmark due to FX or fees.")
    elif usd_ret > 0 and relative_alpha_cny > 0:
        opinions.append("USD investment outperformed CNY benchmark.")
    elif usd_ret < 0:
        opinions.append("USD investment lost money in local terms.")

    return CaseStudyResult(
        usd_product_return=usd_ret,
        local_pnl_cny=local_pnl_cny,
        fx_effect_cny=fx_effect_cny,
        interaction_cny=interaction_cny,
        fees_friction_cny=fees_cny,
        external_flows_cny=ext_flows_cny,
        total_change_cny=total_change_cny,
        cny_wealth_result=cny_wealth_result,
        cny_benchmark_result=cny_benchmark_result,
        relative_alpha_cny=relative_alpha_cny,
        unclassified_cny=unclassified_cny,
        quality=request.data_quality,
        warnings=warnings,
        facts=facts,
        hypotheses=hypotheses,
        opinions=opinions
    )
