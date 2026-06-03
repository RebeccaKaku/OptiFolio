"""Relationship contracts — portfolios, exposures, look-through links, payoffs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class PortfolioComponent:
    """A single component (instrument, series, exposure, or sub-portfolio)
    within a portfolio definition."""

    target_id: str
    target_kind: str = "instrument"  # instrument, series, exposure, portfolio
    weight: Optional[float] = None
    quantity: Optional[float] = None
    role: str = "holding"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioDefinition:
    """A portfolio composed of instruments, series, exposures, or sub-portfolios."""

    portfolio_id: str
    name: str = ""
    components: Tuple[PortfolioComponent, ...] = ()
    rebalance_policy: Optional[str] = None
    weighting_policy: str = "equal_weight"
    currency: str = "CNY"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["components"] = [c.to_dict() for c in self.components]
        return d


@dataclass(frozen=True)
class UnderlyingLink:
    """A look-through relationship between two domain objects.

    relationship_type is one of:
      holds, tracks, references, settles_to, proxy_for, priced_by

    lookthrough_policy:
      none      — do not look through
      holdings  — expand to constituent holdings
      exposure  — expand to risk-factor exposures
      risk_only — used for risk decomposition, not for valuation
    """

    owner_id: str
    underlying_id: str
    owner_kind: str = "instrument"
    underlying_kind: str = "portfolio"
    relationship_type: str = "holds"  # holds, tracks, references, settles_to, proxy_for, priced_by
    lookthrough_policy: str = "none"  # none, holdings, exposure, risk_only
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["valid_from"] = self.valid_from.isoformat() if self.valid_from else None
        d["valid_to"] = self.valid_to.isoformat() if self.valid_to else None
        return d


@dataclass(frozen=True)
class ExposureDefinition:
    """A risk-factor or macro exposure that can be proxied by tradable instruments."""

    exposure_id: str
    reference_series_id: str
    tradable_proxy_ids: Tuple[str, ...] = ()
    default_proxy_id: Optional[str] = None
    hedge_ratio_policy: str = "one_to_one"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tradable_proxy_ids"] = list(self.tradable_proxy_ids)
        return d


@dataclass(frozen=True)
class PayoffDefinition:
    """Describes the payoff structure of a derivative or structured product."""

    payoff_id: str
    owner_instrument_id: str
    underlying_refs: Tuple[str, ...] = ()
    payoff_type: str = "linear"
    parameters: Dict[str, Any] = field(default_factory=dict)
    valuation_model: str = "none"
    greeks_policy: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["underlying_refs"] = list(self.underlying_refs)
        return d
