"""Case Study Service — orchestrates USD case study analysis and journal draft generation.
"""

from typing import Any, Dict, List, Optional
from decimal import Decimal
from datetime import date, timedelta

from src.analytics.case_study import (
    calculate_case_study,
    CaseStudyRequest,
    CaseStudyResult,
    CaseStudyCashflow,
    ReturnMethod
)
from src.analytics.usd_scenario import run_usd_scenarios, UsdExposure, ExposureRole
from src.services.response import success, failure

class CaseStudyService:
    def analyze(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Runs the case study analysis and generates a decision journal draft."""
        try:
            # 1. Parse Request
            cashflows = []
            for cf in payload.get("cashflows", []):
                cashflows.append(CaseStudyCashflow(
                    amount=Decimal(str(cf["amount"])),
                    effective_date=date.fromisoformat(cf["effective_date"]),
                    event_type=cf["event_type"],
                    currency=cf.get("currency", "USD")
                ))

            request = CaseStudyRequest(
                opening_value_usd=Decimal(str(payload["opening_value_usd"])),
                closing_value_usd=Decimal(str(payload["closing_value_usd"])),
                opening_fx=Decimal(str(payload["opening_fx"])),
                closing_fx=Decimal(str(payload["closing_fx"])),
                fee_usd=Decimal(str(payload.get("fee_usd", 0))),
                cny_benchmark_return=Decimal(str(payload.get("cny_benchmark_return", 0))),
                cashflows=cashflows,
                return_method=ReturnMethod(payload.get("return_method", "TWR")),
                caller_supplied_usd_return=Decimal(str(payload["caller_supplied_usd_return"])) if "caller_supplied_usd_return" in payload and payload["caller_supplied_usd_return"] is not None else None,
                data_quality=payload.get("data_quality", "confirmed")
            )

            # 2. Calculate Main Results
            result = calculate_case_study(request)

            # 3. Generate Scenario Matrix (if requested or as default)
            scenario_grid = []
            if payload.get("include_scenarios", True):
                # Use standard scenarios: -5% to +5% for both product and FX
                prod_scenarios = [Decimal(s) for s in ["-0.05", "-0.02", "0.0", "0.02", "0.05"]]
                fx_scenarios = [Decimal(s) for s in ["-0.05", "-0.02", "0.0", "0.02", "0.05"]]

                exposures = [UsdExposure(
                    amount_usd=request.opening_value_usd,
                    role=ExposureRole.PAYOFF_CURRENCY
                )]

                scenario_grid = run_usd_scenarios(
                    exposures=exposures,
                    product_return_scenarios=prod_scenarios,
                    fx_change_scenarios=fx_scenarios,
                    opening_fx=request.opening_fx,
                    fee_usd=request.fee_usd,
                    cny_benchmark_return=request.cny_benchmark_return
                )

            # 4. Generate Journal Draft
            journal_draft = self.generate_journal_draft(request, result, scenario_grid)

            return success({
                "analysis": {
                    "usd_product_return": float(result.usd_product_return),
                    "local_pnl_cny": float(result.local_pnl_cny),
                    "fx_effect_cny": float(result.fx_effect_cny),
                    "interaction_cny": float(result.interaction_cny),
                    "fees_friction_cny": float(result.fees_friction_cny),
                    "external_flows_cny": float(result.external_flows_cny),
                    "total_change_cny": float(result.total_change_cny),
                    "cny_wealth_result": float(result.cny_wealth_result),
                    "cny_benchmark_result": float(result.cny_benchmark_result),
                    "relative_alpha_cny": float(result.relative_alpha_cny),
                    "unclassified_cny": float(result.unclassified_cny),
                    "quality": result.quality,
                    "warnings": result.warnings,
                    "facts": result.facts,
                    "hypotheses": result.hypotheses,
                    "opinions": result.opinions
                },
                "scenarios": self._serialize_grid(scenario_grid) if scenario_grid else None,
                "journal_draft": journal_draft
            })

        except Exception as e:
            return failure(str(e), "CASE_STUDY_ERROR")

    def generate_journal_draft(
        self,
        request: CaseStudyRequest,
        result: CaseStudyResult,
        scenario_grid: List[List[Any]]
    ) -> Dict[str, Any]:
        """Constructs a draft for the decision journal."""

        thesis = f"USD investment case study. Local return: {result.usd_product_return*100:.2f}%. "
        if result.relative_alpha_cny < 0:
            thesis += "Observation: underperformed CNY benchmark when converted."
        else:
            thesis += "Observation: outperformed CNY benchmark."

        baseline = f"Invest in CNY alternative with expected return of {request.cny_benchmark_return*100:.2f}%."

        # Scenarios summary
        priced_in = "USD/CNY exchange rate stability or appreciation was expected."

        invalidation = [
            "USD/CNY depreciates more than product return.",
            "Product return falls significantly below expectation."
        ]

        return {
            "title": f"USD Case Study Analysis ({date.today().isoformat()})",
            "thesis": thesis,
            "baseline": baseline,
            "priced_in": priced_in,
            "evidence_json": {
                "facts": result.facts,
                "quality": result.quality
            },
            "scenarios_json": {
                "grid_summary": "5x5 USD/CNY Sensitivity Matrix",
                "calculated_alpha": float(result.relative_alpha_cny)
            },
            "position_reason": "Historical review of USD Treasury WMP performance vs CNY liquidity.",
            "invalidation_conditions": "\n".join(invalidation),
            "review_at": (date.today() + timedelta(days=90)).isoformat(),
            "author_type": "human"
        }

    def _serialize_grid(self, grid: List[List[Any]]) -> List[List[Dict[str, Any]]]:
        serialized = []
        for row in grid:
            serialized_row = []
            for cell in row:
                serialized_row.append({
                    "ending_value_usd": float(cell.ending_value_usd),
                    "ending_value_cny": float(cell.ending_value_cny),
                    "cny_return": float(cell.cny_return),
                    "local_component": float(cell.local_component),
                    "fx_component": float(cell.fx_component),
                    "interaction": float(cell.interaction),
                    "fees": float(cell.fees),
                    "relative_to_cny_benchmark": float(cell.relative_to_cny_benchmark)
                })
            serialized.append(serialized_row)
        return serialized
