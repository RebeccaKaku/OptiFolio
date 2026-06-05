"""Corporate action types — dividends, stock splits, mergers.

All actions are frozen dataclasses implementing the ``CorporateAction`` ABC.
The ``apply()`` method takes current holdings and cash, and returns
(new_holdings, new_cash, cash_adjustment).

Stub implementations: logic is correct but data must be provided manually.
Automatic detection from external sources is deferred to future work.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class CorporateAction(ABC):
    """Abstract base for all corporate actions."""

    asset_id: str
    ex_date: date          # date when the action takes effect for pricing
    effective_date: date   # date when cash/holdings actually change
    action_type: str = ""  # "dividend", "stock_split", "merger"

    @abstractmethod
    def apply(
        self, holdings: Dict[str, float], cash: Dict[str, float]
    ) -> Tuple[Dict[str, float], Dict[str, float], float]:
        """Apply this action to holdings and cash.

        Returns:
            (new_holdings, new_cash, cash_adjustment_in_asset_currency)
        """
        ...

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["ex_date"] = self.ex_date.isoformat()
        data["effective_date"] = self.effective_date.isoformat()
        return data


@dataclass(frozen=True)
class DividendAction(CorporateAction):
    """Cash dividend with optional withholding tax."""

    dividend_per_share: float = 0.0
    dividend_currency: str = "USD"
    withholding_tax_rate: float = 0.0  # e.g. 0.10 for 10%

    def __post_init__(self):
        if self.action_type:
            pass  # allow override
        object.__setattr__(self, "action_type", "dividend")

    def apply(
        self, holdings: Dict[str, float], cash: Dict[str, float]
    ) -> Tuple[Dict[str, float], Dict[str, float], float]:
        shares = holdings.get(self.asset_id, 0.0)
        if shares <= 0:
            return dict(holdings), dict(cash), 0.0

        gross = shares * self.dividend_per_share
        net = gross * (1.0 - self.withholding_tax_rate)

        new_cash = dict(cash)
        new_cash[self.dividend_currency] = (
            new_cash.get(self.dividend_currency, 0.0) + net
        )
        return dict(holdings), new_cash, net

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DividendAction":
        return cls(
            asset_id=data["asset_id"],
            ex_date=date.fromisoformat(data["ex_date"]),
            effective_date=date.fromisoformat(data["effective_date"]),
            dividend_per_share=float(data.get("dividend_per_share", 0)),
            dividend_currency=data.get("dividend_currency", "USD"),
            withholding_tax_rate=float(data.get("withholding_tax_rate", 0)),
        )


@dataclass(frozen=True)
class StockSplitAction(CorporateAction):
    """Stock split or reverse split.

    split_ratio: e.g. 2.0 for 2:1 forward split; 0.5 for 1:2 reverse split.
    """

    split_ratio: float = 1.0  # > 1 = forward split, < 1 = reverse split

    def __post_init__(self):
        if self.action_type:
            pass
        object.__setattr__(self, "action_type", "stock_split")
        if self.split_ratio <= 0:
            raise ValueError(f"split_ratio must be positive, got {self.split_ratio}")

    def apply(
        self, holdings: Dict[str, float], cash: Dict[str, float]
    ) -> Tuple[Dict[str, float], Dict[str, float], float]:
        new_holdings = dict(holdings)
        if self.asset_id in new_holdings:
            new_holdings[self.asset_id] *= self.split_ratio
        return new_holdings, dict(cash), 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StockSplitAction":
        return cls(
            asset_id=data["asset_id"],
            ex_date=date.fromisoformat(data["ex_date"]),
            effective_date=date.fromisoformat(data["effective_date"]),
            split_ratio=float(data.get("split_ratio", 1.0)),
        )


@dataclass(frozen=True)
class MergerAction(CorporateAction):
    """Merger where the original asset is exchanged for shares of target + optional cash."""

    target_asset_id: str = ""
    exchange_ratio: float = 1.0   # shares of target per share of original
    cash_per_share: float = 0.0   # optional cash component
    cash_currency: str = "USD"

    def __post_init__(self):
        if self.action_type:
            pass
        object.__setattr__(self, "action_type", "merger")

    def apply(
        self, holdings: Dict[str, float], cash: Dict[str, float]
    ) -> Tuple[Dict[str, float], Dict[str, float], float]:
        new_holdings = dict(holdings)
        shares = new_holdings.pop(self.asset_id, 0.0)

        if shares > 0 and self.target_asset_id:
            new_shares = shares * self.exchange_ratio
            new_holdings[self.target_asset_id] = (
                new_holdings.get(self.target_asset_id, 0.0) + new_shares
            )

        cash_adj = shares * self.cash_per_share
        new_cash = dict(cash)
        if cash_adj > 0:
            new_cash[self.cash_currency] = (
                new_cash.get(self.cash_currency, 0.0) + cash_adj
            )

        return new_holdings, new_cash, cash_adj

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MergerAction":
        return cls(
            asset_id=data["asset_id"],
            ex_date=date.fromisoformat(data["ex_date"]),
            effective_date=date.fromisoformat(data["effective_date"]),
            target_asset_id=data.get("target_asset_id", ""),
            exchange_ratio=float(data.get("exchange_ratio", 1.0)),
            cash_per_share=float(data.get("cash_per_share", 0)),
            cash_currency=data.get("cash_currency", "USD"),
        )


# ── Factory ────────────────────────────────────────────────────────────


_ACTION_REGISTRY: Dict[str, type] = {
    "dividend": DividendAction,
    "stock_split": StockSplitAction,
    "merger": MergerAction,
}


def corporate_action_from_dict(data: Dict[str, Any]) -> CorporateAction:
    """Deserialize any corporate action from a dict."""
    action_type = data.get("action_type", "")
    cls = _ACTION_REGISTRY.get(action_type)
    if cls is None:
        raise ValueError(f"Unknown corporate action type: {action_type}")
    return cls.from_dict(data)
