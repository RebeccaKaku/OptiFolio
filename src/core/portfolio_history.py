"""PortfolioHistoryTracker — records and queries portfolio value over time.

Stores snapshots in Parquet under ``local/portfolio_history.parquet``.
Reconstructs equity curves from sparse snapshots and computes
performance metrics.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.core.paths import PROJECT_ROOT
from src.domain import PortfolioHistoryEntry, ValuationResult


class PortfolioHistoryTracker:
    """Tracks portfolio value over time via snapshots."""

    COLUMNS = [
        "date", "total_value", "holdings_value", "cash_value",
        "base_currency", "num_positions",
    ]

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or self._default_path()
        self._df = self._load()

    # ── public API ─────────────────────────────────────────────────────

    def record(self, valuation: ValuationResult) -> PortfolioHistoryEntry:
        """Store a valuation as a history entry (persisted to disk)."""
        entry = PortfolioHistoryEntry(
            date=valuation.as_of,
            total_value=valuation.total_value,
            holdings_value=valuation.holdings_value,
            cash_value=valuation.cash_value,
            base_currency=valuation.base_currency,
            num_positions=len(valuation.positions),
        )

        row = pd.DataFrame([entry.to_dict()])
        row["date"] = pd.to_datetime(row["date"])
        if self._df.empty:
            self._df = row
        else:
            self._df = pd.concat([self._df, row], ignore_index=True)
        self._df = self._df.drop_duplicates("date", keep="last")
        self._df = self._df.sort_values("date").reset_index(drop=True)
        self._save()
        return entry

    def get_history(
        self,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> pd.DataFrame:
        """Return the equity curve as a DataFrame."""
        df = self._df.copy()
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            if start:
                df = df[df["date"] >= pd.Timestamp(start)]
            if end:
                df = df[df["date"] <= pd.Timestamp(end)]
        return df.sort_values("date").reset_index(drop=True)

    def compute_metrics(
        self,
        start: Optional[date] = None,
        end: Optional[date] = None,
        risk_free_rate: float = 0.0,
    ) -> Dict[str, float]:
        """Compute performance metrics from tracked history.

        Returns dict with keys: total_return, annualized_return,
        volatility, sharpe_ratio, max_drawdown, num_observations.
        """
        df = self.get_history(start, end)
        if df.empty or len(df) < 2:
            return {
                "total_return": 0.0,
                "annualized_return": 0.0,
                "volatility": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "num_observations": len(df),
            }

        periods_per_year = 365.0
        equity = df.set_index("date")["total_value"]

        total_return = float(equity.iloc[-1] / equity.iloc[0] - 1)
        days = (equity.index[-1] - equity.index[0]).days
        days = max(days, 1)
        annualized_return = float(
            (1 + total_return) ** (periods_per_year / days) - 1
        )

        daily_returns = equity.pct_change().dropna()
        volatility = float(daily_returns.std(ddof=0) * np.sqrt(periods_per_year))

        excess = annualized_return - risk_free_rate
        sharpe = float(excess / volatility) if volatility > 0 else 0.0

        dd = equity / equity.cummax() - 1
        max_drawdown = float(dd.min())

        return {
            "total_return": round(total_return, 6),
            "annualized_return": round(annualized_return, 6),
            "volatility": round(volatility, 6),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown": round(max_drawdown, 6),
            "num_observations": len(df),
        }

    def clear(self) -> None:
        """Delete all history."""
        self._df = pd.DataFrame(columns=self.COLUMNS)
        self._save()

    # ── persistence ────────────────────────────────────────────────────

    @staticmethod
    def _default_path() -> Path:
        local = os.environ.get("OPTIFOLIO_LOCAL_DIR")
        if local:
            return Path(local) / "portfolio_history.parquet"
        path = PROJECT_ROOT / "local" / "portfolio_history.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _load(self) -> pd.DataFrame:
        if self.storage_path.exists():
            try:
                return pd.read_parquet(self.storage_path)
            except Exception:
                pass
        return pd.DataFrame(columns=self.COLUMNS)

    def _save(self) -> None:
        if self._df.empty:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._df.to_parquet(self.storage_path, compression="snappy", index=False)
