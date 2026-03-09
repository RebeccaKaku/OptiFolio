"""
Data cleaning module for OHLCV data.

This module provides the DataCleaner class for handling data quality issues
including missing values, outliers, and gaps in time series data.
"""

from typing import Optional, Literal
import pandas as pd
import numpy as np

from .base import ProcessingStep


class DataCleaner(ProcessingStep):
    """
    Data cleaner for OHLCV data.
    
    Handles data quality issues:
    - Missing values (drop, forward fill, interpolate)
    - Outliers (IQR, z-score methods)
    - Gaps in time series
    - OHLCV data integrity validation
    
    Example:
        >>> cleaner = DataCleaner()
        >>> clean_df = cleaner.process(raw_df)
        >>> # Or use individual methods
        >>> df = cleaner.handle_missing_values(df, method='ffill')
        >>> df = cleaner.remove_outliers(df, method='iqr', threshold=1.5)
    """
    
    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply default cleaning operations.
        
        This method applies:
        1. OHLCV validation
        2. Missing value handling (forward fill)
        3. Gap filling (up to 5 days)
        
        Args:
            df: Input DataFrame with OHLCV data.
        
        Returns:
            Cleaned DataFrame.
        """
        result = df.copy()
        
        # Validate OHLCV integrity first
        result = self.validate_ohlcv(result)
        
        # Handle missing values with forward fill
        result = self.handle_missing_values(result, method='ffill')
        
        # Fill small gaps
        result = self.fill_gaps(result, max_gap_days=5)
        
        return result
    
    def handle_missing_values(
        self,
        df: pd.DataFrame,
        method: Literal['ffill', 'bfill', 'drop', 'interpolate', 'mean'] = 'ffill',
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Handle missing values in OHLCV data.
        
        Args:
            df: Input DataFrame with OHLCV data.
            method: Method to handle missing values:
                - 'ffill': Forward fill (use previous valid value)
                - 'bfill': Backward fill (use next valid value)
                - 'drop': Drop rows with missing values
                - 'interpolate': Linear interpolation
                - 'mean': Fill with column mean
            limit: Maximum number of consecutive missing values to fill.
                Only applicable for 'ffill', 'bfill', 'interpolate'.
        
        Returns:
            DataFrame with missing values handled.
        """
        result = df.copy()
        ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
        
        # Ensure we're working with lowercase column names
        col_map = {col.lower(): col for col in result.columns}
        
        for col in ohlcv_cols:
            if col not in col_map:
                continue
            
            actual_col = col_map[col]
            
            if method == 'ffill':
                result[actual_col] = result[actual_col].ffill(limit=limit)
            elif method == 'bfill':
                result[actual_col] = result[actual_col].bfill(limit=limit)
            elif method == 'drop':
                result = result.dropna(subset=[actual_col])
            elif method == 'interpolate':
                result[actual_col] = result[actual_col].interpolate(
                    method='linear', limit=limit
                )
            elif method == 'mean':
                mean_val = result[actual_col].mean()
                result[actual_col] = result[actual_col].fillna(mean_val)
        
        return result
    
    def remove_outliers(
        self,
        df: pd.DataFrame,
        method: Literal['iqr', 'zscore'] = 'iqr',
        threshold: float = 3.0
    ) -> pd.DataFrame:
        """
        Remove price outliers from OHLCV data.
        
        For IQR method, threshold is the IQR multiplier (default 1.5 for typical outliers,
        3.0 for extreme outliers).
        For z-score method, threshold is the number of standard deviations.
        
        Note: This method identifies outliers in the 'close' price and removes
        those entire rows. Volume outliers are not removed as they may be legitimate.
        
        Args:
            df: Input DataFrame with OHLCV data.
            method: Outlier detection method:
                - 'iqr': Interquartile range method
                - 'zscore': Z-score method
            threshold: Threshold for outlier detection.
                For IQR: multiplier (1.5 = typical, 3.0 = extreme)
                For zscore: number of standard deviations
        
        Returns:
            DataFrame with outliers removed.
        """
        result = df.copy()
        
        # Get the close price column (case-insensitive)
        close_col = None
        for col in result.columns:
            if col.lower() == 'close':
                close_col = col
                break
        
        if close_col is None:
            return result
        
        close_prices = result[close_col]
        
        if method == 'iqr':
            q1 = close_prices.quantile(0.25)
            q3 = close_prices.quantile(0.75)
            iqr = q3 - q1
            
            lower_bound = q1 - threshold * iqr
            upper_bound = q3 + threshold * iqr
            
            # Keep rows where close price is within bounds
            mask = (close_prices >= lower_bound) & (close_prices <= upper_bound)
            result = result[mask]
            
        elif method == 'zscore':
            mean = close_prices.mean()
            std = close_prices.std()
            
            if std > 0:
                z_scores = np.abs((close_prices - mean) / std)
                mask = z_scores <= threshold
                result = result[mask]
        
        return result
    
    def fill_gaps(
        self,
        df: pd.DataFrame,
        max_gap_days: int = 5
    ) -> pd.DataFrame:
        """
        Fill gaps in time series data.
        
        This method reindexes the DataFrame to include all dates in the range
        and fills small gaps (up to max_gap_days) using forward fill.
        Larger gaps are left as NaN.
        
        Args:
            df: Input DataFrame with OHLCV data.
            max_gap_days: Maximum gap size (in days) to fill.
        
        Returns:
            DataFrame with small gaps filled.
        """
        if df.empty:
            return df
        
        result = df.copy()
        
        # Ensure the index is a DatetimeIndex
        if not isinstance(result.index, pd.DatetimeIndex):
            return result
        
        # Get the date range
        date_range = pd.date_range(
            start=result.index.min(),
            end=result.index.max(),
            freq='D'
        )
        
        # Reindex to include all dates
        result = result.reindex(date_range)
        
        # Identify gaps
        is_null = result.isnull().any(axis=1)
        
        # Group consecutive nulls to find gap sizes
        gap_groups = (is_null != is_null.shift()).cumsum()
        
        for group_id, group_mask in is_null.groupby(gap_groups):
            if not group_mask.iloc[0]:
                continue
            
            gap_size = len(group_mask)
            
            if gap_size <= max_gap_days:
                # Fill small gaps with forward fill
                start_idx = group_mask.index[0]
                end_idx = group_mask.index[-1]
                
                # Get the last valid value before the gap
                before_gap = result.loc[:start_idx - pd.Timedelta(days=1)]
                if not before_gap.empty:
                    last_valid = before_gap.iloc[-1]
                    # Forward fill the gap
                    for col in result.columns:
                        result.loc[start_idx:end_idx, col] = last_valid[col]
        
        return result
    
    def validate_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Validate OHLCV data integrity.
        
        Checks performed:
        1. High >= Low for all rows
        2. Open is within [Low, High] range
        3. Close is within [Low, High] range
        4. All prices are positive
        
        Invalid rows are removed from the DataFrame.
        
        Args:
            df: Input DataFrame with OHLCV data.
        
        Returns:
            DataFrame with invalid rows removed.
        """
        result = df.copy()
        
        # Get column names (case-insensitive)
        col_map = {col.lower(): col for col in result.columns}
        
        required_cols = ['open', 'high', 'low', 'close']
        for col in required_cols:
            if col not in col_map:
                return result  # Return as-is if columns missing
        
        open_col = col_map['open']
        high_col = col_map['high']
        low_col = col_map['low']
        close_col = col_map['close']
        
        # Create validation mask
        valid_mask = pd.Series(True, index=result.index)
        
        # Check high >= low
        valid_mask &= (result[high_col] >= result[low_col])
        
        # Check open is within [low, high]
        valid_mask &= (result[open_col] >= result[low_col])
        valid_mask &= (result[open_col] <= result[high_col])
        
        # Check close is within [low, high]
        valid_mask &= (result[close_col] >= result[low_col])
        valid_mask &= (result[close_col] <= result[high_col])
        
        # Check all prices are positive
        for col in [open_col, high_col, low_col, close_col]:
            valid_mask &= (result[col] > 0)
        
        # Check volume is non-negative if present
        if 'volume' in col_map:
            volume_col = col_map['volume']
            valid_mask &= (result[volume_col] >= 0)
        
        return result[valid_mask]
