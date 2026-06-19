"""Standard Product Comparator — pure function comparison engine.

Design principle: This engine compares financial products (money funds, bonds,
deposits) across standardized dimensions after normalizing yields and fees
to a specific use case (holding period, amount, currency).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


class YieldType(Enum):
    ANNUALIZED_7D = "annualized_7d"
    YTM = "ytm"
    HISTORICAL_1Y = "historical_1y"
    FIXED = "fixed"


@dataclass(frozen=True)
class ComparisonUseCase:
    """The context for comparison."""

    target_currency: str
    amount: Decimal
    holding_period_days: int
    liquidity_requirement: str = "any"  # "T+0", "T+1", "any"
    risk_tolerance: str = "medium"      # "low", "medium", "high"
    allow_fx: bool = False
    fx_shocks: Dict[str, float] = field(
        default_factory=lambda: {"base": 0.0, "bull": 0.05, "bear": -0.05}
    )


@dataclass(frozen=True)
class ProductComparisonInput:
    """Raw data for a single product to be compared."""

    product_id: str
    name: str
    currency: str
    yield_value: float
    yield_type: YieldType
    mgmt_fee_annual: float = 0.0
    redemption_fee: float = 0.0
    fx_fee: float = 0.0
    settlement_days: int = 0
    lockup_days: int = 0
    duration: Optional[float] = None
    credit_rating: Optional[str] = None
    min_amount: Decimal = Decimal("0")
    data_quality: str = "confirmed"
    as_of: Optional[str] = None


@dataclass(frozen=True)
class ProductComparisonResult:
    """Standardized comparison result for one product."""

    product_id: str
    name: str
    net_yield_scenarios: Dict[str, float]  # Annualized net return scenarios
    fees_total_pct: float
    liquidity_score: float  # 0-100 (higher is better/faster)
    duration: Optional[float]
    credit_rating: Optional[str]
    fx_exposure: str
    data_quality: str
    coverage: float
    incomparable: bool
    incomparable_reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compare_products(
    products: List[ProductComparisonInput],
    use_case: ComparisonUseCase,
) -> List[ProductComparisonResult]:
    """Compare a list of products against a use case.

    Normalizes yields, subtracts fees, applies FX scenarios if applicable,
    and checks constraints (min_amount, lockup).
    """
    results: List[ProductComparisonResult] = []

    for p in products:
        reasons: List[str] = []

        # 1. Check hard constraints
        if use_case.amount < p.min_amount:
            reasons.append(f"Amount {use_case.amount} below minimum {p.min_amount}")

        if p.lockup_days > use_case.holding_period_days:
            reasons.append(f"Lockup {p.lockup_days}d exceeds holding period {use_case.holding_period_days}d")

        if not use_case.allow_fx and p.currency != use_case.target_currency:
            reasons.append(f"FX not allowed, but product currency is {p.currency}")

        # 2. Net Yield Calculation (Annualized)
        # Simplified normalization: assume yield_value is already annualized for most types
        base_annual_yield = p.yield_value

        # Subtract fees (annualized)
        holding_period_years = use_case.holding_period_days / 365.0
        total_one_off_fees = p.redemption_fee + p.fx_fee
        annualized_one_off_fees = total_one_off_fees / holding_period_years if holding_period_years > 0 else 0

        net_base_yield = base_annual_yield - p.mgmt_fee_annual - annualized_one_off_fees

        scenarios: Dict[str, float] = {}

        # Apply FX shocks if applicable
        is_fx_case = p.currency != use_case.target_currency
        for scene, shock in use_case.fx_shocks.items():
            if is_fx_case:
                # Approximate: (1 + net_yield) * (1 + shock) - 1
                # For small yields/shocks: net_yield + shock + (net_yield * shock)
                s_yield = (1 + net_base_yield/100.0) * (1 + shock) - 1
                scenarios[scene] = round(s_yield * 100, 4)
            else:
                # Add some variance for non-fixed products even without FX?
                # Spec says "net_yield_scenarios（不是单点承诺）"
                # For simplicity, if no FX and it's a "standard" product, scenarios might be tight.
                if p.yield_type in [YieldType.ANNUALIZED_7D, YieldType.HISTORICAL_1Y]:
                    vol = 0.005 # 0.5% variance for money funds
                    if scene == "bull": scenarios[scene] = round(net_base_yield + vol*100, 4)
                    elif scene == "bear": scenarios[scene] = round(net_base_yield - vol*100, 4)
                    else: scenarios[scene] = round(net_base_yield, 4)
                else:
                    scenarios[scene] = round(net_base_yield, 4)

        # 3. Liquidity Score (0-100)
        # Fast redemption (T+0) = 100, T+1 = 80, T+3 = 60, etc.
        liq_score = max(0, 100 - p.settlement_days * 20)
        if p.lockup_days > 0:
            liq_score *= 0.5 # Penalty for lockup

        # 4. Coverage and Incomparability
        known_fields = 0
        total_fields = 5 # yield, fees, settlement, duration, credit
        if p.yield_value is not None: known_fields += 1
        if p.mgmt_fee_annual is not None: known_fields += 1
        if p.settlement_days is not None: known_fields += 1
        if p.duration is not None: known_fields += 1
        if p.credit_rating is not None: known_fields += 1

        coverage = known_fields / total_fields

        if coverage < 0.4:
            reasons.append(f"Insufficient data coverage: {coverage:.2f}")

        results.append(
            ProductComparisonResult(
                product_id=p.product_id,
                name=p.name,
                net_yield_scenarios=scenarios,
                fees_total_pct=round(p.mgmt_fee_annual * holding_period_years + total_one_off_fees, 4),
                liquidity_score=round(liq_score, 2),
                duration=p.duration,
                credit_rating=p.credit_rating,
                fx_exposure=p.currency if p.currency != use_case.target_currency else "None",
                data_quality=p.data_quality,
                coverage=round(coverage, 2),
                incomparable=len(reasons) > 0,
                incomparable_reasons=reasons,
            )
        )

    # Sort results: Comparable first, then by base net yield DESC, then stable product_id
    results.sort(
        key=lambda x: (
            x.incomparable,
            -x.net_yield_scenarios.get("base", -999.0),
            x.product_id,
        )
    )

    return results
