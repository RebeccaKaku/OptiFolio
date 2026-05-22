"""Portfolio backtesting engine with a vectorbt-compatible boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestRequest:
    prices: pd.DataFrame
    target_weights: Dict[str, float]
    initial_cash: float = 1.0
    rebalance_frequency: str = "M"
    fee_rate: float = 0.0
    risk_free_rate: float = 0.0


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    metrics: Dict[str, float]
    asset_contribution: Dict[str, float]
    engine: str = "vectorbt-compatible"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "equity_curve": {
                index.isoformat(): float(value)
                for index, value in self.equity_curve.items()
            },
            "returns": {
                index.isoformat(): float(value)
                for index, value in self.returns.items()
            },
            "metrics": dict(self.metrics),
            "asset_contribution": dict(self.asset_contribution),
            "engine": self.engine,
            "metadata": dict(self.metadata),
        }


class BacktestEngine:
    """Run deterministic portfolio-level backtests from canonical price matrices."""

    def run(self, request: BacktestRequest) -> BacktestResult:
        prices = self._validate_prices(request.prices)
        weights = self._normalize_weights(request.target_weights, prices.columns)
        returns = prices.pct_change().fillna(0.0)

        portfolio_returns = returns.dot(pd.Series(weights))
        fee_drag = self._fee_drag(returns.index, weights, request.rebalance_frequency, request.fee_rate)
        net_returns = portfolio_returns - fee_drag
        equity_curve = (1.0 + net_returns).cumprod() * request.initial_cash

        asset_contribution = (returns.mul(pd.Series(weights), axis=1)).sum().to_dict()
        metrics = self._calculate_metrics(equity_curve, net_returns, request.risk_free_rate)

        return BacktestResult(
            equity_curve=equity_curve,
            returns=net_returns,
            metrics=metrics,
            asset_contribution={asset: float(value) for asset, value in asset_contribution.items()},
            metadata={
                "weights": weights,
                "rebalance_frequency": request.rebalance_frequency,
                "fee_rate": request.fee_rate,
            },
        )

    def _validate_prices(self, prices: pd.DataFrame) -> pd.DataFrame:
        if prices is None or prices.empty:
            raise ValueError("Price matrix cannot be empty")
        clean = prices.copy()
        clean.index = pd.to_datetime(clean.index)
        clean = clean.sort_index()
        clean = clean.apply(pd.to_numeric, errors="coerce")
        if clean.dropna(how="all").empty:
            raise ValueError("Price matrix has no numeric observations")
        if (clean <= 0).any().any():
            raise ValueError("Price matrix cannot contain non-positive prices")
        return clean.ffill().dropna(how="any")

    def _normalize_weights(self, weights: Dict[str, float], assets: pd.Index) -> Dict[str, float]:
        aligned = {asset: float(weights.get(asset, 0.0)) for asset in assets}
        total = sum(aligned.values())
        if total <= 0:
            raise ValueError("At least one positive target weight is required")
        return {asset: value / total for asset, value in aligned.items()}

    def _fee_drag(
        self,
        index: pd.DatetimeIndex,
        weights: Dict[str, float],
        rebalance_frequency: str,
        fee_rate: float,
    ) -> pd.Series:
        drag = pd.Series(0.0, index=index)
        if fee_rate <= 0 or index.empty:
            return drag

        rebalance_dates = pd.Series(index=index, data=1).resample(rebalance_frequency).first().dropna().index
        if len(rebalance_dates) <= 1:
            return drag

        turnover = sum(abs(value) for value in weights.values())
        for date in rebalance_dates[1:]:
            actual_date = index[index.get_indexer([date], method="nearest")[0]]
            drag.loc[actual_date] += turnover * fee_rate
        return drag

    def _calculate_metrics(
        self,
        equity_curve: pd.Series,
        returns: pd.Series,
        risk_free_rate: float,
    ) -> Dict[str, float]:
        periods_per_year = 252
        total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1 if len(equity_curve) > 1 else 0.0
        annualized_return = (1 + total_return) ** (periods_per_year / max(len(returns), 1)) - 1
        volatility = returns.std(ddof=0) * np.sqrt(periods_per_year)
        excess_return = annualized_return - risk_free_rate
        sharpe = excess_return / volatility if volatility > 0 else 0.0
        drawdown = equity_curve / equity_curve.cummax() - 1

        return {
            "total_return": float(total_return),
            "annualized_return": float(annualized_return),
            "volatility": float(volatility),
            "sharpe_ratio": float(sharpe),
            "max_drawdown": float(drawdown.min()),
        }
