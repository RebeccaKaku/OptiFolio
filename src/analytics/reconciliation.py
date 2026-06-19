from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Any, Set
from enum import Enum

class CoverageLevel(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    EMPTY = "empty"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class PositionInput:
    account_id: str
    product_id: str
    currency: str
    quantity: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    cost_basis: Optional[Decimal] = None
    source: Optional[str] = None
    quality: Optional[str] = None

@dataclass(frozen=True)
class SnapshotInput:
    batch_id: str
    as_of: date
    status: str
    account_coverage: Dict[str, CoverageLevel]
    positions: List[PositionInput]
    cashflow_coverage: CoverageLevel = CoverageLevel.UNKNOWN

@dataclass(frozen=True)
class CashflowInput:
    event_id: str
    event_type: str
    account_id: str
    amount: Decimal
    currency: str
    effective_date: date
    product_id: Optional[str] = None
    counter_amount: Optional[Decimal] = None
    counter_currency: Optional[str] = None
    pair_event_id: Optional[str] = None

@dataclass(frozen=True)
class ReconciliationRequest:
    previous: SnapshotInput
    current: SnapshotInput
    cashflows: List[CashflowInput] = field(default_factory=list)

@dataclass(frozen=True)
class ReconciliationResult:
    opening_value: Decimal
    closing_value: Decimal
    external_net_flow: Decimal
    investment_income: Decimal
    fees_taxes: Decimal
    market_change: Decimal
    fx_effect: Decimal
    internal_flow_net: Decimal
    explained_change: Decimal
    unclassified_change: Decimal
    coverage_status: str
    is_return_eligible: bool
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opening_value": str(self.opening_value),
            "closing_value": str(self.closing_value),
            "external_net_flow": str(self.external_net_flow),
            "investment_income": str(self.investment_income),
            "fees_taxes": str(self.fees_taxes),
            "market_change": str(self.market_change),
            "fx_effect": str(self.fx_effect),
            "internal_flow_net": str(self.internal_flow_net),
            "explained_change": str(self.explained_change),
            "unclassified_change": str(self.unclassified_change),
            "coverage_status": self.coverage_status,
            "is_return_eligible": self.is_return_eligible,
            "warnings": self.warnings,
        }

def reconcile_snapshots(request: ReconciliationRequest) -> ReconciliationResult:
    """Compare two snapshot batches and explain what changed.

    Identity:
    closing - opening = external_net_flow + investment_income + fees_taxes + market_change + fx_effect + unclassified_change

    where explained_change = external_net_flow + investment_income + fees_taxes + market_change + fx_effect
    """
    previous = request.previous
    current = request.current
    cashflows = request.cashflows
    warnings = []

    if current.as_of <= previous.as_of:
        raise ValueError(f"Current snapshot date {current.as_of} must be after previous {previous.as_of}")

    # Determine base currency
    currencies = {p.currency for p in previous.positions if p.market_value is not None} | \
                 {p.currency for p in current.positions if p.market_value is not None}

    if not currencies:
        base_currency = "CNY"
    elif len(currencies) > 1:
        # Per spec: "币种混合未折算均返回明确错误"
        raise ValueError(f"Mixed currencies found: {currencies}. Reconciliation requires a single base currency.")
    else:
        base_currency = currencies.pop()

    opening_value = sum((p.market_value for p in previous.positions if p.market_value is not None), Decimal("0"))
    closing_value = sum((p.market_value for p in current.positions if p.market_value is not None), Decimal("0"))

    if any(p.market_value is None for p in previous.positions):
        warnings.append("Some positions in opening snapshot have missing market value")
    if any(p.market_value is None for p in current.positions):
        warnings.append("Some positions in closing snapshot have missing market value")

    external_net_flow = Decimal("0")
    investment_income = Decimal("0")
    fees_taxes = Decimal("0")
    internal_flow_net = Decimal("0")
    fx_effect = Decimal("0")
    unclassified_flows = Decimal("0")

    for cf in cashflows:
        # Period is (previous.as_of, current.as_of]
        if not (previous.as_of < cf.effective_date <= current.as_of):
            continue

        amt = Decimal("0")
        if cf.currency == base_currency:
            amt = cf.amount
        elif cf.event_type == 'fx_conversion' and cf.counter_currency == base_currency:
            amt = cf.counter_amount if cf.counter_amount is not None else Decimal("0")
        else:
            # Skip cashflows not in base currency if not a valid FX conversion side
            warnings.append(f"Skipping cashflow {cf.event_id} with non-matching currency {cf.currency}")
            continue

        if cf.event_type in ('external_contribution', 'external_withdrawal'):
            external_net_flow += amt
        elif cf.event_type in ('interest', 'dividend', 'coupon'):
            investment_income += amt
        elif cf.event_type == 'maturity':
            internal_flow_net += amt
        elif cf.event_type in ('fee', 'tax'):
            fees_taxes += amt
        elif cf.event_type in ('purchase', 'sale', 'transfer_in', 'transfer_out'):
            internal_flow_net += amt
        elif cf.event_type == 'fx_conversion':
            # We treat the base currency side of FX conversion as internal flow
            # In a balanced portfolio, this would be offset by position changes.
            internal_flow_net += amt
            # For now, we don't have enough data to calculate a separate fx_effect from conversions
            # (which would require knowing the value of the other side at the time).
        elif cf.event_type == 'other':
            unclassified_flows += amt
        else:
            unclassified_flows += amt
            warnings.append(f"Unclassified cashflow type: {cf.event_type}")

    # Coverage Check
    all_accounts = set(previous.account_coverage.keys()) | set(current.account_coverage.keys())
    is_coverage_complete = True
    for acc_id in all_accounts:
        p_cov = previous.account_coverage.get(acc_id, CoverageLevel.EMPTY)
        c_cov = current.account_coverage.get(acc_id, CoverageLevel.EMPTY)
        if p_cov not in (CoverageLevel.COMPLETE, CoverageLevel.EMPTY) or \
           c_cov not in (CoverageLevel.COMPLETE, CoverageLevel.EMPTY):
            is_coverage_complete = False
            break

    if previous.cashflow_coverage != CoverageLevel.COMPLETE:
        is_coverage_complete = False

    # Final Decision for Return Eligibility
    is_return_eligible = is_coverage_complete and opening_value > 0
    coverage_status = "complete" if is_coverage_complete else "partial"

    delta = closing_value - opening_value

    if is_coverage_complete:
        # Residual is market change
        # delta = external + income + fees + internal + fx_effect + unclassified_flows + market_change
        market_change = delta - (external_net_flow + investment_income + fees_taxes + internal_flow_net + fx_effect + unclassified_flows)
        # unclassified_change captures imbalanced internal moves and 'other' events
        unclassified_change = internal_flow_net + unclassified_flows
    else:
        # Market change is unknown, goes to unclassified
        market_change = Decimal("0")
        unclassified_change = delta - (external_net_flow + investment_income + fees_taxes)

    explained_change = external_net_flow + investment_income + fees_taxes + market_change + fx_effect

    return ReconciliationResult(
        opening_value=opening_value,
        closing_value=closing_value,
        external_net_flow=external_net_flow,
        investment_income=investment_income,
        fees_taxes=fees_taxes,
        market_change=market_change,
        fx_effect=fx_effect,
        internal_flow_net=internal_flow_net,
        explained_change=explained_change,
        unclassified_change=unclassified_change,
        coverage_status=coverage_status,
        is_return_eligible=is_return_eligible,
        warnings=warnings
    )
