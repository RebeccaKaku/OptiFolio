"""Service for valuing portfolio book batches and positions.

This service coordinates candidate gathering from the personal database
and the public market data layer (FinData).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd

from optifolio_contracts.quality import ValuationQuality
from src.core.book_valuation import (
    ValuationCandidate,
    ValuationEngine,
    ValuationResult,
)
from src.core.portfolio_book_db import PortfolioBookDatabase
from src.services.response import success, failure

_log = logging.getLogger(__name__)


class BookValuationService:
    """Orchestrates valuation for snapshot batches."""

    def __init__(self, db: PortfolioBookDatabase, data_provider: Any) -> None:
        self._db = db
        self._data_provider = data_provider

    def value_batch(self, batch_id: str) -> Dict[str, Any]:
        """Value all positions in a batch, returning source-tagged results."""
        try:
            batch = self._db.get_batch(batch_id)
            if not batch:
                return failure(f"Batch {batch_id} not found", error_code="NOT_FOUND")

            as_of = pd.Timestamp(batch["as_of"]).date()

            # Fetch product info for all products in batch to know freshness thresholds
            product_ids = {pos["product_id"] for pos in batch["snapshots"]}
            products = {pid: self._db.get_product(pid) for pid in product_ids}

            # TODO: Define thresholds based on product type if needed
            thresholds = {"default": 3}

            results = []
            for pos in batch["snapshots"]:
                candidates = self._gather_candidates(pos, as_of, products.get(pos["product_id"]))

                # target_currency is the currency recorded in the position snapshot
                target_currency = pos.get("currency", "CNY")

                val_result = ValuationEngine.select_best(
                    candidates,
                    as_of,
                    target_currency=target_currency,
                    freshness_thresholds=thresholds
                )

                res_dict = self._serialize_result(pos, val_result)
                results.append(res_dict)

            return success({
                "batch_id": batch_id,
                "as_of": batch["as_of"],
                "valuations": results
            })

        except Exception as exc:
            _log.exception("Error valuing batch %s", batch_id)
            return failure(str(exc), error_code="INTERNAL_ERROR")

    def _gather_candidates(
        self,
        pos: Dict[str, Any],
        as_of: date,
        product: Optional[Any]
    ) -> List[ValuationCandidate]:
        """Gather all potential valuation candidates for a position."""
        candidates = []
        product_id = pos["product_id"]
        account_id = pos["account_id"]

        # 1. Manual candidate from current snapshot
        if pos.get("market_value") is not None:
            # If the batch status is 'confirmed', we treat this as confirmed.
            # Wait, better to look at the snapshot quality field.
            quality_str = pos.get("quality") or "reported"
            quality = ValuationQuality.CONFIRMED if quality_str == "confirmed" else ValuationQuality.REPORTED

            candidates.append(ValuationCandidate(
                amount=pos["market_value"],
                currency=pos.get("currency", "CNY"),
                effective_date=as_of,
                source_id=pos["batch_id"],
                source_type="manual",
                quality=quality
            ))

        # 2. Public candidate (NAV/Price * Quantity)
        if pos.get("quantity") is not None and product and product.data_source != "manual":
            # Attempt to fetch price from DataProvider
            # We use the product_id as the symbol
            try:
                # Get price on or before as_of
                price_series = self._data_provider.prices(product_id, end=as_of.isoformat())
                if price_series is not None and not price_series.empty:
                    latest_price = float(price_series.iloc[-1])
                    price_date = price_series.index[-1].date()

                    candidates.append(ValuationCandidate(
                        price=latest_price,
                        quantity=pos["quantity"],
                        currency=product.currency, # Product definition currency
                        effective_date=price_date,
                        source_id=product_id,
                        source_type="public",
                        quality=ValuationQuality.REPORTED # Public prices are reported
                    ))
            except Exception:
                _log.debug("Failed to fetch public price for %s", product_id)

        # 3. Last known manual values (Historical)
        # We need to query the database for previous confirmed snapshots
        historical = self._get_historical_manual_values(product_id, account_id, as_of)
        for h in historical:
            candidates.append(ValuationCandidate(
                amount=h["market_value"],
                currency=h["currency"],
                effective_date=h["as_of"],
                source_id=h["batch_id"],
                source_type="manual",
                quality=ValuationQuality.CONFIRMED if h["quality"] == "confirmed" else ValuationQuality.REPORTED
            ))

        return candidates

    def _get_historical_manual_values(self, product_id: str, account_id: str, before_date: date) -> List[Dict[str, Any]]:
        """Query DB for previous manual valuations of this position."""
        sql = """
            SELECT ps.market_value, ps.currency, sb.as_of, sb.batch_id, ps.quality
            FROM position_snapshots ps
            JOIN snapshot_batches sb ON ps.batch_id = sb.batch_id
            WHERE ps.product_id = ? AND ps.account_id = ?
              AND sb.as_of < ? AND sb.status = 'confirmed'
              AND ps.market_value IS NOT NULL
            ORDER BY sb.as_of DESC, sb.created_at DESC
            LIMIT 5
        """
        results = []
        conn = self._db.connect()
        try:
            rows = conn.execute(sql, (product_id, account_id, before_date.isoformat())).fetchall()
            for row in rows:
                results.append({
                    "market_value": row["market_value"],
                    "currency": row["currency"],
                    "as_of": pd.Timestamp(row["as_of"]).date(),
                    "batch_id": row["batch_id"],
                    "quality": row["quality"]
                })
        finally:
            conn.close()
        return results

    def _serialize_result(self, pos: Dict[str, Any], res: ValuationResult) -> Dict[str, Any]:
        """Convert ValuationResult to a dict suitable for API response."""
        return {
            "account_id": pos["account_id"],
            "product_id": pos["product_id"],
            "amount": res.amount,
            "currency": res.currency,
            "valuation_date": res.valuation_date.isoformat() if res.valuation_date else None,
            "known_at": res.known_at.isoformat() if res.known_at else None,
            "source_type": res.source_type,
            "source_id": res.source_id,
            "quality": res.quality.value,
            "freshness": res.freshness.value,
            "is_estimate": res.is_estimate,
            "age_days": res.age_days,
            "warnings": res.warnings
        }
