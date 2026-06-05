"""CorporateActionProcessor — manages and applies corporate actions.

Stores actions in YAML under ``local/corporate_actions.yaml`` (not committed to git).
All methods are functional but data must be provided manually; automated
detection from broker statements or public sources is deferred.

Usage::

    cap = CorporateActionProcessor()
    cap.record_dividend("AAPL", date(2025,6,15), amount_per_share=0.50, currency="USD")
    holdings, cash, cash_adj = cap.apply_to_holdings(holdings, cash, up_to_date=date(2025,6,20))
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.core.paths import PROJECT_ROOT
from src.domain.corporate_actions import (
    CorporateAction,
    DividendAction,
    MergerAction,
    StockSplitAction,
    corporate_action_from_dict,
)


class CorporateActionProcessor:
    """Registry of corporate actions with YAML persistence."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or self._default_path()
        self._actions: List[CorporateAction] = []
        self._load()

    # ── public API ─────────────────────────────────────────────────────

    def get_actions(
        self,
        asset_id: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[CorporateAction]:
        """Filter actions by asset and/or date range."""
        result = list(self._actions)
        if asset_id:
            result = [a for a in result if a.asset_id == asset_id]
        if from_date:
            result = [a for a in result if a.ex_date >= from_date]
        if to_date:
            result = [a for a in result if a.ex_date <= to_date]
        return sorted(result, key=lambda a: a.ex_date)

    def record_dividend(
        self,
        asset_id: str,
        ex_date: date,
        amount_per_share: float,
        currency: str = "USD",
        effective_date: Optional[date] = None,
        withholding_tax_rate: float = 0.0,
    ) -> DividendAction:
        """Record a cash dividend. Stub: does not verify against external data."""
        action = DividendAction(
            asset_id=asset_id,
            ex_date=ex_date,
            effective_date=effective_date or ex_date,
            dividend_per_share=amount_per_share,
            dividend_currency=currency,
            withholding_tax_rate=withholding_tax_rate,
        )
        self._actions.append(action)
        self._save()
        return action

    def record_split(
        self,
        asset_id: str,
        ex_date: date,
        ratio: float,
        effective_date: Optional[date] = None,
    ) -> StockSplitAction:
        """Record a stock split. ratio=2.0 means 2:1 forward split."""
        action = StockSplitAction(
            asset_id=asset_id,
            ex_date=ex_date,
            effective_date=effective_date or ex_date,
            split_ratio=ratio,
        )
        self._actions.append(action)
        self._save()
        return action

    def record_merger(
        self,
        asset_id: str,
        target_asset_id: str,
        ex_date: date,
        exchange_ratio: float,
        cash_per_share: float = 0.0,
        cash_currency: str = "USD",
        effective_date: Optional[date] = None,
    ) -> MergerAction:
        """Record a merger/acquisition."""
        action = MergerAction(
            asset_id=asset_id,
            ex_date=ex_date,
            effective_date=effective_date or ex_date,
            target_asset_id=target_asset_id,
            exchange_ratio=exchange_ratio,
            cash_per_share=cash_per_share,
            cash_currency=cash_currency,
        )
        self._actions.append(action)
        self._save()
        return action

    def apply_to_holdings(
        self,
        holdings: Dict[str, float],
        cash: Dict[str, float],
        up_to_date: date,
    ) -> tuple[Dict[str, float], Dict[str, float], float]:
        """Apply all actions chronologically up to the given date.

        Returns:
            (adjusted_holdings, adjusted_cash, total_cash_adjustment)
        """
        adj_holdings = dict(holdings)
        adj_cash = dict(cash)
        total_cash_adj = 0.0

        for action in self.get_actions(to_date=up_to_date):
            adj_holdings, adj_cash, cash_adj = action.apply(adj_holdings, adj_cash)
            total_cash_adj += cash_adj

        return adj_holdings, adj_cash, total_cash_adj

    def list_all(self) -> List[Dict[str, Any]]:
        """Return all actions as dicts (for API serialization)."""
        return [action.to_dict() for action in sorted(self._actions, key=lambda a: a.ex_date)]

    # ── persistence ────────────────────────────────────────────────────

    @staticmethod
    def _default_path() -> Path:
        local = os.environ.get("OPTIFOLIO_LOCAL_DIR")
        if local:
            return Path(local) / "corporate_actions.yaml"
        path = PROJECT_ROOT / "local" / "corporate_actions.yaml"
        # Fall back to project root if local/ doesn't exist yet
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            records = data.get("actions", []) if isinstance(data, dict) else data or []
            self._actions = [corporate_action_from_dict(r) for r in records]
        except Exception:
            self._actions = []

    def _save(self) -> None:
        data = {"actions": [action.to_dict() for action in self._actions]}
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)
