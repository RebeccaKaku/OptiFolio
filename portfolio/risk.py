"""
Risk Metrics Calculator.

This module provides static methods for calculating various portfolio
risk metrics including VaR, CVaR, Sharpe ratio, Sortino ratio, and more.
"""

from typing import Optional, Union

import numpy as np
import pandas as pd
from scipy import stats


class RiskCalculator:
    """
    Calculator for portfolio risk metrics.
    
    Provides static methods for calculating:
    - Value at Risk (VaR)
    - Conditional VaR (Expected Shortfall)
    - Sharpe ratio
    - Sortino ratio
    - Maximum drawdown
    - Volatility
    
    All methods are static and can be called directly without instantiation.
    
    Example:
        >>> returns = pd.Series([0.01, -0.02, 0.03, ...])
        >>> var = RiskCalculator.calculate_var(returns, confidence=0.95)
        >>> sharpe = RiskCalculator.calculate_sharpe(returns, risk_free_rate=0.02)
    """
    
    @staticmethod
    def calculate_var(
        returns: Union[pd.Series, np.ndarray],
        confidence: float = 0.95,
        method: str = 'historical'
    ) -> float:
        """
        Calculate Value at Risk (VaR).
        
        VaR estimates the maximum potential loss over a given time period
        at a specified confidence level.
        
        Args:
            returns: Series or array of returns (decimal format, e.g., 0.01 for 1%).
            confidence: Confidence level (default: 0.95 for 95% VaR).
            method: Calculation method - 'historical', 'parametric', or 'cornish_fisher'.
        
        Returns:
            VaR as a positive number representing the potential loss.
        
        Example:
            >>> returns = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
            >>> var = RiskCalculator.calculate_var(returns, confidence=0.95)
            >>> print(f"95% VaR: {var:.2%}")
        """
        if isinstance(returns, pd.Series):
            returns = returns.dropna().values
        else:
            returns = returns[~np.isnan(returns)]
        
        if len(returns) == 0:
            return 0.0
        
        if method == 'historical':
            # Historical simulation method
            alpha = 1 - confidence
            var = -np.percentile(returns, alpha * 100)
        
        elif method == 'parametric':
            # Parametric method (assumes normal distribution)
            mean = np.mean(returns)
            std = np.std(returns, ddof=1)
            z_score = stats.norm.ppf(1 - confidence)
            var = -(mean + z_score * std)
        
        elif method == 'cornish_fisher':
            # Cornish-Fisher expansion (adjusts for skewness and kurtosis)
            mean = np.mean(returns)
            std = np.std(returns, ddof=1)
            skew = stats.skew(returns)
            kurt = stats.kurtosis(returns)
            
            # Cornish-Fisher z-score
            z = stats.norm.ppf(1 - confidence)
            z_cf = (z + 
                    (z**2 - 1) * skew / 6 + 
                    (z**3 - 3 * z) * kurt / 24 - 
                    (2 * z**3 - 5 * z) * skew**2 / 36)
            
            var = -(mean + z_cf * std)
        
        else:
            raise ValueError(
                f"Unknown method: {method}. Use 'historical', 'parametric', or 'cornish_fisher'"
            )
        
        return max(var, 0.0)  # VaR is reported as positive loss
    
    @staticmethod
    def calculate_cvar(
        returns: Union[pd.Series, np.ndarray],
        confidence: float = 0.95,
        method: str = 'historical'
    ) -> float:
        """
        Calculate Conditional Value at Risk (CVaR) / Expected Shortfall.
        
        CVaR is the expected loss given that the loss exceeds VaR.
        It provides a more complete picture of tail risk than VaR.
        
        Args:
            returns: Series or array of returns.
            confidence: Confidence level (default: 0.95).
            method: Calculation method - 'historical' or 'parametric'.
        
        Returns:
            CVaR as a positive number representing the expected loss in tail.
        
        Example:
            >>> returns = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
            >>> cvar = RiskCalculator.calculate_cvar(returns, confidence=0.95)
            >>> print(f"95% CVaR: {cvar:.2%}")
        """
        if isinstance(returns, pd.Series):
            returns = returns.dropna().values
        else:
            returns = returns[~np.isnan(returns)]
        
        if len(returns) == 0:
            return 0.0
        
        if method == 'historical':
            # Historical simulation method
            alpha = 1 - confidence
            var_threshold = np.percentile(returns, alpha * 100)
            # Average of returns below VaR threshold
            tail_returns = returns[returns <= var_threshold]
            cvar = -np.mean(tail_returns) if len(tail_returns) > 0 else 0.0
        
        elif method == 'parametric':
            # Parametric method (assumes normal distribution)
            mean = np.mean(returns)
            std = np.std(returns, ddof=1)
            alpha = 1 - confidence
            z_score = stats.norm.ppf(alpha)
            
            # CVaR formula for normal distribution
            cvar = -(mean + std * stats.norm.pdf(z_score) / alpha)
        
        else:
            raise ValueError(
                f"Unknown method: {method}. Use 'historical' or 'parametric'"
            )
        
        return max(cvar, 0.0)
    
    @staticmethod
    def calculate_sharpe(
        returns: Union[pd.Series, np.ndarray],
        risk_free_rate: float = 0.02,
        periods_per_year: int = 252
    ) -> float:
        """
        Calculate Sharpe ratio.
        
        The Sharpe ratio measures risk-adjusted return, calculated as
        the excess return per unit of volatility.
        
        Args:
            returns: Series or array of returns (decimal format).
            risk_free_rate: Annual risk-free rate (default: 2%).
            periods_per_year: Number of periods per year for annualization.
        
        Returns:
            Sharpe ratio. Higher is better.
        
        Example:
            >>> returns = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
            >>> sharpe = RiskCalculator.calculate_sharpe(returns, risk_free_rate=0.02)
            >>> print(f"Sharpe Ratio: {sharpe:.2f}")
        """
        if isinstance(returns, pd.Series):
            returns = returns.dropna().values
        else:
            returns = returns[~np.isnan(returns)]
        
        if len(returns) == 0:
            return 0.0
        
        # Convert annual risk-free rate to per-period
        rf_per_period = risk_free_rate / periods_per_year
        
        # Calculate excess returns
        excess_returns = returns - rf_per_period
        
        # Calculate Sharpe ratio
        mean_excess = np.mean(excess_returns)
        std_returns = np.std(returns, ddof=1)
        
        if std_returns == 0:
            return 0.0
        
        # Annualize
        sharpe = (mean_excess * periods_per_year) / (std_returns * np.sqrt(periods_per_year))
        
        return sharpe
    
    @staticmethod
    def calculate_sortino(
        returns: Union[pd.Series, np.ndarray],
        risk_free_rate: float = 0.02,
        periods_per_year: int = 252
    ) -> float:
        """
        Calculate Sortino ratio.
        
        The Sortino ratio is similar to the Sharpe ratio but only considers
        downside volatility, making it more appropriate for asymmetric returns.
        
        Args:
            returns: Series or array of returns.
            risk_free_rate: Annual risk-free rate.
            periods_per_year: Number of periods per year for annualization.
        
        Returns:
            Sortino ratio. Higher is better.
        
        Example:
            >>> returns = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
            >>> sortino = RiskCalculator.calculate_sortino(returns, risk_free_rate=0.02)
            >>> print(f"Sortino Ratio: {sortino:.2f}")
        """
        if isinstance(returns, pd.Series):
            returns = returns.dropna().values
        else:
            returns = returns[~np.isnan(returns)]
        
        if len(returns) == 0:
            return 0.0
        
        # Convert annual risk-free rate to per-period
        rf_per_period = risk_free_rate / periods_per_year
        
        # Calculate excess returns
        excess_returns = returns - rf_per_period
        
        # Calculate downside deviation
        negative_returns = returns[returns < 0]
        
        if len(negative_returns) == 0:
            # No negative returns - return a large positive number
            return float('inf')
        
        # Downside deviation (semi-deviation)
        downside_std = np.std(negative_returns, ddof=1)
        
        if downside_std == 0:
            return 0.0
        
        # Calculate Sortino ratio
        mean_excess = np.mean(excess_returns)
        
        # Annualize
        sortino = (mean_excess * periods_per_year) / (downside_std * np.sqrt(periods_per_year))
        
        return sortino
    
    @staticmethod
    def calculate_max_drawdown(
        returns: Union[pd.Series, np.ndarray],
        is_prices: bool = False
    ) -> float:
        """
        Calculate Maximum Drawdown.
        
        Maximum drawdown measures the largest peak-to-trough decline
        in the portfolio value.
        
        Args:
            returns: Series or array of returns or prices.
            is_prices: If True, input is treated as price series.
                      If False, input is treated as returns series.
        
        Returns:
            Maximum drawdown as a positive decimal (e.g., 0.20 for 20% drawdown).
        
        Example:
            >>> returns = pd.Series([0.01, -0.02, 0.03, -0.05, 0.02])
            >>> max_dd = RiskCalculator.calculate_max_drawdown(returns)
            >>> print(f"Maximum Drawdown: {max_dd:.2%}")
        """
        if isinstance(returns, pd.Series):
            returns = returns.dropna().values
        else:
            returns = returns[~np.isnan(returns)]
        
        if len(returns) == 0:
            return 0.0
        
        if is_prices:
            # Input is price series
            prices = returns
        else:
            # Convert returns to price series (starting at 100)
            prices = 100 * np.cumprod(1 + returns)
        
        # Calculate running maximum
        running_max = np.maximum.accumulate(prices)
        
        # Calculate drawdowns
        drawdowns = (running_max - prices) / running_max
        
        # Return maximum drawdown
        max_drawdown = np.max(drawdowns)
        
        return max_drawdown
    
    @staticmethod
    def calculate_volatility(
        returns: Union[pd.Series, np.ndarray],
        annualize: bool = True,
        periods_per_year: int = 252
    ) -> float:
        """
        Calculate volatility (standard deviation of returns).
        
        Args:
            returns: Series or array of returns.
            annualize: If True, annualize the volatility.
            periods_per_year: Number of periods per year for annualization.
        
        Returns:
            Volatility as decimal.
        
        Example:
            >>> returns = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
            >>> vol = RiskCalculator.calculate_volatility(returns, annualize=True)
            >>> print(f"Annualized Volatility: {vol:.2%}")
        """
        if isinstance(returns, pd.Series):
            returns = returns.dropna().values
        else:
            returns = returns[~np.isnan(returns)]
        
        if len(returns) == 0:
            return 0.0
        
        volatility = np.std(returns, ddof=1)
        
        if annualize:
            volatility *= np.sqrt(periods_per_year)
        
        return volatility
    
    @staticmethod
    def calculate_calmar(
        returns: Union[pd.Series, np.ndarray],
        periods_per_year: int = 252
    ) -> float:
        """
        Calculate Calmar ratio.
        
        The Calmar ratio is the annualized return divided by the
        maximum drawdown. It measures return per unit of drawdown risk.
        
        Args:
            returns: Series or array of returns.
            periods_per_year: Number of periods per year.
        
        Returns:
            Calmar ratio. Higher is better.
        """
        if isinstance(returns, pd.Series):
            returns = returns.dropna().values
        else:
            returns = returns[~np.isnan(returns)]
        
        if len(returns) == 0:
            return 0.0
        
        # Annualized return
        annual_return = np.mean(returns) * periods_per_year
        
        # Maximum drawdown
        max_dd = RiskCalculator.calculate_max_drawdown(returns)
        
        if max_dd == 0:
            return float('inf') if annual_return > 0 else 0.0
        
        return annual_return / max_dd
    
    @staticmethod
    def calculate_all_metrics(
        returns: Union[pd.Series, np.ndarray],
        risk_free_rate: float = 0.02,
        confidence: float = 0.95,
        periods_per_year: int = 252
    ) -> dict:
        """
        Calculate all risk metrics at once.
        
        Args:
            returns: Series or array of returns.
            risk_free_rate: Annual risk-free rate.
            confidence: Confidence level for VaR/CVaR.
            periods_per_year: Number of periods per year.
        
        Returns:
            Dictionary containing all calculated metrics.
        
        Example:
            >>> returns = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
            >>> metrics = RiskCalculator.calculate_all_metrics(returns)
            >>> for name, value in metrics.items():
            ...     print(f"{name}: {value:.4f}")
        """
        return {
            'volatility': RiskCalculator.calculate_volatility(
                returns, annualize=True, periods_per_year=periods_per_year
            ),
            'var': RiskCalculator.calculate_var(
                returns, confidence=confidence
            ),
            'cvar': RiskCalculator.calculate_cvar(
                returns, confidence=confidence
            ),
            'max_drawdown': RiskCalculator.calculate_max_drawdown(returns),
            'sharpe_ratio': RiskCalculator.calculate_sharpe(
                returns, risk_free_rate=risk_free_rate, periods_per_year=periods_per_year
            ),
            'sortino_ratio': RiskCalculator.calculate_sortino(
                returns, risk_free_rate=risk_free_rate, periods_per_year=periods_per_year
            ),
            'calmar_ratio': RiskCalculator.calculate_calmar(
                returns, periods_per_year=periods_per_year
            ),
            'annual_return': np.mean(returns) * periods_per_year if len(returns) > 0 else 0.0
        }
