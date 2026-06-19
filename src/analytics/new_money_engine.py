"""New Money Rule Engine.

Generates multiple allocation proposals for new cash based on rules and constraints.
"""

from __future__ import annotations
import dataclasses
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Literal, Any
from src.analytics.allocation_targets import AllocationGapReport
from src.analytics.trade_friction import AllocationFrictionInput, TradeFrictionRequest, calculate_trade_friction


@dataclass(frozen=True)
class CandidateProduct:
    """A product available for new money allocation."""
    asset_id: str
    name: str
    currency: str
    asset_class: str
    issuer: str
    purpose_bucket: str
    liquidity_level: str  # low, medium, high, unknown
    min_trade_amount: Decimal = Decimal("0")
    max_trade_amount: Optional[Decimal] = None
    friction_input: Optional[AllocationFrictionInput] = None
    monetized_benefit_annual_rate: Optional[Decimal] = None
    # metadata for explanation
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NewMoneyConstraints:
    """Constraints for the new money allocation."""
    liquidity_low_min_pct: Decimal = Decimal("0")  # Minimum % of total value in 'low' liquidity
    single_product_max_pct: Decimal = Decimal("1.0")
    single_issuer_max_pct: Decimal = Decimal("1.0")
    max_cash_retention_pct: Decimal = Decimal("1.0")  # Max % of NEW cash that can remain as residual
    expected_holding_period_years: Decimal = Decimal("1.0")
    no_trade_band_pct: Decimal = Decimal("0")


@dataclass(frozen=True)
class NewMoneyRequest:
    """Request for new money allocation proposals."""
    new_cash_amount: Decimal
    currency: str
    reporting_currency: str
    fx_rates: Dict[str, Decimal]  # Map from currency to reporting_currency (e.g. USD -> 7.2)
    current_total_value: Decimal  # In reporting currency
    current_exposures: Dict[str, Dict[str, Decimal]]  # dimension -> bucket -> weight (0-1)
    gaps: List[AllocationGapReport]
    candidates: List[CandidateProduct]
    constraints: NewMoneyConstraints


@dataclass(frozen=True)
class AllocationItem:
    """A single allocation to a product."""
    asset_id: str
    name: str
    amount_original: Decimal
    currency: str
    amount_reporting: Decimal


@dataclass(frozen=True)
class NewMoneyProposal:
    """A generated allocation proposal."""
    strategy: str  # gap_first, liquidity_first, diversification_first
    allocations: List[AllocationItem]
    residual_cash: Decimal  # In original currency
    post_trade_total_value: Decimal  # In reporting currency
    post_trade_weights: Dict[str, Dict[str, Decimal]]  # dimension -> bucket -> weight
    satisfied_constraints: List[str]
    binding_constraints: List[str]
    rejected_candidates: List[Dict[str, str]]  # asset_id -> reason
    explanation: str
    status: Literal["success", "partial", "failed"]


@dataclass(frozen=True)
class _AssetExposure:
    """Internal helper to track exposures during allocation."""
    product_id: str
    issuer: str
    currency: str
    asset_class: str
    purpose_bucket: str
    liquidity_level: str


class NewMoneyEngine:
    """Core engine for generating new money allocation proposals."""

    def run(self, request: NewMoneyRequest) -> List[NewMoneyProposal]:
        """Generate multiple proposals based on different strategies."""
        proposals = []
        strategies = ["gap_first", "liquidity_first", "diversification_first"]

        for strategy in strategies:
            proposals.append(self._generate_proposal(request, strategy))

        return proposals

    def _generate_proposal(self, request: NewMoneyRequest, strategy: str) -> NewMoneyProposal:
        allocations: List[AllocationItem] = []
        residual_cash_orig = request.new_cash_amount
        satisfied_constraints = []
        binding_constraints = []
        rejected_candidates = []
        explanation_parts = [f"Strategy: {strategy}"]

        # 0. Check if we have FX rate for the NEW cash currency itself
        if request.currency != request.reporting_currency and request.currency not in request.fx_rates:
             return NewMoneyProposal(
                strategy=strategy,
                allocations=[],
                residual_cash=request.new_cash_amount.quantize(Decimal("0.000001")),
                post_trade_total_value=request.current_total_value,
                post_trade_weights=request.current_exposures,
                satisfied_constraints=[],
                binding_constraints=[],
                rejected_candidates=[{"asset_id": "GLOBAL", "reason": f"Missing FX rate for new cash currency {request.currency}"}],
                explanation="Missing FX rate for new cash currency",
                status="failed"
            )

        new_cash_rep = self._to_reporting(request.new_cash_amount, request.currency, request.fx_rates)
        post_trade_total_val_rep = request.current_total_value + new_cash_rep

        # Scaling factor for existing weights: V_old / V_new
        scaling_factor = request.current_total_value / post_trade_total_val_rep if post_trade_total_val_rep > 0 else Decimal("0")

        # Initialize post_trade_weights with scaled existing exposures
        post_trade_weights: Dict[str, Dict[str, Decimal]] = {}
        for dim, buckets in request.current_exposures.items():
            post_trade_weights[dim] = {b: w * scaling_factor for b, w in buckets.items()}

        # 1. Filter candidates by currency
        valid_candidates = []
        for c in request.candidates:
            if c.currency == request.reporting_currency:
                valid_candidates.append(c)
            elif c.currency in request.fx_rates:
                valid_candidates.append(c)
            else:
                rejected_candidates.append({"asset_id": c.asset_id, "reason": f"Missing FX rate for candidate currency {c.currency}"})

        # 2. Sort candidates based on strategy
        sorted_candidates = self._sort_candidates(valid_candidates, request, strategy)

        # 3. Greedy allocation
        for candidate in sorted_candidates:
            if residual_cash_orig <= 0:
                break

            # Calculate max possible allocation for this candidate based on constraints
            alloc_rep = self._calculate_max_allocation(candidate, residual_cash_orig, request, post_trade_weights, post_trade_total_val_rep)

            if alloc_rep > 0:
                # 3.1 Friction analysis
                if candidate.friction_input:
                    fi = candidate.friction_input
                    # Apply fallbacks
                    if fi.no_trade_band_pct is None:
                        fi = dataclasses.replace(fi, no_trade_band_pct=request.constraints.no_trade_band_pct)
                    if fi.min_trade_amount is None and candidate.min_trade_amount > 0:
                        min_trade_rep = self._to_reporting(candidate.min_trade_amount, candidate.currency, request.fx_rates)
                        fi = dataclasses.replace(fi, min_trade_amount=min_trade_rep)

                    fx_rate = request.fx_rates.get(candidate.currency, Decimal("1.0"))
                    friction_req = TradeFrictionRequest(
                        amount_reporting=alloc_rep,
                        total_portfolio_value_reporting=post_trade_total_val_rep,
                        expected_holding_period_years=request.constraints.expected_holding_period_years,
                        reporting_currency=request.reporting_currency,
                        friction_input=fi,
                        monetized_benefit_annual_rate=candidate.monetized_benefit_annual_rate,
                        fx_rate_to_reporting=fx_rate
                    )
                    friction_res = calculate_trade_friction(friction_req)
                    if friction_res.no_trade:
                        rejected_candidates.append({
                            "asset_id": candidate.asset_id,
                            "reason": f"No-trade recommendation: {'; '.join(friction_res.reasons)}"
                        })
                        continue
                    # Adjust allocation if friction limited it
                    if friction_res.eligible_allocations < alloc_rep:
                        alloc_rep = friction_res.eligible_allocations

                # Check min trade amount
                alloc_orig = self._from_reporting(alloc_rep, candidate.currency, request.fx_rates)
                if alloc_orig < candidate.min_trade_amount:
                    # Try to allocate exactly min_trade_amount if possible
                    min_alloc_rep = self._to_reporting(candidate.min_trade_amount, candidate.currency, request.fx_rates)
                    if self._can_allocate(candidate, min_alloc_rep, residual_cash_orig, request, post_trade_weights, post_trade_total_val_rep):
                        alloc_rep = min_alloc_rep
                        alloc_orig = candidate.min_trade_amount
                    else:
                        rejected_candidates.append({"asset_id": candidate.asset_id, "reason": f"Required amount {alloc_orig} is below min trade {candidate.min_trade_amount} or hits constraints"})
                        continue

                # Execute allocation
                allocations.append(AllocationItem(
                    asset_id=candidate.asset_id,
                    name=candidate.name,
                    amount_original=alloc_orig,
                    currency=candidate.currency,
                    amount_reporting=alloc_rep
                ))
                # Update residual cash in ORIGINAL currency
                consumed_orig = self._convert(alloc_rep, candidate.currency, request.currency, request.fx_rates)
                residual_cash_orig -= consumed_orig
                self._update_weights(candidate, alloc_rep, post_trade_weights, post_trade_total_val_rep)
            else:
                 rejected_candidates.append({"asset_id": candidate.asset_id, "reason": "Constraints reached or no gap"})

        # Final constraints check
        # Liquidity floor check
        low_liq_w = sum(w for bucket, w in post_trade_weights.get("liquidity", {}).items() if bucket == "low")
        if low_liq_w >= request.constraints.liquidity_low_min_pct:
            satisfied_constraints.append("liquidity_low_min_pct")
        else:
            binding_constraints.append("liquidity_low_min_pct")

        # Max cash retention check
        retention_pct = residual_cash_orig / request.new_cash_amount if request.new_cash_amount > 0 else Decimal("0")
        if retention_pct <= request.constraints.max_cash_retention_pct:
            satisfied_constraints.append("max_cash_retention_pct")
        else:
            binding_constraints.append("max_cash_retention_pct")

        status: Literal["success", "partial", "failed"] = "success"
        if residual_cash_orig == request.new_cash_amount:
            status = "failed"
        elif residual_cash_orig > 0:
            status = "partial"

        # Final explanation
        explanation_parts.append(f"Status: {status}")
        explanation_parts.append(f"Allocated: {len(allocations)} products")
        explanation_parts.append(f"Residual: {residual_cash_orig} {request.currency}")

        return NewMoneyProposal(
            strategy=strategy,
            allocations=allocations,
            residual_cash=residual_cash_orig.quantize(Decimal("0.000001")),
            post_trade_total_value=post_trade_total_val_rep,
            post_trade_weights={dim: {b: round(w, 6) for b, w in buckets.items()} for dim, buckets in post_trade_weights.items()},
            satisfied_constraints=satisfied_constraints,
            binding_constraints=binding_constraints,
            rejected_candidates=rejected_candidates,
            explanation="\n".join(explanation_parts),
            status=status
        )

    def _sort_candidates(self, candidates: List[CandidateProduct], request: NewMoneyRequest, strategy: str) -> List[CandidateProduct]:
        if strategy == "gap_first":
            # Sort by gap size (desc)
            gap_map = {}
            for report in request.gaps:
                for item in report.items:
                    if item.status == "below":
                         gap_map[(report.dimension, item.bucket)] = item.gap_to_min

            def gap_score(c):
                # Sum of gaps this candidate fills
                score = Decimal("0")
                if ("product", c.asset_id) in gap_map: score += gap_map[("product", c.asset_id)]
                if ("issuer", c.issuer) in gap_map: score += gap_map[("issuer", c.issuer)]
                if ("currency", c.currency) in gap_map: score += gap_map[("currency", c.currency)]
                if ("asset_class", c.asset_class) in gap_map: score += gap_map[("asset_class", c.asset_class)]
                if ("purpose_bucket", c.purpose_bucket) in gap_map: score += gap_map[("purpose_bucket", c.purpose_bucket)]
                return score

            return sorted(candidates, key=lambda c: (-gap_score(c), c.asset_id))

        elif strategy == "liquidity_first":
            # Sort by liquidity (low restriction first)
            order = {"low": 0, "medium": 1, "high": 2, "unknown": 3}
            return sorted(candidates, key=lambda c: (order.get(c.liquidity_level, 3), c.asset_id))

        elif strategy == "diversification_first":
            # Sort by current concentration (asc)
            def conc_score(c):
                score = Decimal("0")
                score += request.current_exposures.get("issuer", {}).get(c.issuer, Decimal("0"))
                score += request.current_exposures.get("product", {}).get(c.asset_id, Decimal("0"))
                return score
            return sorted(candidates, key=lambda c: (conc_score(c), c.asset_id))

        return candidates

    def _calculate_max_allocation(self, candidate: CandidateProduct, residual_orig: Decimal, request: NewMoneyRequest, weights: Dict[str, Dict[str, Decimal]], total_val_rep: Decimal) -> Decimal:
        residual_rep = self._to_reporting(residual_orig, request.currency, request.fx_rates)

        # 1. Product cap
        current_prod_w = weights.get("product", {}).get(candidate.asset_id, Decimal("0"))
        max_prod_w = request.constraints.single_product_max_pct
        avail_prod_w = max(Decimal("0"), max_prod_w - current_prod_w)
        limit_prod_rep = avail_prod_w * total_val_rep

        # 2. Issuer cap
        current_iss_w = weights.get("issuer", {}).get(candidate.issuer, Decimal("0"))
        max_iss_w = request.constraints.single_issuer_max_pct
        avail_iss_w = max(Decimal("0"), max_iss_w - current_iss_w)
        limit_iss_rep = avail_iss_w * total_val_rep

        # 3. Max trade amount
        limit_trade_rep = Decimal("Infinity")
        if candidate.max_trade_amount:
            limit_trade_rep = self._to_reporting(candidate.max_trade_amount, candidate.currency, request.fx_rates)

        # 4. Cash retention (Soft? or Hard?) - Let's assume hard for now
        # Actually, let's just use residual_rep as the primary limit

        return min(residual_rep, limit_prod_rep, limit_iss_rep, limit_trade_rep)

    def _can_allocate(self, candidate: CandidateProduct, amount_rep: Decimal, residual_orig: Decimal, request: NewMoneyRequest, weights: Dict[str, Dict[str, Decimal]], total_val_rep: Decimal) -> bool:
        residual_rep = self._to_reporting(residual_orig, request.currency, request.fx_rates)
        if amount_rep > residual_rep: return False

        # Product cap
        current_prod_w = weights.get("product", {}).get(candidate.asset_id, Decimal("0"))
        if (current_prod_w + amount_rep / total_val_rep) > request.constraints.single_product_max_pct: return False

        # Issuer cap
        current_iss_w = weights.get("issuer", {}).get(candidate.issuer, Decimal("0"))
        if (current_iss_w + amount_rep / total_val_rep) > request.constraints.single_issuer_max_pct: return False

        return True

    def _update_weights(self, candidate: CandidateProduct, amount_rep: Decimal, weights: Dict[str, Dict[str, Decimal]], total_val_rep: Decimal):
        w_inc = amount_rep / total_val_rep
        dims = {
            "product": candidate.asset_id,
            "issuer": candidate.issuer,
            "currency": candidate.currency,
            "asset_class": candidate.asset_class,
            "purpose_bucket": candidate.purpose_bucket,
            "liquidity": candidate.liquidity_level
        }
        for dim, bucket in dims.items():
            if dim not in weights: weights[dim] = {}
            weights[dim][bucket] = weights[dim].get(bucket, Decimal("0")) + w_inc

    def _to_reporting(self, amount: Decimal, currency: str, fx_rates: Dict[str, Decimal]) -> Decimal:
        if currency in fx_rates:
            return amount * fx_rates[currency]
        return amount

    def _from_reporting(self, amount_rep: Decimal, target_currency: str, fx_rates: Dict[str, Decimal]) -> Decimal:
        if target_currency in fx_rates:
            return amount_rep / fx_rates[target_currency]
        return amount_rep

    def _convert(self, amount: Decimal, from_currency: str, to_currency: str, fx_rates: Dict[str, Decimal]) -> Decimal:
        """Convert amount from one currency to another via reporting currency."""
        if from_currency == to_currency:
            return amount
        amount_rep = self._to_reporting(amount, from_currency, fx_rates)
        to_rate = fx_rates.get(to_currency, Decimal("1"))
        if to_currency in fx_rates:
            return amount_rep / fx_rates[to_currency]
        return amount_rep
