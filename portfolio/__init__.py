"""
Portfolio Optimization Module.

This module provides portfolio optimization tools including:
- Mean-Variance optimization
- Black-Litterman model
- Risk metrics calculation
- Portfolio constraints

Example:
    >>> from portfolio import PortfolioOptimizer, RiskCalculator
    >>> 
    >>> # Create optimizer
    >>> optimizer = PortfolioOptimizer(method='black_litterman')
    >>> optimizer.add_views({'AAPL': (0.15, 0.8)})
    >>> optimizer.set_market_caps({'AAPL': 3000, 'MSFT': 2500})
    >>> 
    >>> # Run optimization
    >>> result = optimizer.run(prices)
    >>> print(result.weights)
    >>> 
    >>> # Calculate risk metrics
    >>> returns = prices.pct_change().dropna()
    >>> metrics = RiskCalculator.calculate_all_metrics(returns)
"""

# Base classes and types
from .base import (
    BaseOptimizer,
    OptimizationResult,
    RiskMetrics,
)

# Optimization strategies
from .mean_variance import MeanVarianceOptimizer
from .black_litterman import BlackLittermanOptimizer

# Risk calculations
from .risk import RiskCalculator

# Constraints
from .constraints import (
    Constraint,
    ConstraintsBuilder,
    validate_weights,
)

# Unified interface
from .optimizer import PortfolioOptimizer

# Public API
__all__ = [
    # Base classes
    'BaseOptimizer',
    'OptimizationResult',
    'RiskMetrics',
    
    # Optimizers
    'MeanVarianceOptimizer',
    'BlackLittermanOptimizer',
    'PortfolioOptimizer',
    
    # Risk
    'RiskCalculator',
    
    # Constraints
    'Constraint',
    'ConstraintsBuilder',
    'validate_weights',
]

__version__ = '1.0.0'
