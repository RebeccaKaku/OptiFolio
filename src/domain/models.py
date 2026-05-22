"""Framework-independent portfolio domain objects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Universe:
    asset_ids: Tuple[str, ...]
    base_currency: str = "USD"
    name: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["asset_ids"] = list(self.asset_ids)
        return data


@dataclass(frozen=True)
class Holding:
    asset_id: str
    quantity: float
    currency: str = "USD"
    market_value: Optional[float] = None
    cost_basis: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioSnapshot:
    as_of: date
    holdings: Tuple[Holding, ...]
    cash: Dict[str, float] = field(default_factory=dict)
    base_currency: str = "USD"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(),
            "holdings": [holding.to_dict() for holding in self.holdings],
            "cash": dict(self.cash),
            "base_currency": self.base_currency,
        }


@dataclass(frozen=True)
class OptimizationRequest:
    assets: Tuple[str, ...]
    start: Optional[date] = None
    end: Optional[date] = None
    method: str = "mean_variance"
    objective: str = "max_sharpe"
    risk_free_rate: float = 0.02
    long_only: bool = True
    weight_bounds: Tuple[float, float] = (0.0, 1.0)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["assets"] = list(self.assets)
        data["start"] = self.start.isoformat() if self.start else None
        data["end"] = self.end.isoformat() if self.end else None
        data["weight_bounds"] = list(self.weight_bounds)
        return data


@dataclass(frozen=True)
class AllocationResult:
    weights: Dict[str, float]
    expected_return: float
    volatility: float
    sharpe_ratio: float
    method_used: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskReport:
    volatility: float
    max_drawdown: float
    sharpe_ratio: float
    var_95: Optional[float] = None
    cvar_95: Optional[float] = None
    sortino_ratio: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RebalancePlan:
    current_weights: Dict[str, float]
    target_weights: Dict[str, float]
    trades: Dict[str, float]
    estimated_turnover: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
