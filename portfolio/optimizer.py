"""
Unified Portfolio Optimizer Interface.

This module provides a single interface for portfolio optimization,
supporting multiple optimization methods including mean-variance and
Black-Litterman.
"""

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .base import BaseOptimizer, OptimizationResult, RiskMetrics
from .black_litterman import BlackLittermanOptimizer
from .constraints import ConstraintsBuilder, validate_weights
from .mean_variance import MeanVarianceOptimizer
from .risk import RiskCalculator


class PortfolioOptimizer:
    """
    Unified interface for portfolio optimization.
    
    Provides a simple, consistent API for running portfolio optimization
    using different strategies. Supports mean-variance and Black-Litterman
    optimization methods.
    
    Example:
        >>> # Mean-variance optimization
        >>> optimizer = PortfolioOptimizer(method='mean_variance')
        >>> result = optimizer.run(prices)
        
        >>> # Black-Litterman with views
        >>> optimizer = PortfolioOptimizer(method='black_litterman')
        >>> optimizer.add_views({'AAPL': (0.15, 0.8)})
        >>> optimizer.set_market_caps({'AAPL': 3000, 'MSFT': 2500})
        >>> result = optimizer.run(prices)
    
    Attributes:
        method: Current optimization method.
        risk_free_rate: Annual risk-free rate.
    """
    
    VALID_METHODS = ('mean_variance', 'black_litterman')
    
    def __init__(
        self,
        method: str = 'black_litterman',
        risk_free_rate: float = 0.02,
        long_only: bool = True,
        weight_bounds: Tuple[float, float] = (0, 1)
    ):
        """
        Initialize the portfolio optimizer.
        
        Args:
            method: Optimization method - 'mean_variance' or 'black_litterman'.
            risk_free_rate: Annual risk-free rate (default: 2%).
            long_only: If True, only allow non-negative weights.
            weight_bounds: Min and max weight for each position.
        
        Raises:
            ValueError: If method is not recognized.
        """
        if method not in self.VALID_METHODS:
            raise ValueError(
                f"Unknown method '{method}'. Valid methods: {self.VALID_METHODS}"
            )
        
        self._method = method
        self._risk_free_rate = risk_free_rate
        self._long_only = long_only
        self._weight_bounds = weight_bounds
        
        # Initialize constraints builder
        self._constraints = ConstraintsBuilder()
        if long_only:
            self._constraints.set_long_only()
        if weight_bounds != (0, 1):
            self._constraints.set_weight_bounds(*weight_bounds)
        
        # Initialize optimizers
        self._mv_optimizer = MeanVarianceOptimizer(
            risk_free_rate=risk_free_rate,
            long_only=long_only,
            weight_bounds=weight_bounds
        )
        self._bl_optimizer = BlackLittermanOptimizer(
            risk_free_rate=risk_free_rate
        )
        
        # Views and market caps for Black-Litterman
        self._views: Dict[str, Tuple[float, float]] = {}
        self._market_caps: Dict[str, float] = {}
        
        # Last result
        self._last_result: Optional[OptimizationResult] = None
    
    @property
    def method(self) -> str:
        """Get the current optimization method."""
        return self._method
    
    @property
    def risk_free_rate(self) -> float:
        """Get the risk-free rate."""
        return self._risk_free_rate
    
    def set_method(self, method: str) -> 'PortfolioOptimizer':
        """
        Set the optimization method.
        
        Args:
            method: 'mean_variance' or 'black_litterman'.
        
        Returns:
            Self for method chaining.
        """
        if method not in self.VALID_METHODS:
            raise ValueError(
                f"Unknown method '{method}'. Valid methods: {self.VALID_METHODS}"
            )
        self._method = method
        return self
    
    def add_views(self, views: Dict[str, Tuple[float, float]]) -> 'PortfolioOptimizer':
        """
        Add investor views for Black-Litterman optimization.
        
        Views are expressed as expected returns with confidence levels.
        
        Args:
            views: Dictionary mapping symbol to (expected_return, confidence).
                   Expected return should be annualized (e.g., 0.15 for 15%).
                   Confidence should be between 0 and 1.
        
        Returns:
            Self for method chaining.
        
        Example:
            >>> optimizer.add_views({
            ...     'AAPL': (0.15, 0.8),  # 15% return, 80% confidence
            ...     'MSFT': (0.12, 0.6)   # 12% return, 60% confidence
            ... })
        """
        self._views.update(views)
        self._bl_optimizer.set_views(self._views)
        return self
    
    def add_view(
        self,
        symbol: str,
        expected_return: float,
        confidence: float
    ) -> 'PortfolioOptimizer':
        """
        Add a single investor view.
        
        Args:
            symbol: Asset symbol.
            expected_return: Expected annualized return.
            confidence: Confidence level (0-1).
        
        Returns:
            Self for method chaining.
        """
        self._views[symbol] = (expected_return, confidence)
        self._bl_optimizer.add_view(symbol, expected_return, confidence)
        return self
    
    def clear_views(self) -> 'PortfolioOptimizer':
        """Clear all investor views."""
        self._views.clear()
        self._bl_optimizer.clear_views()
        return self
    
    def set_market_caps(self, market_caps: Dict[str, float]) -> 'PortfolioOptimizer':
        """
        Set market capitalizations for Black-Litterman optimization.
        
        Args:
            market_caps: Dictionary mapping symbol to market capitalization.
        
        Returns:
            Self for method chaining.
        """
        self._market_caps = market_caps.copy()
        self._bl_optimizer.set_market_caps(market_caps)
        return self
    
    def set_long_only(self) -> 'PortfolioOptimizer':
        """
        Set long-only constraint.
        
        Returns:
            Self for method chaining.
        """
        self._long_only = True
        self._constraints.set_long_only()
        self._mv_optimizer.long_only = True
        self._mv_optimizer.weight_bounds = (0, 1)
        return self
    
    def set_weight_bounds(
        self,
        min_weight: float,
        max_weight: float
    ) -> 'PortfolioOptimizer':
        """
        Set weight bounds for positions.
        
        Args:
            min_weight: Minimum weight for any position.
            max_weight: Maximum weight for any position.
        
        Returns:
            Self for method chaining.
        """
        self._weight_bounds = (min_weight, max_weight)
        self._constraints.set_weight_bounds(min_weight, max_weight)
        self._mv_optimizer.weight_bounds = (min_weight, max_weight)
        return self
    
    def set_sector_limits(
        self,
        sectors: Dict[str, List[str]],
        limits: Dict[str, float]
    ) -> 'PortfolioOptimizer':
        """
        Set sector exposure limits.
        
        Args:
            sectors: Dictionary mapping sector name to list of symbols.
            limits: Dictionary mapping sector name to maximum weight.
        
        Returns:
            Self for method chaining.
        """
        self._constraints.set_sector_limits(sectors, limits)
        return self
    
    def run(
        self,
        prices: pd.DataFrame,
        optimization_method: str = 'max_sharpe',
        **kwargs
    ) -> OptimizationResult:
        """
        Execute portfolio optimization.
        
        Args:
            prices: DataFrame with assets as columns and dates as index.
            optimization_method: 'max_sharpe' or 'min_volatility'.
            **kwargs: Additional arguments passed to the optimizer.
        
        Returns:
            OptimizationResult with optimal weights and metrics.
        
        Raises:
            ValueError: If price data is insufficient.
        """
        if self._method == 'mean_variance':
            result = self._mv_optimizer.optimize(
                prices,
                method=optimization_method,
                **kwargs
            )
        else:  # black_litterman
            result = self._bl_optimizer.optimize(
                prices,
                method=optimization_method,
                **kwargs
            )
        
        # Validate result against constraints
        is_valid, violations = validate_weights(
            result.weights,
            self._constraints.build()
        )
        
        if not is_valid:
            result.metadata['constraint_violations'] = violations
        
        self._last_result = result
        return result
    
    def calculate_risk(
        self,
        weights: Dict[str, float],
        prices: pd.DataFrame
    ) -> RiskMetrics:
        """
        Calculate risk metrics for given weights.
        
        Args:
            weights: Dictionary of portfolio weights.
            prices: Price DataFrame.
        
        Returns:
            RiskMetrics with various risk measures.
        """
        # Calculate portfolio returns
        returns = prices.pct_change().dropna()
        
        # Align weights with returns columns
        weight_array = [weights.get(col, 0) for col in returns.columns]
        weight_array = [w / sum(weight_array) if sum(weight_array) > 0 else 0 
                       for w in weight_array]
        
        # Calculate portfolio returns
        portfolio_returns = (returns * weight_array).sum(axis=1)
        
        # Calculate risk metrics
        metrics = RiskCalculator.calculate_all_metrics(
            portfolio_returns,
            risk_free_rate=self._risk_free_rate
        )
        
        # Calculate sector weights if sector mapping exists
        sector_weights = {}
        sector_mapping = self._constraints.get_sector_mapping()
        if sector_mapping:
            for symbol, weight in weights.items():
                sector = sector_mapping.get(symbol)
                if sector:
                    sector_weights[sector] = sector_weights.get(sector, 0) + weight
        
        return RiskMetrics(
            volatility=metrics['volatility'],
            var_95=metrics['var'],
            cvar_95=metrics['cvar'],
            max_drawdown=metrics['max_drawdown'],
            sharpe_ratio=metrics['sharpe_ratio'],
            sortino_ratio=metrics['sortino_ratio'],
            sector_weights=sector_weights
        )
    
    def get_report(self) -> str:
        """
        Generate a detailed report of the last optimization.
        
        Returns:
            Formatted string report.
        
        Raises:
            ValueError: If no optimization has been run yet.
        """
        if self._last_result is None:
            return "No optimization has been run yet."
        
        result = self._last_result
        
        lines = [
            "=" * 60,
            "PORTFOLIO OPTIMIZATION REPORT",
            "=" * 60,
            "",
            f"Method: {result.method_used}",
            f"Risk-Free Rate: {self._risk_free_rate:.2%}",
            "",
            "-" * 40,
            "PERFORMANCE METRICS",
            "-" * 40,
            f"Expected Return:    {result.expected_return:>10.2%}",
            f"Expected Volatility: {result.volatility:>9.2%}",
            f"Sharpe Ratio:       {result.sharpe_ratio:>10.4f}",
            "",
            "-" * 40,
            "OPTIMAL WEIGHTS",
            "-" * 40,
        ]
        
        # Add weights sorted by value
        for symbol, weight in result.sorted_weights:
            if weight > 1e-6:  # Only show non-zero weights
                lines.append(f"  {symbol:<10} {weight:>10.2%}")
        
        # Add metadata if available
        if result.metadata:
            lines.extend([
                "",
                "-" * 40,
                "ADDITIONAL INFO",
                "-" * 40,
            ])
            
            for key, value in result.metadata.items():
                if key == 'constraint_violations':
                    lines.append(f"Constraint Violations: {value}")
                elif key not in ('posterior_returns', 'views'):
                    lines.append(f"{key}: {value}")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def get_efficient_frontier(
        self,
        prices: pd.DataFrame,
        n_points: int = 100
    ) -> List[Tuple[float, float]]:
        """
        Calculate efficient frontier points.
        
        Only available for mean-variance optimization.
        
        Args:
            prices: Price DataFrame.
            n_points: Number of points on the frontier.
        
        Returns:
            List of (return, volatility) tuples.
        """
        if self._method != 'mean_variance':
            raise NotImplementedError(
                "Efficient frontier is only available for mean-variance optimization"
            )
        
        return self._mv_optimizer.calculate_efficient_frontier(
            prices, n_points=n_points
        )
    
    @property
    def last_result(self) -> Optional[OptimizationResult]:
        """Get the most recent optimization result."""
        return self._last_result
    
    def __repr__(self) -> str:
        return (
            f"PortfolioOptimizer(\n"
            f"  method='{self._method}',\n"
            f"  risk_free_rate={self._risk_free_rate:.2%},\n"
            f"  long_only={self._long_only},\n"
            f"  views={len(self._views)},\n"
            f"  market_caps={len(self._market_caps)}\n"
            f")"
        )
