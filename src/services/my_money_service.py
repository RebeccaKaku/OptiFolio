"""Service for the "My Money" trusted home page.

This service aggregates portfolio book data, values it using the unified
portfolio valuation engine, and provides a trusted summary of assets and
performance.

Valuation is unified with PortfolioService — both use ValuationEngine.value()
for the canonical total. Per-asset quality/freshness labels come from
BookValuationService for the "data quality" display.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.analytics.currency_aggregation import CurrencyAggregator, FxQuote
from src.analytics.reconciliation import (
    reconcile_snapshots,
    ReconciliationRequest,
    SnapshotInput,
    PositionInput,
    CashflowInput,
    CoverageLevel,
)
from optifolio_contracts.quality import ValuationQuality
from src.core.portfolio_book_db import PortfolioBookDatabase
from src.services.book_valuation_service import BookValuationService
from src.services.response import success, failure

_log = logging.getLogger(__name__)


class MyMoneyService:
    """Orchestrates the home page summary with dual-currency and trusted returns."""

    def __init__(
        self,
        db: PortfolioBookDatabase,
        valuation_svc: BookValuationService,
        data_provider: Any,
        portfolio_service: Any = None,
    ) -> None:
        self._db = db
        self._valuation_svc = valuation_svc
        self._data_provider = data_provider
        self._portfolio_service = portfolio_service
        self._aggregator = CurrencyAggregator()

    def get_summary(
        self, as_of: Optional[date] = None, reporting_currency: str = "CNY"
    ) -> Dict[str, Any]:
        """Generate the comprehensive "My Money" summary."""
        try:
            target_date = as_of or date.today()
            as_of_str = target_date.isoformat()

            # 1. Get the latest confirmed batch
            latest_batch = self._db.get_latest_confirmed_batch(as_of_str)
            if not latest_batch:
                return success(
                    {
                        "has_data": False,
                        "message": "No confirmed snapshots found. Please complete onboarding.",
                    }
                )

            # 2. Get per-asset quality labels from BookValuationService
            val_res = self._valuation_svc.value_batch(latest_batch["batch_id"])
            if not val_res["success"]:
                return val_res

            valuations = val_res["data"]["valuations"]

            # 3. Get canonical total from PortfolioService (unified valuation path)
            # Use strict=False so positions without today's price use the last
            # available price with stale_days annotation — the overview should
            # always show an estimated total rather than nothing.
            portfolio_total = None
            if self._portfolio_service is not None:
                try:
                    pv = self._portfolio_service.get_value(
                        as_of=target_date, base_currency=reporting_currency, strict=False,
                    )
                    if pv.get("success"):
                        portfolio_total = pv["data"].get("total_value")
                except Exception:
                    _log.debug("PortfolioService valuation failed; falling back to aggregator total")

            # 4. Aggregate valuations for currency breakdown
            currencies = {v["currency"] for v in valuations} | {reporting_currency, "USD", "CNY"}
            fx_quotes = self._get_fx_quotes(currencies, reporting_currency, target_date)

            from src.domain import ValuationResult as SingleAssetValuationResult
            from optifolio_contracts.quality import ValuationFreshness
            val_objs = []
            for v in valuations:
                val_objs.append(SingleAssetValuationResult(
                    as_of=target_date,
                    total_value=0.0,
                    holdings_value=0.0,
                    cash_value=0.0,
                    base_currency=reporting_currency,
                    amount=v["amount"],
                    currency=v["currency"],
                    valuation_date=date.fromisoformat(v["valuation_date"]) if v["valuation_date"] else None,
                    known_at=date.fromisoformat(v["known_at"]) if v["known_at"] else None,
                    source_type=v["source_type"],
                    source_id=v["source_id"],
                    quality=ValuationQuality(v["quality"]),
                    freshness=ValuationFreshness(v["freshness"]),
                    is_estimate=v["is_estimate"],
                    age_days=v["age_days"],
                    warnings=v["warnings"]
                ))

            agg_res = self._aggregator.aggregate(
                val_objs, fx_quotes, reporting_currency, target_date
            )

            # 5. Reconciliation for returns
            prev_batch = self._db.get_previous_confirmed_batch(latest_batch["as_of"])
            recon_data = None
            return_status = "unavailable"
            return_reason = "No previous snapshot to compare against."

            if prev_batch:
                if prev_batch.get("status") != "confirmed":
                    return_reason = (
                        "Previous snapshot is not confirmed — comparison is not meaningful."
                    )
                    _log.warning(
                        "Skipping reconciliation: prev_batch %s has status=%s (not confirmed)",
                        prev_batch.get("batch_id"), prev_batch.get("status"),
                    )
                else:
                    prev_val_res = self._valuation_svc.value_batch(prev_batch["batch_id"])
                    if prev_val_res["success"]:
                        prev_vals = prev_val_res["data"]["valuations"]

                        recon_data, return_status, return_reason = self._perform_reconciliation(
                            prev_batch, prev_vals, latest_batch, valuations,
                            reporting_currency, fx_quotes
                        )

            positions = self._build_position_rows(latest_batch, valuations)

            # 6. Build final response — use unified portfolio total when available
            total_assets = portfolio_total if portfolio_total is not None else float(agg_res.reporting_total)
            summary = {
                "has_data": True,
                "as_of": latest_batch["as_of"],
                "valuation_as_of": target_date.isoformat(),
                "reporting_currency": reporting_currency,
                "total_assets_reporting": total_assets,
                "total_is_exact": agg_res.reporting_total_is_exact,
                "valuation_source": "PortfolioService" if portfolio_total is not None else "Aggregator",
                "positions": positions,
                "by_currency": {
                    curr: {
                        "amount_original": float(sub.amount_original),
                        "amount_reporting": float(sub.amount_reporting),
                        "count": sub.count,
                        "unknown_count": sub.unknown_count,
                        "is_estimated": sub.is_estimated,
                    }
                    for curr, sub in agg_res.by_original_currency.items()
                },
                "quality_summary": {q.value: count for q, count in agg_res.quality_summary.items()},
                "return_status": return_status,
                "return_reason": return_reason,
                "performance": recon_data,
                "warnings": agg_res.warnings,
            }

            # Add USD display if reporting is CNY
            if reporting_currency == "CNY":
                usd_sub = agg_res.by_original_currency.get("USD")
                if usd_sub:
                    summary["usd_total"] = float(usd_sub.amount_original)

            return success(summary)

        except Exception as exc:
            _log.exception("Error generating my money summary")
            return failure(str(exc), error_code="INTERNAL_ERROR")


    def _build_position_rows(
        self, latest_batch: Dict[str, Any], valuations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        products = {
            p["product_id"]: p
            for p in (latest_batch.get("products") or [])
            if p.get("product_id")
        }
        if not products:
            product_ids = {v["product_id"] for v in valuations}
            products = {}
            for product_id in product_ids:
                product = self._db.get_product(product_id)
                if product:
                    products[product_id] = product.to_dict()

        rows = []
        for v in valuations:
            product = products.get(v["product_id"], {})
            quantity = v.get("quantity")
            amount = v.get("amount")
            unit_price = None
            if quantity not in (None, 0) and amount is not None:
                try:
                    unit_price = float(amount) / float(quantity)
                except (TypeError, ValueError, ZeroDivisionError):
                    unit_price = None
            rows.append({
                "account_id": v.get("account_id"),
                "product_id": v.get("product_id"),
                "name": product.get("name") or v.get("product_id"),
                "product_type": product.get("product_type") or "unknown",
                "issuer": product.get("issuer") or "",
                "quantity": quantity,
                "unit_price": unit_price,
                "market_value": amount,
                "currency": v.get("currency"),
                "valuation_date": v.get("valuation_date"),
                "source_type": v.get("source_type"),
                "source_id": v.get("source_id"),
                "quality": v.get("quality"),
                "freshness": v.get("freshness"),
                "is_estimate": v.get("is_estimate"),
                "age_days": v.get("age_days"),
                "warnings": v.get("warnings") or [],
            })
        return rows

    def _get_fx_quotes(self, currencies: set[str], reporting: str, as_of: date) -> List[FxQuote]:
        quotes = []
        for curr in currencies:
            if curr == reporting:
                continue
            try:
                # Try to get rate from provider
                rate = self._data_provider.fx_rate(curr, reporting, date_str=as_of.isoformat())
                if rate:
                    quotes.append(FxQuote(
                        base=curr,
                        quote=reporting,
                        rate=Decimal(str(rate)),
                        as_of=as_of,
                        source="DataProvider",
                        quality=ValuationQuality.REPORTED
                    ))
            except Exception:
                _log.debug("Failed to get FX rate for %s/%s", curr, reporting)
        return quotes

    def _perform_reconciliation(
        self, prev_batch, prev_vals, curr_batch, curr_vals,
        reporting_currency, fx_quotes
    ) -> tuple[Optional[Dict[str, Any]], str, str]:

        # 1. Convert both batches to reporting currency
        # We need a map of rates
        rate_map = {f"{q.base}/{q.quote}": q.rate for q in fx_quotes}
        rate_map[f"{reporting_currency}/{reporting_currency}"] = Decimal("1")

        def convert_positions(vals, as_of_date):
            converted = []
            for v in vals:
                rate = rate_map.get(f"{v['currency']}/{reporting_currency}")
                if rate is None:
                    # Try inverse
                    inv_rate = rate_map.get(f"{reporting_currency}/{v['currency']}")
                    if inv_rate:
                        rate = Decimal("1") / inv_rate

                mkt_val = None
                if v["amount"] is not None and rate is not None:
                    mkt_val = Decimal(str(v["amount"])) * rate

                converted.append(PositionInput(
                    account_id=v["account_id"],
                    product_id=v["product_id"],
                    currency=reporting_currency,
                    market_value=mkt_val,
                    quantity=Decimal(str(v["quantity"])) if v.get("quantity") is not None else None,
                ))
            return converted

        prev_pos = convert_positions(prev_vals, date.fromisoformat(prev_batch["as_of"]))
        curr_pos = convert_positions(curr_vals, date.fromisoformat(curr_batch["as_of"]))

        # 2. Get cashflows
        cf_rows = self._db.get_cashflows_for_period(prev_batch["as_of"], curr_batch["as_of"])
        cashflows = []
        for row in cf_rows:
            # Convert cashflow to reporting currency
            amt = Decimal(str(row["amount"]))
            rate = rate_map.get(f"{row['currency']}/{reporting_currency}")
            if rate is None:
                 inv_rate = rate_map.get(f"{reporting_currency}/{row['currency']}")
                 if inv_rate:
                     rate = Decimal("1") / inv_rate

            if rate:
                cashflows.append(CashflowInput(
                    event_id=row["event_id"],
                    event_type=row["event_type"],
                    account_id=row["account_id"],
                    amount=amt * rate,
                    currency=reporting_currency,
                    effective_date=date.fromisoformat(row["effective_date"]),
                    counter_amount=Decimal(str(row["counter_amount"])) * rate if row["counter_amount"] and rate else None,
                    counter_currency=reporting_currency if row["counter_currency"] else None,
                ))
            else:
                _log.warning("Skipping cashflow %s due to missing FX rate", row["event_id"])

        # 3. Prepare inputs
        def to_cov(c):
            return CoverageLevel(c) if c in [e.value for e in CoverageLevel] else CoverageLevel.UNKNOWN

        prev_input = SnapshotInput(
            batch_id=prev_batch["batch_id"],
            as_of=date.fromisoformat(prev_batch["as_of"]),
            status=prev_batch["status"],
            account_coverage={c["account_id"]: to_cov(c["coverage"]) for c in prev_batch["account_coverage"]},
            positions=prev_pos,
            cashflow_coverage=CoverageLevel.COMPLETE # Assume complete for now or check DB
        )
        curr_input = SnapshotInput(
            batch_id=curr_batch["batch_id"],
            as_of=date.fromisoformat(curr_batch["as_of"]),
            status=curr_batch["status"],
            account_coverage={c["account_id"]: to_cov(c["coverage"]) for c in curr_batch["account_coverage"]},
            positions=curr_pos,
            cashflow_coverage=CoverageLevel.COMPLETE
        )

        # 4. Reconcile
        try:
            req = ReconciliationRequest(previous=prev_input, current=curr_input, cashflows=cashflows)
            res = reconcile_snapshots(req)

            return_status = "available" if res.is_return_eligible else "estimated"
            if not res.is_return_eligible:
                return_reason = "Insufficient coverage for return calculation."
            else:
                return_reason = "Success"

            return res.to_dict(), return_status, return_reason
        except Exception as exc:
            _log.warning(
                "Reconciliation computation error "
                "(prev_batch=%s as_of=%s, curr_batch=%s as_of=%s, "
                "currency=%s): %s",
                prev_batch.get("batch_id"), prev_batch.get("as_of"),
                curr_batch.get("batch_id"), curr_batch.get("as_of"),
                reporting_currency, exc,
            )
            return None, "unavailable", "Reconciliation computation error"
