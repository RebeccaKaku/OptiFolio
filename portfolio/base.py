"""
Base classes for portfolio optimization.

This module provides the foundational data structures and abstract base class
for portfolio optimization strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import pandas as pd


@dataclass
class OptimizationResult:
    """
    Result of portfolio optimization.
    
    Attributes:
        weights: Dictionary mapping symbol to weight (0-1).
        expected_return: Annualized expected return.
        volatility: Annualized volatility (standard deviation).
        sharpe_ratio: Risk-adjusted return metric.
        method_used: Name of the optimization method used.
        metadata: Additional information about the optimization.
    """
    weights: Dict[str, float]
    expected_return: float
    volatility: float
    sharpe_ratio: float
    method_used: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert weights to a DataFrame.
        
        Returns:
            DataFrame with symbols as index and weights as column.
        """
        return pd.DataFrame(
            {'weight': self.weights},
            index=list(self.weights.keys())
        ).sort_values('weight', ascending=False)
    
    @property
    def sorted_weights(self) -> List[Tuple[str, float]]:
        """
        Return weights sorted by value descending.
        
        Returns:
            List of (symbol, weight) tuples sorted by weight.
        """
        return sorted(
            self.weights.items(),
            key=lambda x: x[1],
            reverse=True
        )
    
    @property
    def non_zero_weights(self) -> Dict[str, float]:
        """
        Return only non-zero weights.
        
        Returns:
            Dictionary of symbols with non-zero weights.
        """
        return {k: v for k, v in self.weights.items() if v > 1e-6}
    
    def __repr__(self) -> str:
        return (
            f"OptimizationResult(\n"
            f"  method='{self.method_used}',\n"
            f"  expected_return={self.expected_return:.4f},\n"
            f"  volatility={self.volatility:.4f},\n"
            f"  sharpe_ratio={self.sharpe_ratio:.4f},\n"
            f"  assets={len(self.non_zero_weights)}\n"
            f")"
        )


@dataclass
class RiskMetrics:
    """
    Portfolio risk metrics.
    
    Attributes:
        volatility: Annualized volatility.
        var_95: Value at Risk at 95% confidence.
        cvar_95: Conditional VaR (Expected Shortfall) at 95% confidence.
        max_drawdown: Maximum drawdown.
        sharpe_ratio: Sharpe ratio.
        sortino_ratio: Sortino ratio.
        sector_weights: Dictionary mapping sector to total weight.
    """
    volatility: float
    var_95: float
    cvar_95: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    sector_weights: Dict[str, float] = field(default_factory=dict)
    
    def __repr__(self) -> str:
        return (
            f"RiskMetrics(\n"
            f"  volatility={self.volatility:.4f},\n"
            f"  var_95={self.var_95:.4f},\n"
            f"  cvar_95={self.cvar_95:.4f},\n"
            f"  max_drawdown={self.max_drawdown:.4f},\n"
            f"  sharpe_ratio={self.sharpe_ratio:.4f},\n"
            f"  sortino_ratio={self.sortino_ratio:.4f}\n"
            f")"
        )


class BaseOptimizer(ABC):
    """
    Abstract base class for portfolio optimization strategies.
    
    All optimization strategies must implement the optimize method
    which takes price data and returns an OptimizationResult.
    """
    
    def __init__(self, risk_free_rate: float = 0.02):
        """
        Initialize the optimizer.
        
        Args:
            risk_free_rate: Annual risk-free rate (default: 2%).
        """
        self.risk_free_rate = risk_free_rate
        self._last_result: OptimizationResult | None = None
    
    @abstractmethod
    def optimize(self, prices: pd.DataFrame) -> OptimizationResult:
        """
        Optimize portfolio weights.
        
        Args:
            prices: DataFrame with assets as columns and dates as index.
                   Each column contains price data for an asset.
        
        Returns:
            OptimizationResult with optimal weights and metrics.
        
        Raises:
            ValueError: If price data is insufficient or invalid.
        """
        pass
    
    def validate_prices(self, prices: pd.DataFrame) -> None:
        """
        Validate price data before optimization.
        
        Args:
            prices: Price DataFrame to validate.
        
        Raises:
            ValueError: If validation fails.
        """
        if prices is None or prices.empty:
            raise ValueError("Price data cannot be empty")
        
        if len(prices.columns) < 1:
            raise ValueError("At least one asset is required")
        
        if len(prices) < 2:
            raise ValueError("At least 2 price observations are required")
        
        # Check for all-NaN columns
        nan_columns = prices.columns[prices.isna().all()].tolist()
        if nan_columns:
            raise ValueError(f"Columns with all NaN values: {nan_columns}")
    
    def calculate_returns(self, prices: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate simple returns from prices.
        
        Args:
            prices: Price DataFrame.
        
        Returns:
            DataFrame of simple returns.
        """
        return prices.pct_change().dropna()
    
    def calculate_log_returns(self, prices: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate log returns from prices.
        
        Args:
            prices: Price DataFrame.
        
        Returns:
            DataFrame of log returns.
        """
        return np.log(prices / prices.shift(1)).dropna()
    
    @property
    def last_result(self) -> OptimizationResult | None:
        """
        Get the most recent optimization result.
        
        Returns:
            Last OptimizationResult or None if not yet run.
        """
        return self._last_result


# Import numpy for log returns calculation
import numpy as np
