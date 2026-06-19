"""Permanent loss and liquidity risk analysis.

Classifies risk into four independent dimensions:
1. Market Volatility (price fluctuations)
2. Liquidity Restriction (access speed)
3. Permanent Loss (credit/structural risk)
4. Data Unknown (completeness/freshness)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from src.domain import PositionValue, ProductDefinition


@dataclass(frozen=True)
class RiskDimension:
    """Risk assessment for a single dimension."""
    level: str  # low | medium | high | unknown
    evidence: str
    rule_id: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PositionRiskEntry:
    """Risk profile for a single position."""
    asset_id: str
    name: str
    value_base: float
    market_volatility: RiskDimension
    liquidity_restriction: RiskDimension
    permanent_loss: RiskDimension
    data_unknown: RiskDimension
    as_of: date

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "value_base": self.value_base,
            "market_volatility": self.market_volatility.to_dict(),
            "liquidity_restriction": self.liquidity_restriction.to_dict(),
            "permanent_loss": self.permanent_loss.to_dict(),
            "data_unknown": self.data_unknown.to_dict(),
            "as_of": self.as_of.isoformat(),
        }


@dataclass(frozen=True)
class RiskSummaryItem:
    """Aggregated risk value for a specific level in a dimension."""
    level: str
    value: float
    pct: float


@dataclass(frozen=True)
class PermanentLossReport:
    """Portfolio-wide risk report."""
    as_of: date
    total_value: float
    unknown_value: float  # Value of assets with 'unknown' in ANY dimension
    positions: List[PositionRiskEntry]
    summary: Dict[str, List[RiskSummaryItem]]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(),
            "total_value": self.total_value,
            "unknown_value": self.unknown_value,
            "positions": [p.to_dict() for p in self.positions],
            "summary": {
                dim: [item.__dict__ for item in items]
                for dim, items in self.summary.items()
            },
            "warnings": self.warnings,
        }


class PermanentLossAnalyzer:
    """Analyzes portfolio for permanent loss and liquidity risks."""

    def analyze(
        self,
        positions: Dict[str, PositionValue],
        product_registry: Dict[str, ProductDefinition],
        liquidity_report: Any,  # LiquidityReport
        as_of: date,
    ) -> PermanentLossReport:
        """Analyze risks for all positions."""
        total_value = sum(p.value_base for p in positions.values())

        # Map liquidity buckets to positions for easier lookup
        liq_map = {}
        if liquidity_report:
            for bucket in liquidity_report.buckets:
                for asset_id in bucket.asset_ids:
                    liq_map[asset_id] = bucket.name

        risk_entries = []
        warnings = []
        for asset_id, pos in positions.items():
            product = product_registry.get(asset_id)
            liq_bucket = liq_map.get(asset_id, "未知")

            entry = self._analyze_position(asset_id, pos, product, liq_bucket, as_of)
            risk_entries.append(entry)

            # Collect warnings from entries with unknown/high risk
            if entry.data_unknown.level == "unknown":
                warnings.append(f"资产 {entry.name} ({asset_id}) 数据不全: {entry.data_unknown.evidence}")
            if entry.permanent_loss.level == "high":
                warnings.append(f"资产 {entry.name} ({asset_id}) 永久损失风险高: {entry.permanent_loss.evidence}")

        # Calculate summary
        summary = self._calculate_summary(risk_entries, total_value)

        # unknown_value is assets where ANY dimension is 'unknown'
        unknown_value = sum(
            p.value_base for p in risk_entries
            if any(d.level == "unknown" for d in [
                p.market_volatility, p.liquidity_restriction,
                p.permanent_loss, p.data_unknown
            ])
        )

        return PermanentLossReport(
            as_of=as_of,
            total_value=total_value,
            unknown_value=unknown_value,
            positions=risk_entries,
            summary=summary,
            warnings=list(set(warnings)), # Deduplicate
        )

    def _analyze_position(
        self,
        asset_id: str,
        pos: PositionValue,
        product: Optional[ProductDefinition],
        liq_bucket: str,
        as_of: date,
    ) -> PositionRiskEntry:
        name = product.name if product else asset_id

        # 1. Data Unknown
        data_unknown = self._eval_data_unknown(asset_id, product)

        # 2. Liquidity Restriction
        liquidity_restriction = self._eval_liquidity(asset_id, product, liq_bucket)

        # 3. Market Volatility
        market_volatility = self._eval_volatility(asset_id, product)

        # 4. Permanent Loss
        permanent_loss = self._eval_permanent_loss(asset_id, product)

        return PositionRiskEntry(
            asset_id=asset_id,
            name=name,
            value_base=pos.value_base,
            market_volatility=market_volatility,
            liquidity_restriction=liquidity_restriction,
            permanent_loss=permanent_loss,
            data_unknown=data_unknown,
            as_of=as_of,
        )

    def _eval_data_unknown(self, asset_id: str, product: Optional[ProductDefinition]) -> RiskDimension:
        if not product:
            return RiskDimension("unknown", "缺少产品基本条款信息", "data_missing")

        # Check for essential metadata
        # Some legacy products might have empty product_type but we treat them as low unknown data
        # if the product object exists at all, unless truly critical fields are missing.
        return RiskDimension("low", "产品条款基本完整", "data_complete")

    def _eval_liquidity(self, asset_id: str, product: Optional[ProductDefinition], liq_bucket: str) -> RiskDimension:
        if liq_bucket == "未知":
            return RiskDimension("unknown", "流动性条款未知", "liq_unknown")

        if liq_bucket in ("T+0", "T+1"):
            return RiskDimension("low", f"变现极快 ({liq_bucket})", "liq_fast")

        if liq_bucket in ("T+2~T+4", "7天内", "1个月内"):
            return RiskDimension("medium", f"变现需一定时间 ({liq_bucket})", "liq_medium")

        return RiskDimension("high", f"变现受限或需长期持有 ({liq_bucket})", "liq_locked")

    def _eval_volatility(self, asset_id: str, product: Optional[ProductDefinition]) -> RiskDimension:
        if not product:
            return RiskDimension("unknown", "未知资产波动性", "vol_unknown")

        ptype = product.product_type or ""
        pname = product.name or ""

        if ptype in ("cash", "deposit", "money_fund") or "货币" in pname:
            return RiskDimension("low", "极低价格波动", "vol_low")

        if "bond" in ptype or ptype == "fixed_income":
            # US Treasury special mention
            if "UST" in asset_id or "Treasury" in pname:
                return RiskDimension("medium", "美债正常久期波动", "vol_medium")
            return RiskDimension("medium", "债券类正常价格波动", "vol_medium")

        if ptype in ("equity", "stock", "equity_fund", "index_fund", "etf_fund", "stock_fund"):
            return RiskDimension("high", "权益类资产正常价格波动", "vol_high")

        if ptype == "mixed_fund":
            return RiskDimension("high", "混合基金价格波动较高", "vol_high")

        return RiskDimension("medium", "一般市场波动", "vol_default")

    def _eval_permanent_loss(self, asset_id: str, product: Optional[ProductDefinition]) -> RiskDimension:
        if not product:
            return RiskDimension("unknown", "产品结构未知，无法评估永久损失风险", "pl_unknown")

        # UST special case (US Sovereign credit = Low permanent loss risk)
        pname = product.name or ""
        if "UST" in asset_id or "Treasury" in pname:
            return RiskDimension("low", "主权信用风险极低", "pl_sovereign")

        ptype = product.product_type or ""
        metadata = product.metadata or {}

        # Principal guarantee check - IMPORTANT: do not default to True if unknown
        guaranteed = metadata.get("principal_guaranteed")

        if guaranteed is False:
            return RiskDimension("high", "非保本产品，存在本金损失风险", "pl_no_guarantee")

        if ptype in ("cash", "deposit"):
            return RiskDimension("low", "无本金损失风险（受存款保险保障/主权信用）", "pl_safe")

        if ptype == "money_fund":
            return RiskDimension("low", "底层资产稳健，永久损失风险极低", "pl_low")

        if ptype in ("equity", "stock"):
            # Equities have inherent risk of company failure
            return RiskDimension("medium", "底层公司经营风险可能导致权益归零", "pl_equity")

        if ptype in ("bank_wmp", "structured_deposit", "trust"):
            if guaranteed is None:
                return RiskDimension("unknown", "理财/结构化产品保本条款不明", "pl_unknown_guarantee")
            return RiskDimension("medium", "结构化理财产品信用与合规风险", "pl_structured")

        if "bond" in ptype:
            return RiskDimension("medium", "存在发行人违约风险", "pl_credit")

        return RiskDimension("unknown", "无法确定该产品类型的永久损失风险", "pl_type_unknown")

    def _calculate_summary(self, entries: List[PositionRiskEntry], total_value: float) -> Dict[str, List[RiskSummaryItem]]:
        dimensions = ["market_volatility", "liquidity_restriction", "permanent_loss", "data_unknown"]
        levels = ["low", "medium", "high", "unknown"]

        summary = {}
        for dim in dimensions:
            dim_summary = []
            for level in levels:
                val = sum(e.value_base for e in entries if getattr(e, dim).level == level)
                pct = (val / total_value) if total_value > 0 else 0.0
                dim_summary.append(RiskSummaryItem(level, val, round(pct, 4)))
            summary[dim] = dim_summary

        return summary
