"""
Black-Litterman Portfolio Optimization.

This module implements the Black-Litterman model which combines market
equilibrium returns with investor views to produce posterior expected returns.
"""

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from pypfopt import BlackLittermanModel, EfficientFrontier, risk_models
from pypfopt.black_litterman import market_implied_prior_returns

from .base import BaseOptimizer, OptimizationResult


class BlackLittermanOptimizer(BaseOptimizer):
    """
    Black-Litterman portfolio optimization.
    
    Combines market equilibrium with investor views to produce optimal
    portfolio weights. The model addresses the limitations of traditional
    mean-variance optimization by:
    
    1. Starting with market equilibrium returns as a prior
    2. Incorporating investor views with specified confidence levels
    3. Producing posterior expected returns that blend both sources
    
    Example:
        >>> optimizer = BlackLittermanOptimizer(risk_free_rate=0.02)
        >>> optimizer.set_market_caps({'AAPL': 3000, 'MSFT': 2500})
        >>> optimizer.set_views({'AAPL': (0.15, 0.8)})  # 15% return, 80% confidence
        >>> result = optimizer.optimize(prices)
    
    Attributes:
        risk_free_rate: Annual risk-free rate.
        market_caps: Dictionary of market capitalizations.
        views: Dictionary of investor views.
        tau: Scaling parameter for prior covariance (default: 0.05).
    """
    
    def __init__(
        self,
        risk_free_rate: float = 0.02,
        tau: float = 0.05
    ):
        """
        Initialize the Black-Litterman optimizer.
        
        Args:
            risk_free_rate: Annual risk-free rate (default: 2%).
            tau: Scaling parameter for the prior covariance matrix.
                 Smaller values give more weight to market equilibrium.
        """
        super().__init__(risk_free_rate)
        self.tau = tau
        self._market_caps: Dict[str, float] = {}
        self._views: Dict[str, Tuple[float, float]] = {}
        self._omega: Optional[np.ndarray] = None
        self._bl_model: Optional[BlackLittermanModel] = None
    
    def set_views(self, views: Dict[str, Tuple[float, float]]) -> None:
        """
        Set investor views.
        
        Views are expressed as expected returns with confidence levels.
        The confidence level (0-1) determines how strongly the view
        influences the posterior returns.
        
        Args:
            views: Dictionary mapping symbol to (expected_return, confidence).
                   Expected return should be annualized (e.g., 0.15 for 15%).
                   Confidence should be between 0 and 1.
        
        Example:
            >>> optimizer.set_views({
            ...     'AAPL': (0.15, 0.8),   # Expect 15% return, 80% confident
            ...     'MSFT': (0.12, 0.6),   # Expect 12% return, 60% confident
            ... })
        """
        for symbol, (expected_return, confidence) in views.items():
            if not 0 <= confidence <= 1:
                raise ValueError(
                    f"Confidence must be between 0 and 1, got {confidence}"
                )
        self._views = views.copy()
    
    def add_view(self, symbol: str, expected_return: float, confidence: float) -> None:
        """
        Add a single investor view.
        
        Args:
            symbol: Asset symbol.
            expected_return: Expected annualized return.
            confidence: Confidence level (0-1).
        """
        if not 0 <= confidence <= 1:
            raise ValueError(
                f"Confidence must be between 0 and 1, got {confidence}"
            )
        self._views[symbol] = (expected_return, confidence)
    
    def clear_views(self) -> None:
        """Clear all investor views."""
        self._views.clear()
    
    def set_market_caps(self, market_caps: Dict[str, float]) -> None:
        """
        Set market capitalizations for calculating equilibrium returns.
        
        Market caps are used to determine market weights and calculate
        the implied equilibrium returns.
        
        Args:
            market_caps: Dictionary mapping symbol to market capitalization.
                        Values can be in any consistent unit (billions, millions, etc.)
        
        Example:
            >>> optimizer.set_market_caps({
            ...     'AAPL': 3000,  # $3000 billion
            ...     'MSFT': 2500,  # $2500 billion
            ... })
        """
        self._market_caps = market_caps.copy()
    
    def set_omega(self, omega: np.ndarray) -> None:
        """
        Set the uncertainty matrix for views directly.
        
        Omega represents the uncertainty in each view. Higher values
        indicate less confidence in the view.
        
        Args:
            omega: Diagonal matrix of view uncertainties.
        """
        self._omega = omega
    
    def optimize(
        self,
        prices: pd.DataFrame,
        market_prices: Optional[pd.Series] = None,
        risk_model: str = 'ledoit_wolf',
        method: str = 'max_sharpe'
    ) -> OptimizationResult:
        """
        Perform Black-Litterman optimization.
        
        Args:
            prices: DataFrame with assets as columns and dates as index.
            market_prices: Optional market prices for CAPM-based estimation.
            risk_model: Covariance estimation method.
            method: Optimization method - 'max_sharpe' or 'min_volatility'.
        
        Returns:
            OptimizationResult with optimal weights and metrics.
        
        Raises:
            ValueError: If price data is insufficient or views are invalid.
        """
        # Validate inputs
        self.validate_prices(prices)
        
        if method not in ('max_sharpe', 'min_volatility'):
            raise ValueError(
                f"Invalid method '{method}'. Use 'max_sharpe' or 'min_volatility'"
            )
        
        # Calculate covariance matrix
        cov_matrix = self._calculate_risk_model(prices, risk_model)
        
        # Build Black-Litterman model
        bl_model = self._build_bl_model(prices, cov_matrix, market_prices)
        
        # Get posterior returns and covariance
        posterior_returns = bl_model.bl_returns()
        posterior_cov = bl_model.bl_cov()
        
        # Optimize using posterior estimates
        ef = EfficientFrontier(posterior_returns, posterior_cov)
        
        try:
            if method == 'max_sharpe':
                weights = ef.max_sharpe(self.risk_free_rate)
            else:
                weights = ef.min_volatility()
        except Exception as e:
            raise ValueError(f"Optimization failed: {str(e)}") from e
        
        # Clean weights
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
            method_used=f"black_litterman_{method}",
            metadata={
                'tau': self.tau,
                'risk_model': risk_model,
                'num_views': len(self._views),
                'posterior_returns': posterior_returns.to_dict(),
                'views': self._views.copy()
            }
        )
        
        self._last_result = result
        self._bl_model = bl_model
        return result
    
    def _build_bl_model(
        self,
        prices: pd.DataFrame,
        cov_matrix: pd.DataFrame,
        market_prices: Optional[pd.Series] = None
    ) -> BlackLittermanModel:
        """
        Build the Black-Litterman model.
        
        Args:
            prices: Price DataFrame.
            cov_matrix: Covariance matrix.
            market_prices: Optional market prices.
        
        Returns:
            Configured BlackLittermanModel instance.
        """
        # Get asset list
        assets = list(prices.columns)
        
        # Calculate prior returns (market equilibrium)
        if self._market_caps:
            # Use market caps to calculate equilibrium returns
            market_caps_series = pd.Series(self._market_caps)
            # Ensure market caps align with price columns
            market_caps_aligned = market_caps_series.reindex(assets).fillna(0)
            
            prior_returns = market_implied_prior_returns(
                market_caps_aligned,
                self.risk_free_rate,
                cov_matrix
            )
        else:
            # Use historical mean as fallback prior
            prior_returns = prices.pct_change().mean() * 252  # Annualize
        
        # Build views if provided
        if self._views:
            # Create view matrix P and view returns Q
            view_assets = list(self._views.keys())
            
            # Validate view assets exist in price data
            missing_assets = set(view_assets) - set(assets)
            if missing_assets:
                raise ValueError(
                    f"View assets not found in price data: {missing_assets}"
                )
            
            # Build P matrix (pick matrix) - absolute views
            P = np.zeros((len(view_assets), len(assets)))
            Q = np.zeros(len(view_assets))
            
            for i, asset in enumerate(view_assets):
                asset_idx = assets.index(asset)
                P[i, asset_idx] = 1.0
                Q[i] = self._views[asset][0]  # Expected return
            
            # Build omega (uncertainty matrix) from confidence levels
            if self._omega is None:
                omega = self._calculate_omega_from_confidence(
                    P, cov_matrix, view_assets
                )
            else:
                omega = self._omega
            
            # Create Black-Litterman model
            bl_model = BlackLittermanModel(
                cov_matrix,
                pi=prior_returns,
                Q=Q,
                P=P,
                omega=omega,
                tau=self.tau
            )
        else:
            # No views - use prior returns only
            bl_model = BlackLittermanModel(
                cov_matrix,
                pi=prior_returns,
                tau=self.tau
            )
        
        return bl_model
    
    def _calculate_omega_from_confidence(
        self,
        P: np.ndarray,
        cov_matrix: pd.DataFrame,
        view_assets: list
    ) -> np.ndarray:
        """
        Calculate omega matrix from confidence levels.
        
        Uses the Idzorek method to convert confidence levels (0-1)
        to omega values. Higher confidence = lower omega.
        
        Args:
            P: Pick matrix.
            cov_matrix: Covariance matrix.
            view_assets: List of assets with views.
        
        Returns:
            Diagonal omega matrix.
        """
        n_views = len(view_assets)
        omega = np.zeros((n_views, n_views))
        
        # Scale factor based on tau and covariance
        tau_cov = self.tau * cov_matrix.values
        
        for i, asset in enumerate(view_assets):
            confidence = self._views[asset][1]
            # Base uncertainty from covariance
            asset_idx = list(cov_matrix.columns).index(asset)
            base_uncertainty = tau_cov[asset_idx, asset_idx]
            
            # Adjust based on confidence
            # Higher confidence -> lower omega
            # confidence = 1 -> omega = 0 (certain view)
            # confidence = 0 -> omega = infinity (ignored view)
            if confidence >= 0.99:
                omega[i, i] = 1e-10  # Near-certain view
            elif confidence <= 0.01:
                omega[i, i] = 1e10  # Effectively ignored
            else:
                # Scale uncertainty inversely with confidence
                omega[i, i] = base_uncertainty * (1 - confidence) / confidence
        
        return omega
    
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
        if method == 'ledoit_wolf':
            return risk_models.CovarianceShrinkage(prices).ledoit_wolf()
        elif method == 'sample_cov':
            return risk_models.sample_cov(prices)
        elif method == 'exp_cov':
            return risk_models.exp_cov(prices)
        else:
            raise ValueError(f"Unknown risk model: {method}")
    
    def get_posterior_returns(self) -> Optional[pd.Series]:
        """
        Get the posterior expected returns from the last optimization.
        
        Returns:
            Series of posterior returns or None if not yet optimized.
        """
        if self._bl_model is None:
            return None
        return self._bl_model.bl_returns()
    
    def get_posterior_covariance(self) -> Optional[pd.DataFrame]:
        """
        Get the posterior covariance matrix from the last optimization.
        
        Returns:
            DataFrame of posterior covariance or None if not yet optimized.
        """
        if self._bl_model is None:
            return None
        return self._bl_model.bl_cov()
    
    def get_market_implied_returns(
        self,
        prices: pd.DataFrame,
        risk_model: str = 'ledoit_wolf'
    ) -> pd.Series:
        """
        Calculate market-implied equilibrium returns.
        
        These are the returns that would make the market portfolio
        optimal under mean-variance optimization.
        
        Args:
            prices: Price DataFrame.
            risk_model: Covariance estimation method.
        
        Returns:
            Series of implied equilibrium returns.
        """
        self.validate_prices(prices)
        
        if not self._market_caps:
            raise ValueError(
                "Market caps must be set to calculate implied returns"
            )
        
        cov_matrix = self._calculate_risk_model(prices, risk_model)
        assets = list(prices.columns)
        market_caps_series = pd.Series(self._market_caps)
        market_caps_aligned = market_caps_series.reindex(assets).fillna(0)
        
        return market_implied_prior_returns(
            market_caps_aligned,
            self.risk_free_rate,
            cov_matrix
        )
