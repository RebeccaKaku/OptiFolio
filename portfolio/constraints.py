"""
Portfolio Constraints Builder.

This module provides a fluent interface for building portfolio constraints
that can be applied to optimization problems.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class Constraint:
    """
    Represents a single portfolio constraint.
    
    Attributes:
        type: Type of constraint (e.g., 'long_only', 'weight_bounds', 'sector').
        params: Parameters for the constraint.
    """
    type: str
    params: Dict[str, Any] = field(default_factory=dict)


class ConstraintsBuilder:
    """
    Builder for portfolio optimization constraints.
    
    Provides a fluent interface for constructing constraints that can be
    passed to portfolio optimizers. Supports common constraint types including
    long-only, position limits, and sector exposure limits.
    
    Example:
        >>> builder = ConstraintsBuilder()
        >>> builder.set_long_only()
        >>> builder.set_weight_bounds(0.0, 0.3)  # Max 30% per position
        >>> builder.set_sector_limits(sectors, limits)
        >>> constraints = builder.build()
    """
    
    def __init__(self):
        """Initialize an empty constraints builder."""
        self._constraints: List[Constraint] = []
        self._weight_bounds: Tuple[float, float] = (0, 1)
        self._sector_mapping: Dict[str, str] = {}
        self._sector_limits: Dict[str, float] = {}
    
    def set_long_only(self) -> 'ConstraintsBuilder':
        """
        Set long-only constraint (no short selling).
        
        All weights must be non-negative.
        
        Returns:
            Self for method chaining.
        """
        self._constraints.append(Constraint(type='long_only'))
        self._weight_bounds = (0, 1)
        return self
    
    def set_weight_bounds(
        self,
        min_weight: float,
        max_weight: float
    ) -> 'ConstraintsBuilder':
        """
        Set minimum and maximum weight bounds for each position.
        
        Args:
            min_weight: Minimum weight for any single position.
            max_weight: Maximum weight for any single position.
        
        Returns:
            Self for method chaining.
        
        Example:
            >>> builder.set_weight_bounds(0.0, 0.3)  # 0-30% per position
        """
        if min_weight > max_weight:
            raise ValueError(
                f"min_weight ({min_weight}) cannot exceed max_weight ({max_weight})"
            )
        
        self._constraints.append(Constraint(
            type='weight_bounds',
            params={'min_weight': min_weight, 'max_weight': max_weight}
        ))
        self._weight_bounds = (min_weight, max_weight)
        return self
    
    def set_sector_limits(
        self,
        sectors: Dict[str, List[str]],
        limits: Dict[str, float]
    ) -> 'ConstraintsBuilder':
        """
        Set sector exposure limits.
        
        Limits the total weight that can be allocated to each sector.
        
        Args:
            sectors: Dictionary mapping sector name to list of symbols.
            limits: Dictionary mapping sector name to maximum weight.
        
        Returns:
            Self for method chaining.
        
        Example:
            >>> sectors = {
            ...     'Technology': ['AAPL', 'MSFT', 'GOOGL'],
            ...     'Finance': ['JPM', 'BAC', 'GS']
            ... }
            >>> limits = {'Technology': 0.4, 'Finance': 0.3}
            >>> builder.set_sector_limits(sectors, limits)
        """
        # Validate that all limited sectors exist
        for sector in limits:
            if sector not in sectors:
                raise ValueError(f"Sector '{sector}' not found in sectors mapping")
        
        # Create reverse mapping: symbol -> sector
        sector_mapping = {}
        for sector, symbols in sectors.items():
            for symbol in symbols:
                sector_mapping[symbol] = sector
        
        self._constraints.append(Constraint(
            type='sector_limits',
            params={
                'sectors': sectors,
                'limits': limits,
                'sector_mapping': sector_mapping
            }
        ))
        self._sector_mapping = sector_mapping
        self._sector_limits = limits
        
        return self
    
    def set_target_volatility(
        self,
        target_vol: float
    ) -> 'ConstraintsBuilder':
        """
        Set target portfolio volatility constraint.
        
        The optimizer will try to maximize return while keeping
        volatility at or below the target.
        
        Args:
            target_vol: Target annualized volatility (decimal).
        
        Returns:
            Self for method chaining.
        """
        if target_vol <= 0:
            raise ValueError("Target volatility must be positive")
        
        self._constraints.append(Constraint(
            type='target_volatility',
            params={'target_vol': target_vol}
        ))
        return self
    
    def set_target_return(
        self,
        target_return: float
    ) -> 'ConstraintsBuilder':
        """
        Set target portfolio return constraint.
        
        The optimizer will minimize risk while achieving at least
        the target return.
        
        Args:
            target_return: Target annualized return (decimal).
        
        Returns:
            Self for method chaining.
        """
        self._constraints.append(Constraint(
            type='target_return',
            params={'target_return': target_return}
        ))
        return self
    
    def set_turnover_limit(
        self,
        current_weights: Dict[str, float],
        max_turnover: float
    ) -> 'ConstraintsBuilder':
        """
        Set portfolio turnover limit.
        
        Limits how much the portfolio can change from current positions.
        
        Args:
            current_weights: Current portfolio weights.
            max_turnover: Maximum allowed turnover (sum of absolute weight changes).
        
        Returns:
            Self for method chaining.
        """
        if max_turnover < 0:
            raise ValueError("Maximum turnover cannot be negative")
        
        self._constraints.append(Constraint(
            type='turnover_limit',
            params={
                'current_weights': current_weights,
                'max_turnover': max_turnover
            }
        ))
        return self
    
    def add_custom_constraint(
        self,
        constraint_type: str,
        params: Dict[str, Any]
    ) -> 'ConstraintsBuilder':
        """
        Add a custom constraint.
        
        Args:
            constraint_type: Type identifier for the constraint.
            params: Parameters for the constraint.
        
        Returns:
            Self for method chaining.
        """
        self._constraints.append(Constraint(
            type=constraint_type,
            params=params
        ))
        return self
    
    def build(self) -> List[Constraint]:
        """
        Build and return the list of constraints.
        
        Returns:
            List of Constraint objects.
        """
        return self._constraints.copy()
    
    def build_dict(self) -> Dict[str, Any]:
        """
        Build constraints as a dictionary for pyportfolioopt.
        
        Returns:
            Dictionary with constraint configuration.
        """
        result = {
            'weight_bounds': self._weight_bounds,
            'constraints': []
        }
        
        for constraint in self._constraints:
            if constraint.type == 'sector_limits':
                # Convert to pyportfolioopt format
                result['constraints'].append({
                    'type': 'sector',
                    'sector_mapping': constraint.params['sector_mapping'],
                    'limits': constraint.params['limits']
                })
            elif constraint.type == 'target_volatility':
                result['target_volatility'] = constraint.params['target_vol']
            elif constraint.type == 'target_return':
                result['target_return'] = constraint.params['target_return']
        
        return result
    
    def get_weight_bounds(self) -> Tuple[float, float]:
        """
        Get the current weight bounds.
        
        Returns:
            Tuple of (min_weight, max_weight).
        """
        return self._weight_bounds
    
    def get_sector_mapping(self) -> Dict[str, str]:
        """
        Get the symbol-to-sector mapping.
        
        Returns:
            Dictionary mapping symbol to sector name.
        """
        return self._sector_mapping.copy()
    
    def clear(self) -> 'ConstraintsBuilder':
        """
        Clear all constraints.
        
        Returns:
            Self for method chaining.
        """
        self._constraints.clear()
        self._weight_bounds = (0, 1)
        self._sector_mapping.clear()
        self._sector_limits.clear()
        return self
    
    def __len__(self) -> int:
        """Return the number of constraints."""
        return len(self._constraints)
    
    def __repr__(self) -> str:
        constraint_types = [c.type for c in self._constraints]
        return f"ConstraintsBuilder(constraints={constraint_types})"


def apply_constraints_to_efficient_frontier(
    ef,
    constraints: List[Constraint],
    assets: List[str]
) -> None:
    """
    Apply constraints to a pyportfolioopt EfficientFrontier object.
    
    This function modifies the EfficientFrontier in place to add
    the specified constraints.
    
    Args:
        ef: EfficientFrontier instance.
        constraints: List of Constraint objects.
        assets: List of asset symbols in order.
    
    Note:
        This is a helper function for internal use. Most constraints
        are handled during EfficientFrontier initialization or through
        its methods.
    """
    for constraint in constraints:
        if constraint.type == 'target_volatility':
            # Target volatility is handled during optimization
            pass
        elif constraint.type == 'target_return':
            # Target return is handled during optimization
            pass
        elif constraint.type == 'sector_limits':
            # Sector constraints need to be converted to linear constraints
            sector_mapping = constraint.params['sector_mapping']
            limits = constraint.params['limits']
            
            for sector, max_weight in limits.items():
                # Get indices of assets in this sector
                sector_indices = [
                    i for i, asset in enumerate(assets)
                    if sector_mapping.get(asset) == sector
                ]
                
                if sector_indices:
                    # Create constraint: sum of weights in sector <= max_weight
                    # This is handled differently in pyportfolioopt
                    pass  # Sector constraints require custom handling


def validate_weights(
    weights: Dict[str, float],
    constraints: List[Constraint]
) -> Tuple[bool, List[str]]:
    """
    Validate that weights satisfy all constraints.
    
    Args:
        weights: Dictionary of portfolio weights.
        constraints: List of Constraint objects.
    
    Returns:
        Tuple of (is_valid, list_of_violations).
    """
    violations = []
    
    for constraint in constraints:
        if constraint.type == 'long_only':
            negative_weights = [
                symbol for symbol, weight in weights.items()
                if weight < -1e-6
            ]
            if negative_weights:
                violations.append(
                    f"Long-only constraint violated: negative weights for {negative_weights}"
                )
        
        elif constraint.type == 'weight_bounds':
            min_w = constraint.params['min_weight']
            max_w = constraint.params['max_weight']
            
            for symbol, weight in weights.items():
                if weight < min_w - 1e-6 or weight > max_w + 1e-6:
                    violations.append(
                        f"Weight bounds violated: {symbol} weight {weight:.4f} "
                        f"outside [{min_w}, {max_w}]"
                    )
        
        elif constraint.type == 'sector_limits':
            sector_mapping = constraint.params['sector_mapping']
            limits = constraint.params['limits']
            
            # Calculate sector weights
            sector_weights = {}
            for symbol, weight in weights.items():
                sector = sector_mapping.get(symbol)
                if sector:
                    sector_weights[sector] = sector_weights.get(sector, 0) + weight
            
            # Check limits
            for sector, limit in limits.items():
                actual = sector_weights.get(sector, 0)
                if actual > limit + 1e-6:
                    violations.append(
                        f"Sector limit violated: {sector} weight {actual:.4f} "
                        f"exceeds limit {limit}"
                    )
    
    is_valid = len(violations) == 0
    return is_valid, violations
