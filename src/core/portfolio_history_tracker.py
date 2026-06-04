import pandas as pd
import numpy as np
from typing import Dict, Any

class PortfolioHistoryTracker:
    @staticmethod
    def compute_metrics(returns: pd.Series, risk_free_rate: float = 0.02) -> Dict[str, Any]:
        """
        Compute portfolio performance metrics: sharpe, sortino, calmar, max_drawdown, win_rate.
        """
        if returns.empty:
            return {}

        total_return = (1 + returns).prod() - 1
        ann_return = (1 + total_return) ** (252 / len(returns)) - 1 if len(returns) > 0 else 0
        vol = returns.std() * np.sqrt(252)

        sharpe = (ann_return - risk_free_rate) / vol if vol > 0 else 0

        neg_returns = returns[returns < 0]
        downside_std = neg_returns.std() * np.sqrt(252) if not neg_returns.empty else 0
        sortino = (ann_return - risk_free_rate) / downside_std if downside_std > 0 else 0

        cum_returns = (1 + returns).cumprod()
        running_max = cum_returns.cummax()
        drawdown = (cum_returns - running_max) / running_max
        max_drawdown = drawdown.min()

        calmar = ann_return / abs(max_drawdown) if max_drawdown != 0 else 0
        win_rate = (returns > 0).mean()

        return {
            "total_return": float(total_return),
            "annual_return": float(ann_return),
            "volatility": float(vol),
            "sharpe": float(sharpe),
            "sortino": float(sortino),
            "calmar": float(calmar),
            "max_drawdown": float(max_drawdown),
            "win_rate": float(win_rate)
        }

    @staticmethod
    def compute_rolling_metrics(returns: pd.Series, window: int = 60) -> pd.DataFrame:
        """
        Compute rolling performance metrics.
        """
        rolling_ann_return = returns.rolling(window).mean() * 252
        rolling_vol = returns.rolling(window).std() * np.sqrt(252)
        rolling_sharpe = rolling_ann_return / rolling_vol

        # Calculate rolling max drawdown
        def calc_max_dd(window_returns):
            cum_returns = (1 + window_returns).cumprod()
            return (cum_returns / cum_returns.cummax() - 1).min()

        rolling_max_dd = returns.rolling(window).apply(calc_max_dd)

        return pd.DataFrame({
            "rolling_sharpe": rolling_sharpe,
            "rolling_max_drawdown": rolling_max_dd
        })
