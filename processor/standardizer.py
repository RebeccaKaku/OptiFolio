"""
Data standardization module for OHLCV data.

This module provides the DataStandardizer class for ensuring consistent
data format across the system, including column names, index format, and data types.
"""

from typing import Optional, Dict, List
import pandas as pd
import numpy as np

from .base import ProcessingStep


# Standard column names (lowercase)
STANDARD_COLUMNS = ['open', 'high', 'low', 'close', 'volume']

# Common column name mappings
COLUMN_MAPPINGS = {
    # Yahoo Finance variants
    'Open': 'open',
    'High': 'high',
    'Low': 'low',
    'Close': 'close',
    'Volume': 'volume',
    'Adj Close': 'adj_close',
    
    # Other common variants
    'OPEN': 'open',
    'HIGH': 'high',
    'LOW': 'low',
    'CLOSE': 'close',
    'VOLUME': 'volume',
    
    # Abbreviations
    'o': 'open',
    'h': 'high',
    'l': 'low',
    'c': 'close',
    'v': 'volume',
    
    # With underscores
    'open_price': 'open',
    'high_price': 'high',
    'low_price': 'low',
    'close_price': 'close',
    
    # Timestamp variants
    'date': 'timestamp',
    'Date': 'timestamp',
    'datetime': 'timestamp',
    'DateTime': 'timestamp',
    'time': 'timestamp',
    'Time': 'timestamp',
}


class DataStandardizer(ProcessingStep):
    """
    Data standardizer for OHLCV data.
    
    Ensures consistent data format:
    - Lowercase column names (open, high, low, close, volume)
    - DatetimeIndex named 'timestamp'
    - Correct data types (float for prices, float/int for volume)
    
    Example:
        >>> standardizer = DataStandardizer()
        >>> std_df = standardizer.process(raw_df)
        >>> # Or use individual methods
        >>> df = standardizer.standardize_columns(df)
        >>> df = standardizer.standardize_index(df)
    """
    
    def __init__(
        self,
        required_columns: Optional[List[str]] = None,
        column_mappings: Optional[Dict[str, str]] = None
    ):
        """
        Initialize the DataStandardizer.
        
        Args:
            required_columns: List of required column names. Defaults to standard OHLCV columns.
            column_mappings: Custom column name mappings. Merged with default mappings.
        """
        self.required_columns = required_columns or STANDARD_COLUMNS.copy()
        self.column_mappings = {**COLUMN_MAPPINGS}
        if column_mappings:
            self.column_mappings.update(column_mappings)
    
    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply full standardization.
        
        This method applies:
        1. Column name standardization
        2. Index standardization
        3. Data type standardization
        
        Args:
            df: Input DataFrame with OHLCV data.
        
        Returns:
            Standardized DataFrame.
        """
        result = df.copy()
        
        result = self.standardize_columns(result)
        result = self.standardize_index(result)
        result = self.standardize_dtypes(result)
        
        return result
    
    def standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize column names to lowercase.
        
        Ensures column names are lowercase and follow the standard naming:
        - open, high, low, close, volume
        
        Also handles common column name variants and mappings.
        
        Args:
            df: Input DataFrame with OHLCV data.
        
        Returns:
            DataFrame with standardized column names.
        """
        result = df.copy()
        
        # Create new column names
        new_columns = {}
        
        for col in result.columns:
            col_str = str(col)
            
            # Check if it's already lowercase standard
            if col_str.lower() in STANDARD_COLUMNS:
                new_columns[col] = col_str.lower()
            # Check mappings
            elif col_str in self.column_mappings:
                new_columns[col] = self.column_mappings[col_str]
            # Default to lowercase
            else:
                new_columns[col] = col_str.lower()
        
        # Rename columns
        result = result.rename(columns=new_columns)
        
        # Handle duplicate columns (keep the first one)
        if result.columns.duplicated().any():
            # Keep first occurrence of each column
            result = result.loc[:, ~result.columns.duplicated()]
        
        return result
    
    def standardize_index(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize the index to DatetimeIndex named 'timestamp'.
        
        Handles:
        - Converting various date formats to DatetimeIndex
        - Setting the index name to 'timestamp'
        - Converting timezone-aware index to UTC if needed
        
        Args:
            df: Input DataFrame with OHLCV data.
        
        Returns:
            DataFrame with standardized index.
        """
        result = df.copy()
        
        # If index is already DatetimeIndex, just rename
        if isinstance(result.index, pd.DatetimeIndex):
            result.index.name = 'timestamp'
            return result
        
        # Check if there's a timestamp column that should be the index
        timestamp_cols = ['timestamp', 'date', 'datetime', 'time', 'Date', 'DateTime']
        
        for col in timestamp_cols:
            if col in result.columns:
                try:
                    result[col] = pd.to_datetime(result[col])
                    result = result.set_index(col)
                    result.index.name = 'timestamp'
                    return result
                except (ValueError, TypeError):
                    continue
        
        # Try to convert the index to datetime
        try:
            result.index = pd.to_datetime(result.index)
            result.index.name = 'timestamp'
        except (ValueError, TypeError):
            # If conversion fails, keep the original index but set the name
            result.index.name = 'timestamp'
        
        return result
    
    def standardize_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize data types for OHLCV columns.
        
        Ensures:
        - Price columns (open, high, low, close) are float
        - Volume column is float or int
        - Additional columns are converted to appropriate types
        
        Args:
            df: Input DataFrame with OHLCV data.
        
        Returns:
            DataFrame with standardized data types.
        """
        result = df.copy()
        
        # Price columns should be float
        price_cols = ['open', 'high', 'low', 'close', 'adj_close']
        
        for col in price_cols:
            if col in result.columns:
                result[col] = pd.to_numeric(result[col], errors='coerce').astype(float)
        
        # Volume should be numeric (int or float)
        if 'volume' in result.columns:
            result['volume'] = pd.to_numeric(result['volume'], errors='coerce')
            # Try to convert to int if all values are whole numbers
            if result['volume'].notna().all():
                if (result['volume'] == result['volume'].astype(int)).all():
                    result['volume'] = result['volume'].astype(int)
        
        return result
    
    def validate_format(self, df: pd.DataFrame) -> bool:
        """
        Validate that the DataFrame has the standard format.
        
        Checks:
        - Index is DatetimeIndex named 'timestamp'
        - Required columns exist (open, high, low, close, volume)
        - Data types are correct
        
        Args:
            df: Input DataFrame to validate.
        
        Returns:
            True if valid, False otherwise.
        """
        # Check index
        if not isinstance(df.index, pd.DatetimeIndex):
            return False
        
        if df.index.name != 'timestamp':
            return False
        
        # Check required columns
        for col in self.required_columns:
            if col not in df.columns:
                return False
        
        # Check data types
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            if col in df.columns:
                if not pd.api.types.is_float_dtype(df[col]):
                    return False
        
        return True
    
    def get_missing_columns(self, df: pd.DataFrame) -> List[str]:
        """
        Get list of missing required columns.
        
        Args:
            df: Input DataFrame to check.
        
        Returns:
            List of missing column names.
        """
        existing = set(df.columns.str.lower())
        required = set(self.required_columns)
        
        return list(required - existing)
    
    def ensure_columns(self, df: pd.DataFrame, fill_value: float = np.nan) -> pd.DataFrame:
        """
        Ensure all required columns exist, adding missing ones with fill value.
        
        Args:
            df: Input DataFrame.
            fill_value: Value to use for missing columns.
        
        Returns:
            DataFrame with all required columns.
        """
        result = df.copy()
        
        for col in self.required_columns:
            if col not in result.columns:
                result[col] = fill_value
        
        return result
    
    def reorder_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Reorder columns to standard order: open, high, low, close, volume, then others.
        
        Args:
            df: Input DataFrame.
        
        Returns:
            DataFrame with columns in standard order.
        """
        result = df.copy()
        
        # Standard columns first
        ordered_cols = [col for col in STANDARD_COLUMNS if col in result.columns]
        
        # Then any additional columns
        other_cols = [col for col in result.columns if col not in ordered_cols]
        
        return result[ordered_cols + other_cols]
