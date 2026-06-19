"""Return and FX attribution logic.

This module decomposes total return into product return, FX effect,
interaction term, fees, and cashflow components.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Any, Set, Tuple
from enum import Enum
from src.analytics.reconciliation import SnapshotInput, CashflowInput, CoverageLevel, PositionInput
from src.analytics.currency_aggregation import FxQuote

class AttributionQuality(str, Enum):
    EXACT = "exact"
    ESTIMATED = "estimated"
    NOT_ATTRIBUTABLE = "not_attributable"

@dataclass(frozen=True)
class AssetAttribution:
    """Attribution breakdown for a single asset (product in an account)."""
    account_id: str
    product_id: str
    currency: str

    # Amount-based attribution (in reporting currency)
    opening_value_reporting: Decimal
    closing_value_reporting: Decimal
    total_change_reporting: Decimal

    local_pnl_reporting: Decimal  # Change due to local price/income
    fx_pnl_reporting: Decimal     # Change due to FX rate movement
    interaction_pnl_reporting: Decimal # Cross term

    external_flows_reporting: Decimal
    fees_taxes_reporting: Decimal
    unclassified_reporting: Decimal

    # Return-based attribution (decimal)
    local_return: Optional[Decimal] = None
    fx_return: Optional[Decimal] = None
    interaction_return: Optional[Decimal] = None
    total_return_reporting: Optional[Decimal] = None

    quality: AttributionQuality = AttributionQuality.EXACT
    warnings: List[str] = field(default_factory=list)
    relative_loss_flag: bool = False  # USD gain but CNY relative loss

@dataclass(frozen=True)
class TotalAttribution:
    """Aggregated attribution across all assets."""
    reporting_currency: str
    opening_value: Decimal
    closing_value: Decimal
    total_change: Decimal

    local_pnl_reporting: Decimal
    fx_pnl_reporting: Decimal
    interaction_pnl_reporting: Decimal
    external_flows_reporting: Decimal
    fees_taxes_reporting: Decimal
    unclassified_reporting: Decimal

    total_return: Optional[Decimal] = None
    quality: AttributionQuality = AttributionQuality.EXACT
    asset_attributions: List[AssetAttribution] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

@dataclass(frozen=True)
class AttributionRequest:
    previous: SnapshotInput
    current: SnapshotInput
    cashflows: List[CashflowInput]
    fx_quotes: List[FxQuote]  # Should include quotes for all relevant dates
    reporting_currency: str = "CNY"
    fees_already_in_closing_value: bool = False

@dataclass(frozen=True)
class AttributionResult:
    total: TotalAttribution
    by_asset: List[AssetAttribution]

def attribute_returns(request: AttributionRequest) -> AttributionResult:
    """Pure function to decompose returns into various factors."""
    prev = request.previous
    curr = request.current
    reporting_curr = request.reporting_currency

    overall_quality = AttributionQuality.EXACT
    overall_warnings = []

    # Check coverage
    if any(cov != CoverageLevel.COMPLETE for cov in prev.account_coverage.values()):
        overall_quality = AttributionQuality.ESTIMATED
        overall_warnings.append("Previous snapshot has partial account coverage")
    if any(cov != CoverageLevel.COMPLETE for cov in curr.account_coverage.values()):
        overall_quality = AttributionQuality.ESTIMATED
        overall_warnings.append("Current snapshot has partial account coverage")
    if prev.cashflow_coverage != CoverageLevel.COMPLETE:
        overall_quality = AttributionQuality.ESTIMATED
        overall_warnings.append("Cashflow coverage is not complete")

    # Index FX quotes by (base, quote, as_of)
    fx_map: Dict[Tuple[str, str, date], Decimal] = {}
    for q in request.fx_quotes:
        fx_map[(q.base, q.quote, q.as_of)] = q.rate

    def get_fx(base: str, target: str, dt: date) -> Optional[Decimal]:
        if base == target:
            return Decimal("1")
        if (base, target, dt) in fx_map:
            return fx_map[(base, target, dt)]
        if (target, base, dt) in fx_map:
            return Decimal("1") / fx_map[(target, base, dt)]
        return None

    # Group positions by (account_id, product_id)
    all_keys = set()
    prev_pos: Dict[Tuple[str, str], PositionInput] = {}
    for p in prev.positions:
        key = (p.account_id, p.product_id)
        prev_pos[key] = p
        all_keys.add(key)

    curr_pos: Dict[Tuple[str, str], PositionInput] = {}
    for p in curr.positions:
        key = (p.account_id, p.product_id)
        curr_pos[key] = p
        all_keys.add(key)

    # Group cashflows by (account_id, product_id)
    asset_flows: Dict[Tuple[str, str], List[CashflowInput]] = {}
    for cf in request.cashflows:
        if not (prev.as_of < cf.effective_date <= curr.as_of):
            continue
        key = (cf.account_id, cf.product_id or "CASH") # If product_id is None, it might be cash in account
        if key not in asset_flows:
            asset_flows[key] = []
        asset_flows[key].append(cf)

    asset_attributions = []

    for key in sorted(all_keys):
        acc_id, prod_id = key
        p_prev = prev_pos.get(key)
        p_curr = curr_pos.get(key)

        currency = p_curr.currency if p_curr else (p_prev.currency if p_prev else "UNKNOWN")

        opening_local = p_prev.market_value if p_prev and p_prev.market_value is not None else Decimal("0")
        closing_local = p_curr.market_value if p_curr and p_curr.market_value is not None else Decimal("0")

        opening_fx = get_fx(currency, reporting_curr, prev.as_of)
        closing_fx = get_fx(currency, reporting_curr, curr.as_of)

        warnings = []
        quality = AttributionQuality.EXACT

        if opening_fx is None:
            warnings.append(f"Missing opening FX for {currency}")
            quality = AttributionQuality.NOT_ATTRIBUTABLE
        if closing_fx is None:
            warnings.append(f"Missing closing FX for {currency}")
            quality = AttributionQuality.NOT_ATTRIBUTABLE

        opening_reporting = opening_local * (opening_fx if opening_fx else Decimal("0"))
        closing_reporting = closing_local * (closing_fx if closing_fx else Decimal("0"))

        # Aggregate flows for this asset
        flows = asset_flows.get(key, [])
        ext_flows_local = Decimal("0")
        fees_local = Decimal("0")
        income_local = Decimal("0")

        ext_flows_rep = Decimal("0")
        fees_rep = Decimal("0")

        for cf in flows:
            if cf.currency != currency:
                warnings.append(f"Flow currency mismatch: {cf.currency} vs asset {currency}")
                quality = AttributionQuality.ESTIMATED
                # Try to convert to asset currency if needed? For now just skip or use reporting?
                # Actually, let's just use it as is if it's the same, or convert to reporting directly.

            # Identify flow type
            amt = cf.amount
            if cf.event_type in ('external_contribution', 'external_withdrawal', 'purchase', 'sale', 'transfer_in', 'transfer_out'):
                ext_flows_local += amt
                # Convert to reporting currency
                cf_fx = get_fx(cf.currency, reporting_curr, cf.effective_date)
                if cf_fx:
                    ext_flows_rep += amt * cf_fx
                else:
                    # Estimate flow FX using average of opening/closing or just closing
                    warnings.append(f"Missing FX for flow {cf.event_id} on {cf.effective_date}, using closing FX")
                    quality = AttributionQuality.ESTIMATED
                    if closing_fx:
                        ext_flows_rep += amt * closing_fx

            elif cf.event_type in ('fee', 'tax'):
                fees_local += amt # usually negative
                # Fees are converted at closing FX per spec
                if closing_fx:
                    fees_rep += amt * closing_fx
                else:
                    quality = AttributionQuality.ESTIMATED
            elif cf.event_type in ('interest', 'dividend', 'coupon'):
                income_local += amt
                # Income is part of local pnl, but we track it if we want gross vs net
                # For now let's treat it as part of local price change in terms of decomposition
                # OR should we treat it as a flow? Spec says "product return + FX + interaction + fees + cashflow"
                # "cashflow" here likely means external flows.
                # Investment income is part of product return.

        # Calculation of local PNL (gross)
        # If fees_already_in_closing_value is true, closing_local already has fees deducted.
        # Identity: closing_local = opening_local + local_pnl + ext_flows_local + income_local + fees_local
        # gross_local_pnl = local_pnl + income_local
        # So gross_local_pnl = closing_local - opening_local - ext_flows_local - (fees_local if net else 0)

        if request.fees_already_in_closing_value:
            gross_local_pnl = closing_local - opening_local - ext_flows_local - fees_local
        else:
            gross_local_pnl = closing_local - opening_local - ext_flows_local
            # If fees are NOT in closing value, it means they are outside.
            # But the identity usually is about the book value.

        local_pnl_rep = gross_local_pnl * (opening_fx if opening_fx else Decimal("0"))
        fx_pnl_rep = opening_local * ((closing_fx - opening_fx) if (closing_fx and opening_fx) else Decimal("0"))
        interaction_pnl_rep = gross_local_pnl * ((closing_fx - opening_fx) if (closing_fx and opening_fx) else Decimal("0"))

        total_change_rep = closing_reporting - opening_reporting

        # Identity Check: total_change = local_pnl_rep + fx_pnl_rep + interaction_pnl_rep + flows_rep + fees_rep + unclassified
        # Note: fees_rep is usually negative, so -fees_reporting in spec means we subtract a negative, which is add.
        # "local_pnl_reporting + fx_effect + interaction_effect - fees_reporting + external_flows_reporting + unclassified"
        # My fees_rep is negative if it's a fee. Spec says -fees_reporting. So I should use positive for deduction.
        # Let's align with spec: fees_reporting is the absolute cost or signed?
        # Re-reading: "R_local 是扣费前产品回报；费用作为期末从产品计价币种扣除的独立金额... bridge 只做展示而不得再次扣除"
        # Let's use signed amounts. Fees are negative.

        # Re-calc unclassified to force identity
        explained = local_pnl_rep + fx_pnl_rep + interaction_pnl_rep + ext_flows_rep + fees_rep
        unclassified_rep = total_change_rep - explained

        # Return calculation
        local_ret = None
        fx_ret = None
        inter_ret = None
        total_ret = None

        if quality != AttributionQuality.NOT_ATTRIBUTABLE and opening_local > 0:
            # We need to decide how to handle flows for return calculation.
            # Simple return if no flows: R = (closing - opening) / opening
            # If there are flows, the spec says: "有现金流时只接受上游提供且标记方法的回报或输出 not_attributable，不得自行套简单收益率"
            if ext_flows_local == 0 and fees_local == 0 and income_local == 0:
                local_ret = gross_local_pnl / opening_local
                if opening_fx and closing_fx and opening_fx > 0:
                    fx_ret = (closing_fx / opening_fx) - 1
                    inter_ret = local_ret * fx_ret
                    total_ret = (1 + local_ret) * (1 + fx_ret) - 1
            else:
                # Flow present, cannot use simple return
                quality = AttributionQuality.ESTIMATED # Or NOT_ATTRIBUTABLE for returns
                warnings.append("Returns not calculated due to cashflows (simple return invalid)")
        elif opening_local == 0 and closing_local != 0:
            quality = AttributionQuality.ESTIMATED
            warnings.append("Opening value is zero, returns not attributable")

        rel_loss = False
        if local_ret is not None and total_ret is not None:
            if local_ret > 0 and total_ret < 0:
                rel_loss = True

        asset_attributions.append(AssetAttribution(
            account_id=acc_id,
            product_id=prod_id,
            currency=currency,
            opening_value_reporting=opening_reporting,
            closing_value_reporting=closing_reporting,
            total_change_reporting=total_change_rep,
            local_pnl_reporting=local_pnl_rep,
            fx_pnl_reporting=fx_pnl_rep,
            interaction_pnl_reporting=interaction_pnl_rep,
            external_flows_reporting=ext_flows_rep,
            fees_taxes_reporting=fees_rep,
            unclassified_reporting=unclassified_rep,
            local_return=local_ret,
            fx_return=fx_ret,
            interaction_return=inter_ret,
            total_return_reporting=total_ret,
            quality=quality,
            warnings=warnings,
            relative_loss_flag=rel_loss
        ))

    # Aggregate to total
    total_opening = sum(a.opening_value_reporting for a in asset_attributions)
    total_closing = sum(a.closing_value_reporting for a in asset_attributions)
    total_change = total_closing - total_opening

    total_local_pnl = sum(a.local_pnl_reporting for a in asset_attributions)
    total_fx_pnl = sum(a.fx_pnl_reporting for a in asset_attributions)
    total_inter_pnl = sum(a.interaction_pnl_reporting for a in asset_attributions)
    total_flows = sum(a.external_flows_reporting for a in asset_attributions)
    total_fees = sum(a.fees_taxes_reporting for a in asset_attributions)
    total_unclassified = sum(a.unclassified_reporting for a in asset_attributions)

    total_quality = overall_quality
    if any(a.quality == AttributionQuality.NOT_ATTRIBUTABLE for a in asset_attributions):
        total_quality = AttributionQuality.ESTIMATED
    elif any(a.quality == AttributionQuality.ESTIMATED for a in asset_attributions):
        total_quality = AttributionQuality.ESTIMATED

    # Total return calculation (simple)
    total_ret = None
    if total_opening > 0 and total_flows == 0 and total_fees == 0:
        total_ret = total_change / total_opening

    total_attr = TotalAttribution(
        reporting_currency=reporting_curr,
        opening_value=total_opening,
        closing_value=total_closing,
        total_change=total_change,
        local_pnl_reporting=total_local_pnl,
        fx_pnl_reporting=total_fx_pnl,
        interaction_pnl_reporting=total_inter_pnl,
        external_flows_reporting=total_flows,
        fees_taxes_reporting=total_fees,
        unclassified_reporting=total_unclassified,
        total_return=total_ret,
        quality=total_quality,
        asset_attributions=asset_attributions,
        warnings=overall_warnings
    )

    return AttributionResult(total=total_attr, by_asset=asset_attributions)
