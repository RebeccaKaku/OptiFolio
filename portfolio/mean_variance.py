"""
Mean-Variance Portfolio Optimization.

This module implements classical mean-variance optimization using pyportfolioopt.
Supports maximum Sharpe ratio and minimum volatility optimization objectives.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from pypfopt import EfficientFrontier, expected_returns, risk_models

from .base import BaseOptimizer, OptimizationResult


class MeanVarianceOptimizer(BaseOptimizer):
    """
    Classical mean-variance portfolio optimization.
    
    Uses pyportfolioopt's EfficientFrontier for core optimization.
    Supports maximum Sharpe ratio and minimum volatility objectives.
    
    Example:
        >>> optimizer = MeanVarianceOptimizer(risk_free_rate=0.02)
        >>> result = optimizer.optimize(prices, method='max_sharpe')
        >>> print(result.weights)
    """
    
    def __init__(
        self,
        risk_free_rate: float = 0.02,
        long_only: bool = True,
        weight_bounds: Tuple[float, float] = (0, 1)
    ):
        """
        Initialize the mean-variance optimizer.
        
        Args:
            risk_free_rate: Annual risk-free rate (default: 2%).
            long_only: If True, only allow non-negative weights.
            weight_bounds: Min and max weight for each asset.
        """
        super().__init__(risk_free_rate)
        self.long_only = long_only
        self.weight_bounds = weight_bounds
    
    def optimize(
        self,
        prices: pd.DataFrame,
        method: str = 'max_sharpe',
        expected_returns_method: str = 'mean_historical_return',
        risk_model: str = 'sample_cov'
    ) -> OptimizationResult:
        """
        Optimize portfolio weights using mean-variance optimization.
        
        Args:
            prices: DataFrame with assets as columns and dates as index.
            method: Optimization method - 'max_sharpe' or 'min_volatility'.
            expected_returns_method: Method to estimate expected returns.
                Options: 'mean_historical_return', 'ema_historical_return',
                         'capm_return'
            risk_model: Covariance estimation method.
                Options: 'sample_cov', 'semicovariance', 'exp_cov',
                         'ledoit_wolf', 'ledoit_wolf_constant_variance',
                         'ledoit_wolf_single_factor', 'ledoit_wolf_shrinkage',
                         'oracle_approximating'
        
        Returns:
            OptimizationResult with optimal weights and metrics.
        
        Raises:
            ValueError: If price data is insufficient or method is invalid.
        """
        # Validate inputs
        self.validate_prices(prices)
        
        if method not in ('max_sharpe', 'min_volatility'):
            raise ValueError(
                f"Invalid method '{method}'. Use 'max_sharpe' or 'min_volatility'"
            )
        
        # Calculate expected returns and covariance matrix
        mu = self._calculate_expected_returns(
            prices, expected_returns_method
        )
        cov_matrix = self._calculate_risk_model(prices, risk_model)
        
        # Create efficient frontier
        ef = EfficientFrontier(
            mu,
            cov_matrix,
            weight_bounds=self.weight_bounds if self.long_only else (None, None)
        )
        
        # Optimize based on method
        try:
            if method == 'max_sharpe':
                weights = ef.max_sharpe(self.risk_free_rate)
            else:
                weights = ef.min_volatility()
        except Exception as e:
            raise ValueError(f"Optimization failed: {str(e)}") from e
        
        # Clean weights (remove near-zero values)
        cleaned_weights = ef.clean_weights()
        
        # Calculate portfolio performance
        expected_return, volatility, sharpe = ef.portfolio_performance(
            risk_free_rate=self.risk_free_rate
        )
        
        # Create result
        result = OptimizationResult(
            weights=dict(cleaned_weights),
            expected_return=expected_return,
            volatility=volatility,
            sharpe_ratio=sharpe,
            method_used=f"mean_variance_{method}",
            metadata={
                'expected_returns_method': expected_returns_method,
                'risk_model': risk_model,
                'long_only': self.long_only,
                'weight_bounds': self.weight_bounds
            }
        )
        
        self._last_result = result
        return result
    
    def _calculate_expected_returns(
        self,
        prices: pd.DataFrame,
        method: str
    ) -> pd.Series:
        """
        Calculate expected returns using specified method.
        
        Args:
            prices: Price DataFrame.
            method: Estimation method name.
        
        Returns:
            Series of expected returns for each asset.
        """
        method_map = {
            'mean_historical_return': expected_returns.mean_historical_return,
            'ema_historical_return': expected_returns.ema_historical_return,
            'capm_return': expected_returns.capm_return
        }
        
        if method not in method_map:
            raise ValueError(
                f"Unknown expected returns method: {method}. "
                f"Options: {list(method_map.keys())}"
            )
        
        return method_map[method](prices)
    
    def _calculate_risk_model(
        self,
        prices: pd.DataFrame,
        method: str
    ) -> pd.DataFrame:
        """
        Calculate covariance matrix using specified method.
        
        Args:
            prices: Price DataFrame.
            method: Risk model name.
        
        Returns:
            Covariance matrix DataFrame.
        """
        method_map = {
            'sample_cov': risk_models.sample_cov,
            'semicovariance': risk_models.semicovariance,
            'exp_cov': risk_models.exp_cov,
            'ledoit_wolf': risk_models.CovarianceShrinkage(
                prices
            ).ledoit_wolf,
            'ledoit_wolf_constant_variance': lambda: risk_models.CovarianceShrinkage(
                prices
            ).ledoit_wolf_constant_variance(),
            'ledoit_wolf_single_factor': lambda: risk_models.CovarianceShrinkage(
                prices
            ).ledoit_wolf_single_factor(),
            'ledoit_wolf_shrinkage': lambda: risk_models.CovarianceShrinkage(
                prices
            ).ledoit_wolf_shrinkage(),
            'oracle_approximating': lambda: risk_models.CovarianceShrinkage(
                prices
            ).oracle_approximating()
        }
        
        if method not in method_map:
            raise ValueError(
                f"Unknown risk model: {method}. "
                f"Options: {list(method_map.keys())}"
            )
        
        result = method_map[method]
        # Handle callable vs function
        if callable(result) and method in ('ledoit_wolf',):
            return result()
        elif callable(result):
            return result(prices) if 'prices' in result.__code__.co_varnames else result()
        return result
    
    def calculate_efficient_frontier(
        self,
        prices: pd.DataFrame,
        n_points: int = 100,
        expected_returns_method: str = 'mean_historical_return',
        risk_model: str = 'sample_cov'
    ) -> List[Tuple[float, float]]:
        """
        Calculate efficient frontier points.
        
        Args:
            prices: Price DataFrame.
            n_points: Number of points on the frontier.
            expected_returns_method: Method for expected returns.
            risk_model: Covariance estimation method.
        
        Returns:
            List of (return, volatility) tuples representing the frontier.
        """
        self.validate_prices(prices)
        
        mu = self._calculate_expected_returns(prices, expected_returns_method)
        cov_matrix = self._calculate_risk_model(prices, risk_model)
        
        ef = EfficientFrontier(
            mu,
            cov_matrix,
            weight_bounds=self.weight_bounds if self.long_only else (None, None)
        )
        
        # Get minimum volatility portfolio
        ef.min_volatility()
        min_vol_return, min_vol_vol, _ = ef.portfolio_performance()
        
        # Get maximum return portfolio (100% in highest return asset)
        max_return = mu.max()
        
        # Generate efficient frontier
        frontier_points = []
        target_returns = np.linspace(min_vol_return, max_return, n_points)
        
        for target in target_returns:
            ef_copy = EfficientFrontier(
                mu,
                cov_matrix,
                weight_bounds=self.weight_bounds if self.long_only else (None, None)
            )
            try:
                ef_copy.efficient_return(target)
                ret, vol, _ = ef_copy.portfolio_performance()
                frontier_points.append((ret, vol))
            except Exception:
                # Skip points that can't be achieved
                continue
        
        return frontier_points
    
    def get_minimum_variance(
        self,
        prices: pd.DataFrame,
        expected_returns_method: str = 'mean_historical_return',
        risk_model: str = 'sample_cov'
    ) -> OptimizationResult:
        """
        Find the minimum variance portfolio.
        
        Args:
            prices: Price DataFrame.
            expected_returns_method: Method for expected returns.
            risk_model: Covariance estimation method.
        
        Returns:
            OptimizationResult for minimum variance portfolio.
        """
        return self.optimize(
            prices,
            method='min_volatility',
            expected_returns_method=expected_returns_method,
            risk_model=risk_model
        )
    
    def get_maximum_sharpe(
        self,
        prices: pd.DataFrame,
        expected_returns_method: str = 'mean_historical_return',
        risk_model: str = 'sample_cov'
    ) -> OptimizationResult:
        """
        Find the maximum Sharpe ratio portfolio.
        
        Args:
            prices: Price DataFrame.
            expected_returns_method: Method for expected returns.
            risk_model: Covariance estimation method.
        
        Returns:
            OptimizationResult for maximum Sharpe portfolio.
        """
        return self.optimize(
            prices,
            method='max_sharpe',
            expected_returns_method=expected_returns_method,
            risk_model=risk_model
        )
