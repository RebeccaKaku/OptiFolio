"""USD Scenario Analysis — stress test portfolio against USD/CNY moves.

Provides a two-dimensional scenario matrix: product returns x FX changes.
Decomposes the impact into local return, FX effect, interaction, and fees.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict


class ExposureRole(str, Enum):
    """Role of an exposure in FX sensitivity analysis."""
    PAYOFF_CURRENCY = "payoff_currency"
    LOOKTHROUGH_ECONOMIC = "lookthrough_economic"
    HEDGED = "hedged"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class UsdExposure:
    """Represents a USD-denominated or USD-sensitive exposure."""
    amount_usd: Decimal
    role: ExposureRole
    hedged_ratio: Decimal = Decimal("0")
    asset_id: Optional[str] = None


@dataclass(frozen=True)
class ScenarioResult:
    """Result for a single scenario grid cell."""
    ending_value_usd: Decimal
    ending_value_cny: Decimal
    cny_return: Decimal
    local_component: Decimal
    fx_component: Decimal
    interaction: Decimal
    fees: Decimal
    relative_to_cny_benchmark: Decimal
    scenario_not_forecast: bool = True


def run_usd_scenarios(
    exposures: List[UsdExposure],
    product_return_scenarios: List[Decimal],
    fx_change_scenarios: List[Decimal],
    opening_fx: Decimal,
    fee_usd: Decimal = Decimal("0"),
    cny_benchmark_return: Decimal = Decimal("0"),
    fees_already_in_return: bool = False,
) -> List[List[ScenarioResult]]:
    """Execute scenario analysis across a grid of product and FX moves."""
    if opening_fx <= 0:
        raise ValueError("opening_fx must be positive")
    if not product_return_scenarios or not fx_change_scenarios:
        raise ValueError("Scenarios cannot be empty")

    # 1. Deduplicate exposures
    # Priority: PAYOFF_CURRENCY > HEDGED > LOOKTHROUGH_ECONOMIC > UNKNOWN
    unique_exposures: List[UsdExposure] = []
    id_map: Dict[str, UsdExposure] = {}

    for e in exposures:
        if e.asset_id is None:
            unique_exposures.append(e)
            continue

        if e.asset_id not in id_map:
            id_map[e.asset_id] = e
        else:
            existing = id_map[e.asset_id]
            priority = {
                ExposureRole.PAYOFF_CURRENCY: 4,
                ExposureRole.HEDGED: 3,
                ExposureRole.LOOKTHROUGH_ECONOMIC: 2,
                ExposureRole.UNKNOWN: 1,
            }
            if priority.get(e.role, 0) > priority.get(existing.role, 0):
                id_map[e.asset_id] = e

    unique_exposures.extend(id_map.values())

    total_opening_usd = sum(e.amount_usd for e in unique_exposures)
    total_opening_cny = total_opening_usd * opening_fx

    # Proportionally allocate fee among non-unknown exposures
    relevant_usd = sum(
        e.amount_usd for e in unique_exposures if e.role != ExposureRole.UNKNOWN
    )

    # 2. Prepare grid
    grid: List[List[ScenarioResult]] = []

    for r_prod in product_return_scenarios:
        row: List[ScenarioResult] = []
        for r_fx in fx_change_scenarios:
            cell_ending_usd = Decimal("0")
            cell_ending_cny = Decimal("0")
            cell_local = Decimal("0")
            cell_fx = Decimal("0")
            cell_interaction = Decimal("0")
            cell_fees = Decimal("0")

            for e in unique_exposures:
                op_usd = e.amount_usd
                op_cny = op_usd * opening_fx

                if e.role == ExposureRole.UNKNOWN:
                    cell_ending_usd += op_usd
                    cell_ending_cny += op_cny
                    continue

                # Effective FX shock for this exposure
                # PAYOFF_CURRENCY: FX move directly impacts CNY translation.
                # HEDGED: Only unhedged portion is impacted.
                # LOOKTHROUGH_ECONOMIC: Only as risk description, not directly pressured per spec.
                if e.role == ExposureRole.PAYOFF_CURRENCY:
                    r_fx_eff = r_fx
                elif e.role == ExposureRole.HEDGED:
                    r_fx_eff = r_fx * (Decimal("1") - e.hedged_ratio)
                else:  # LOOKTHROUGH_ECONOMIC
                    r_fx_eff = Decimal("0")

                # Fee allocation
                allocated_fee = Decimal("0")
                if not fees_already_in_return and relevant_usd > 0:
                    allocated_fee = fee_usd * (op_usd / relevant_usd)

                # Calculations
                end_usd = op_usd * (Decimal("1") + r_prod) - allocated_fee
                end_cny = end_usd * opening_fx * (Decimal("1") + r_fx_eff)

                # Attribution bridge (CNY)
                local = op_usd * r_prod * opening_fx
                fx_effect = op_usd * opening_fx * r_fx_eff
                interaction = op_usd * r_prod * opening_fx * r_fx_eff
                fees_impact = -allocated_fee * opening_fx * (Decimal("1") + r_fx_eff)

                cell_ending_usd += end_usd
                cell_ending_cny += end_cny
                cell_local += local
                cell_fx += fx_effect
                cell_interaction += interaction
                cell_fees += fees_impact

            cny_ret = (
                (cell_ending_cny / total_opening_cny) - Decimal("1")
                if total_opening_cny != 0
                else Decimal("0")
            )
            rel_benchmark = cell_ending_cny - (
                total_opening_cny * (Decimal("1") + cny_benchmark_return)
            )

            row.append(
                ScenarioResult(
                    ending_value_usd=cell_ending_usd,
                    ending_value_cny=cell_ending_cny,
                    cny_return=cny_ret,
                    local_component=cell_local,
                    fx_component=cell_fx,
                    interaction=cell_interaction,
                    fees=cell_fees,
                    relative_to_cny_benchmark=rel_benchmark,
                )
            )
        grid.append(row)

    return grid
