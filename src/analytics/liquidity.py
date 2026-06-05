"""Liquidity risk analysis for portfolio positions.

Groups every position and cash holding into a liquidity bucket based on
product type, symbol pattern, and lockup metadata, then computes the
percentage of portfolio value available within 7 days and locked long-term.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from src.domain import CashHolding, PositionValue, ProductDefinition


# ── Bucket ordering ─────────────────────────────────────────────────────────

BUCKET_ORDER = [
    "T+0",
    "T+1",
    "T+2~T+4",
    "7天内",
    "1个月内",
    "3个月内",
    "1年内",
    "锁仓",
]

_AVAILABLE_7D_BUCKETS = {"T+0", "T+1", "T+2~T+4", "7天内"}


# ── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LiquidityBucket:
    """A single liquidity bucket aggregating one or more positions.

    Attributes:
        name: Human-readable label (e.g. "T+0", "T+1", "7天内").
        value: Total market value in base currency assigned to this bucket.
        pct: Percentage of total portfolio value (0–100).
        asset_ids: Asset IDs that fall into this bucket.
    """

    name: str
    value: float
    pct: float
    asset_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiquidityReport:
    """Liquidity risk report for a portfolio snapshot.

    Attributes:
        as_of: Valuation date.
        total_value: Total portfolio value in base currency.
        buckets: Ordered liquidity buckets with aggregated values.
        available_7d_pct: Percentage of portfolio available within 7 days.
        locked_pct: Percentage of portfolio in locked/long-term buckets.
    """

    as_of: date
    total_value: float
    buckets: List[LiquidityBucket]
    available_7d_pct: float
    locked_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(),
            "total_value": self.total_value,
            "buckets": [b.to_dict() for b in self.buckets],
            "available_7d_pct": round(self.available_7d_pct, 2),
            "locked_pct": round(self.locked_pct, 2),
        }


# ── Analyzer ────────────────────────────────────────────────────────────────


class LiquidityAnalyzer:
    """Classify portfolio positions into liquidity buckets.

    Usage::

        analyzer = LiquidityAnalyzer()
        report = analyzer.analyze(
            positions=valuation_result.positions,
            product_registry=registry,
            total_value=valuation_result.total_value,
            cash_breakdown=valuation_result.cash_breakdown,
        )
    """

    def analyze(
        self,
        positions: Dict[str, PositionValue],
        product_registry: Dict[str, ProductDefinition],
        total_value: float,
        as_of: date,
        cash_breakdown: Optional[Dict[str, CashHolding]] = None,
    ) -> LiquidityReport:
        """Classify every position and cash holding into a liquidity bucket.

        Args:
            positions: {asset_id: PositionValue} from ValuationEngine.
            product_registry: {asset_id: ProductDefinition} lookup.
            total_value: Total portfolio value in base currency (must be > 0).
            as_of: Valuation date for the report.
            cash_breakdown: {currency: CashHolding} from ValuationResult
                            (aggregated as "T+0").

        Returns:
            LiquidityReport with ordered buckets and aggregate metrics.
        """
        self._warnings: List[str] = []

        bucket_values: Dict[str, float] = {name: 0.0 for name in BUCKET_ORDER}
        bucket_asset_ids: Dict[str, List[str]] = {name: [] for name in BUCKET_ORDER}

        # ── Cash is always T+0 ────────────────────────────────────────────
        if cash_breakdown:
            cash_total = sum(ch.value_base for ch in cash_breakdown.values())
            if cash_total > 0:
                bucket_values["T+0"] += cash_total
                bucket_asset_ids["T+0"].append("CASH")

        # ── Classify each position ────────────────────────────────────────
        for asset_id, pos in positions.items():
            product = product_registry.get(asset_id)
            bucket = self._classify(asset_id, product, as_of)
            if bucket not in bucket_values:
                bucket = "7天内"
            bucket_values[bucket] += pos.value_base
            bucket_asset_ids[bucket].append(asset_id)

        # ── Build bucket list (preserving order) ──────────────────────────
        buckets: List[LiquidityBucket] = []
        for name in BUCKET_ORDER:
            value = bucket_values[name]
            pct = (value / total_value * 100) if total_value > 0 else 0.0
            buckets.append(
                LiquidityBucket(
                    name=name,
                    value=value,
                    pct=round(pct, 2),
                    asset_ids=sorted(bucket_asset_ids[name]),
                )
            )

        # ── Aggregate metrics ─────────────────────────────────────────────
        available_7d = sum(
            bucket_values[name] for name in _AVAILABLE_7D_BUCKETS
        )
        available_7d_pct = (
            (available_7d / total_value * 100) if total_value > 0 else 0.0
        )
        locked_pct = (
            (bucket_values["锁仓"] / total_value * 100) if total_value > 0 else 0.0
        )

        return LiquidityReport(
            as_of=as_of,
            total_value=total_value,
            buckets=buckets,
            available_7d_pct=round(available_7d_pct, 2),
            locked_pct=round(locked_pct, 2),
        )

    # ── Classification heuristics ────────────────────────────────────────────

    def _classify(
        self,
        asset_id: str,
        product: Optional[ProductDefinition],
        as_of: date,
    ) -> str:
        """Map a single asset to a liquidity bucket name.

        Priority (first match wins):
        1. Product registry (product_type and metadata).
        2. Symbol pattern heuristics (A-share / US stock).
        3. Default fallback (7天内).
        """
        # Cash pseudo-positions
        if asset_id.upper() in ("CASH", "CNY_CASH", "USD_CASH", "CASH_BALANCE"):
            return "T+0"

        if product is not None:
            ptype = product.product_type or ""
            pname = product.name or ""

            # Money market fund → T+1
            if ptype == "money_fund" or "货币" in pname:
                return "T+1"

            # Open-end funds → T+2~T+4
            if ptype in (
                "mixed_fund",
                "bond_fund",
                "equity_fund",
                "stock_fund",
                "index_fund",
                "etf_fund",
                "balanced_fund",
                "qdii_fund",
            ):
                return "T+2~T+4"

            # Bank WMP → inspect lockup / liquidity_type
            if ptype == "bank_wmp":
                return self._classify_bank_wmp(product, as_of)

            # Deposit → distinguish demand vs time by maturity/term
            if ptype == "deposit":
                return self._classify_deposit(product, as_of)

            # Structured deposit → check liquidity_type, fallback 1 month
            if ptype in ("structured_deposit", "structured_note"):
                return self._classify_bank_wmp(product, as_of)

        # ── Symbol pattern heuristics ─────────────────────────────────────
        return self._classify_by_symbol(asset_id)

    def _classify_by_symbol(self, asset_id: str) -> str:
        """Classify by symbol pattern when no product metadata is available."""
        sym = asset_id.strip()

        # A-share: sh600519, sz000001, or bare 6-digit numeric
        if re.match(r"^(sh|sz|SH|SZ)\d{6}$", sym):
            return "T+1"
        if re.match(r"^\d{6}$", sym):
            return "T+1"

        # US / global stock: letters, optional dot (e.g. BRK.B), optional dash
        if re.match(r"^[A-Za-z]+(\.[A-Za-z]+)?$", sym):
            return "T+1"

        # Fallback
        return "7天内"

    @staticmethod
    def _classify_bank_wmp(product: ProductDefinition, as_of: date) -> str:
        """Classify a bank WMP or structured product by lockup / liquidity_type."""
        lockup = product.metadata.get("lockup_end_date") if product.metadata else None

        if lockup:
            if isinstance(lockup, str):
                try:
                    lockup = datetime.fromisoformat(lockup).date()
                except (ValueError, TypeError):
                    pass

            if isinstance(lockup, date):
                days = (lockup - as_of).days
                if days <= 0:
                    return "T+0"
                if days <= 30:
                    return "1个月内"
                if days <= 90:
                    return "3个月内"
                if days <= 365:
                    return "1年内"
                return "锁仓"

        # Fallback: liquidity_type string
        if product.liquidity_type:
            lt = product.liquidity_type.lower()
            if "t+0" in lt:
                return "T+0"
            if "t+1" in lt:
                return "T+1"
            if "month" in lt or "月" in lt:
                return "1个月内"

        # Default for bank WMP / structured products
        return "1个月内"

    def _classify_deposit(self, product: ProductDefinition, as_of: date) -> str:
        """Classify a deposit as demand (T+0) or time (maturity-based bucket).

        Checks metadata for maturity_date, lockup_end_date, or term (days).
        If unable to determine whether a deposit is demand or time, assumes
        T+0 and records a warning in ``self._warnings``.
        """
        metadata = product.metadata if product.metadata else {}

        # Check for a maturity / lockup end date
        lockup = metadata.get("maturity_date") or metadata.get("lockup_end_date")
        if lockup:
            if isinstance(lockup, str):
                try:
                    lockup = datetime.fromisoformat(lockup).date()
                except (ValueError, TypeError):
                    lockup = None

            if isinstance(lockup, date):
                days = (lockup - as_of).days
                if days <= 0:
                    return "T+0"
                if days <= 7:
                    return "7天内"
                if days <= 30:
                    return "1个月内"
                if days <= 90:
                    return "3个月内"
                if days <= 365:
                    return "1年内"
                return "锁仓"

        # Check for a term (in days)
        term = metadata.get("term")
        if term is not None:
            try:
                term_days = int(term)
            except (ValueError, TypeError):
                term_days = 0

            if term_days <= 0:
                return "T+0"
            if term_days <= 7:
                return "7天内"
            if term_days <= 30:
                return "1个月内"
            if term_days <= 90:
                return "3个月内"
            if term_days <= 365:
                return "1年内"
            return "锁仓"

        # Unable to determine if demand or time — assume T+0 and warn
        self._warnings.append(
            f"Deposit {product.product_id}: unable to determine if demand/time, assuming T+0"
        )
        return "T+0"
