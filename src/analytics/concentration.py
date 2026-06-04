"""Concentration risk analyzer for portfolio positions.

Computes concentration breakdowns by currency, asset class, and issuer,
with threshold-based warnings for single-point-of-failure risks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from src.domain import PositionValue


# ── Thresholds ────────────────────────────────────────────────────────────

_SINGLE_CURRENCY_PCT = 0.80
_SINGLE_ISSUER_PCT = 0.30
_EQUITY_PCT = 0.70


# ── Asset class mapping ───────────────────────────────────────────────────


def _map_asset_class(asset_type: str) -> str:
    """Map asset_type strings from the registry to concentration asset classes."""
    t = (asset_type or "").strip().lower()
    if not t:
        return "unknown"

    # Direct matches
    if t in ("cash", "currency", "money_market", "deposit"):
        return "cash"
    if t in ("equity", "us_equity", "hk_equity", "cn_stock", "cn_stock_sh", "cn_stock_sz"):
        return "equity"
    if t in ("fund", "etf", "mutual_fund", "index_fund", "bond_fund", "mixed_fund", "money_market_fund"):
        return "fund"
    if t in ("bond", "government_bond", "corporate_bond", "convertible_bond"):
        return "bond"
    if "bank" in t or "wmp" in t:
        return "bank_wmp"
    if "commodity" in t or "gold" in t or "metal" in t:
        return "commodity"
    if "reit" in t or "real_estate" in t:
        return "real_estate"
    if "crypto" in t:
        return "crypto"

    # Heuristic fallback
    if "stock" in t or "equity" in t:
        return "equity"
    if "fund" in t or "etf" in t:
        return "fund"
    if "bond" in t:
        return "bond"

    return "other"


# ── Dataclasses ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ConcentrationItem:
    """A single entry in a concentration breakdown.

    Attributes:
        dimension: Grouping axis (e.g. "currency", "asset_class", "issuer").
        key: Group value (e.g. "USD", "equity", "Apple Inc.").
        value: Market value in base currency.
        pct: Percentage of total portfolio value (0–100).
        asset_ids: Asset IDs that belong to this group.
    """

    dimension: str
    key: str
    value: float
    pct: float
    asset_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConcentrationReport:
    """Concentration risk report for a portfolio snapshot.

    Attributes:
        as_of: Valuation date.
        total_value: Total portfolio value in base currency.
        by_currency: Breakdown by denomination currency.
        by_asset_class: Breakdown by mapped asset class.
        by_issuer: Breakdown by issuer/manager name.
        warnings: Human-readable threshold breach messages in Chinese.
    """

    as_of: date
    total_value: float
    by_currency: List[ConcentrationItem] = field(default_factory=list)
    by_asset_class: List[ConcentrationItem] = field(default_factory=list)
    by_issuer: List[ConcentrationItem] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(),
            "total_value": self.total_value,
            "by_currency": [item.to_dict() for item in self.by_currency],
            "by_asset_class": [item.to_dict() for item in self.by_asset_class],
            "by_issuer": [item.to_dict() for item in self.by_issuer],
            "warnings": list(self.warnings),
        }


# ── Analyzer ──────────────────────────────────────────────────────────────


class ConcentrationAnalyzer:
    """Compute concentration risk across currency, asset class, and issuer."""

    def analyze(
        self,
        positions: Dict[str, PositionValue],
        asset_meta: Dict[str, Dict[str, Any]],
        as_of: date,
    ) -> ConcentrationReport:
        """Analyze concentration from a set of valued positions.

        Args:
            positions: {asset_id: PositionValue} from ValuationEngine.
            asset_meta: {asset_id: {name, asset_type, currency, issuer, manager, ...}}
                        Loaded from config/asset_registry.yaml.
            as_of: Valuation date for the report.

        Returns:
            ConcentrationReport with three breakdown axes and threshold warnings.
        """
        if not positions:
            return ConcentrationReport(
                as_of=as_of,
                total_value=0.0,
            )

        total_value = sum(p.value_base for p in positions.values())
        if total_value <= 0:
            return ConcentrationReport(
                as_of=as_of,
                total_value=0.0,
            )

        # ── Currency breakdown ──────────────────────────────────────────
        currency_buckets: Dict[str, Dict[str, Any]] = {}
        for asset_id, pos in positions.items():
            cur = pos.currency or "unknown"
            if cur not in currency_buckets:
                currency_buckets[cur] = {"value": 0.0, "asset_ids": []}
            currency_buckets[cur]["value"] += pos.value_base
            currency_buckets[cur]["asset_ids"].append(asset_id)

        by_currency = sorted(
            [
                ConcentrationItem(
                    dimension="currency",
                    key=cur,
                    value=bucket["value"],
                    pct=round(bucket["value"] / total_value * 100, 2),
                    asset_ids=bucket["asset_ids"],
                )
                for cur, bucket in currency_buckets.items()
            ],
            key=lambda x: x.value,
            reverse=True,
        )

        # ── Asset class breakdown ───────────────────────────────────────
        class_buckets: Dict[str, Dict[str, Any]] = {}
        for asset_id, pos in positions.items():
            meta = asset_meta.get(asset_id, {})
            asset_type = meta.get("asset_type", "")
            asset_class = _map_asset_class(asset_type)
            if asset_class not in class_buckets:
                class_buckets[asset_class] = {"value": 0.0, "asset_ids": []}
            class_buckets[asset_class]["value"] += pos.value_base
            class_buckets[asset_class]["asset_ids"].append(asset_id)

        by_asset_class = sorted(
            [
                ConcentrationItem(
                    dimension="asset_class",
                    key=cls,
                    value=bucket["value"],
                    pct=round(bucket["value"] / total_value * 100, 2),
                    asset_ids=bucket["asset_ids"],
                )
                for cls, bucket in class_buckets.items()
            ],
            key=lambda x: x.value,
            reverse=True,
        )

        # ── Issuer breakdown ────────────────────────────────────────────
        issuer_buckets: Dict[str, Dict[str, Any]] = {}
        for asset_id, pos in positions.items():
            meta = asset_meta.get(asset_id, {})
            issuer = meta.get("issuer") or meta.get("manager") or meta.get("name") or asset_id
            if issuer not in issuer_buckets:
                issuer_buckets[issuer] = {"value": 0.0, "asset_ids": []}
            issuer_buckets[issuer]["value"] += pos.value_base
            issuer_buckets[issuer]["asset_ids"].append(asset_id)

        by_issuer = sorted(
            [
                ConcentrationItem(
                    dimension="issuer",
                    key=issuer,
                    value=bucket["value"],
                    pct=round(bucket["value"] / total_value * 100, 2),
                    asset_ids=bucket["asset_ids"],
                )
                for issuer, bucket in issuer_buckets.items()
            ],
            key=lambda x: x.value,
            reverse=True,
        )

        # ── Warnings ────────────────────────────────────────────────────
        warnings: List[str] = []

        # Single currency > 80%
        for item in by_currency:
            if item.pct > _SINGLE_CURRENCY_PCT * 100:
                warnings.append(
                    f"单一币种 {item.key} 占比 {item.pct:.1f}%，超过 {_SINGLE_CURRENCY_PCT * 100:.0f}% 阈值"
                )

        # Single issuer > 30%
        for item in by_issuer:
            if item.pct > _SINGLE_ISSUER_PCT * 100:
                warnings.append(
                    f"单一发行方 {item.key} 占比 {item.pct:.1f}%，超过 {_SINGLE_ISSUER_PCT * 100:.0f}% 阈值"
                )

        # Equity > 70%
        for item in by_asset_class:
            if item.key == "equity" and item.pct > _EQUITY_PCT * 100:
                warnings.append(
                    f"权益类资产占比 {item.pct:.1f}%，超过 {_EQUITY_PCT * 100:.0f}% 阈值"
                )

        return ConcentrationReport(
            as_of=as_of,
            total_value=total_value,
            by_currency=by_currency,
            by_asset_class=by_asset_class,
            by_issuer=by_issuer,
            warnings=warnings,
        )
