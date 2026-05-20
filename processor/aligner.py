"""
Data alignment module for OHLCV data.

This module provides the DataAligner class for aligning data across
different timezones, frequencies, and business day calendars.
"""

from typing import Dict, Literal, Optional
import pandas as pd
import numpy as np
from datetime import time

from .base import ProcessingStep


# Business day calendars for different exchanges
# SSE: Shanghai Stock Exchange (China)
# NYSE: New York Stock Exchange (US)
EXCHANGE_CALENDARS = {
    'SSE': {
        'timezone': 'Asia/Shanghai',
        'open_time': time(9, 30),
        'close_time': time(15, 0),
        # Chinese holidays are approximated; for production use pandas_market_calendars
        'weekmask': 'Mon Tue Wed Thu Fri',
    },
    'NYSE': {
        'timezone': 'America/New_York',
        'open_time': time(9, 30),
        'close_time': time(16, 0),
        'weekmask': 'Mon Tue Wed Thu Fri',
    },
    'HKEX': {
        'timezone': 'Asia/Hong_Kong',
        'open_time': time(9, 30),
        'close_time': time(16, 0),
        'weekmask': 'Mon Tue Wed Thu Fri',
    },
    'LSE': {
        'timezone': 'Europe/London',
        'open_time': time(8, 0),
        'close_time': time(16, 30),
        'weekmask': 'Mon Tue Wed Thu Fri',
    },
}


class DataAligner(ProcessingStep):
    """
    Data aligner for OHLCV data.
    
    Handles alignment operations:
    - Timezone conversion
    - Frequency resampling
    - Business day alignment
    - Multiple DataFrame alignment
    
    Example:
        >>> aligner = DataAligner()
        >>> aligned_df = aligner.process(raw_df)
        >>> # Or use individual methods
        >>> df = aligner.align_timezone(df, target_tz='Asia/Shanghai')
        >>> df = aligner.align_business_days(df, calendar='SSE')
    """
    
    def __init__(
        self,
        target_tz: str = 'UTC',
        target_freq: str = 'D',
        calendar: str = 'NYSE'
    ):
        """
        Initialize the DataAligner.
        
        Args:
            target_tz: Target timezone for alignment.
            target_freq: Target frequency for resampling.
            calendar: Default calendar for business day alignment.
        """
        self.target_tz = target_tz
        self.target_freq = target_freq
        self.calendar = calendar
    
    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply default alignment operations.
        
        This method applies:
        1. Timezone alignment to target timezone
        2. Frequency alignment to target frequency
        3. Business day alignment using default calendar
        
        Args:
            df: Input DataFrame with OHLCV data.
        
        Returns:
            Aligned DataFrame.
        """
        result = df.copy()
        
        result = self.align_timezone(result, target_tz=self.target_tz)
        result = self.align_frequency(result, freq=self.target_freq)
        result = self.align_business_days(result, calendar=self.calendar)
        
        return result
    
    def align_timezone(
        self,
        df: pd.DataFrame,
        target_tz: str = 'Asia/Shanghai'
    ) -> pd.DataFrame:
        """
        Convert timezone of the DataFrame index.
        
        Handles both timezone-aware and timezone-naive DataFrames.
        If the index is timezone-naive, it is assumed to be in UTC.
        
        Args:
            df: Input DataFrame with DatetimeIndex.
            target_tz: Target timezone (e.g., 'Asia/Shanghai', 'America/New_York').
        
        Returns:
            DataFrame with index converted to target timezone.
        """
        result = df.copy()
        
        if not isinstance(result.index, pd.DatetimeIndex):
            return result
        
        # If index is timezone-naive, localize to UTC first
        if result.index.tz is None:
            result.index = result.index.tz_localize('UTC')
        
        # Convert to target timezone
        result.index = result.index.tz_convert(target_tz)
        
        return result
    
    def align_frequency(
        self,
        df: pd.DataFrame,
        freq: str = 'D'
    ) -> pd.DataFrame:
        """
        Resample DataFrame to target frequency.
        
        Supported frequencies:
        - 'D': Daily
        - 'W': Weekly
        - 'M': Monthly
        - 'H': Hourly
        - 'T' or 'min': Minute
        
        For OHLCV data:
        - Open: First value in the period
        - High: Maximum value in the period
        - Low: Minimum value in the period
        - Close: Last value in the period
        - Volume: Sum of volumes in the period
        
        Args:
            df: Input DataFrame with OHLCV data.
            freq: Target frequency for resampling.
        
        Returns:
            Resampled DataFrame.
        """
        result = df.copy()
        
        if not isinstance(result.index, pd.DatetimeIndex):
            return result
        
        # Get column names (case-insensitive)
        col_map = {col.lower(): col for col in result.columns}
        
        # Define aggregation rules for OHLCV
        agg_rules = {}
        
        if 'open' in col_map:
            agg_rules[col_map['open']] = 'first'
        if 'high' in col_map:
            agg_rules[col_map['high']] = 'max'
        if 'low' in col_map:
            agg_rules[col_map['low']] = 'min'
        if 'close' in col_map:
            agg_rules[col_map['close']] = 'last'
        if 'volume' in col_map:
            agg_rules[col_map['volume']] = 'sum'
        
        # Add any additional columns with 'last' aggregation
        for col in result.columns:
            if col not in agg_rules:
                agg_rules[col] = 'last'
        
        # Resample and aggregate
        resampled = result.resample(freq).agg(agg_rules)
        
        # Drop rows where all OHLCV values are NaN
        ohlcv_cols = [col_map.get(c) for c in ['open', 'high', 'low', 'close'] if c in col_map]
        if ohlcv_cols:
            resampled = resampled.dropna(subset=ohlcv_cols, how='all')
        
        return resampled
    
    def align_business_days(
        self,
        df: pd.DataFrame,
        calendar: Literal['SSE', 'NYSE', 'HKEX', 'LSE'] = 'SSE'
    ) -> pd.DataFrame:
        """
        Align DataFrame to business days of a specific exchange.
        
        This method:
        1. Removes weekends
        2. Filters to valid trading days based on the exchange calendar
        
        Note: This is a simplified implementation that removes weekends.
        For production use with holiday handling, consider using
        pandas_market_calendars library.
        
        Args:
            df: Input DataFrame with OHLCV data.
            calendar: Exchange calendar to use ('SSE', 'NYSE', 'HKEX', 'LSE').
        
        Returns:
            DataFrame with only business days.
        """
        result = df.copy()
        
        if not isinstance(result.index, pd.DatetimeIndex):
            return result
        
        if calendar not in EXCHANGE_CALENDARS:
            calendar = 'NYSE'  # Default to NYSE
        
        cal_info = EXCHANGE_CALENDARS[calendar]
        
        # Get the target timezone for this calendar
        target_tz = cal_info['timezone']
        
        # Convert to calendar's timezone for proper day-of-week filtering
        original_tz = result.index.tz
        if result.index.tz is not None:
            temp_index = result.index.tz_convert(target_tz)
        else:
            temp_index = result.index.tz_localize('UTC').tz_convert(target_tz)
        
        # Filter to weekdays (Monday=0 to Friday=4)
        weekday_mask = temp_index.weekday < 5
        
        result = result[weekday_mask]
        
        # Restore original timezone if needed
        if original_tz is not None:
            result.index = result.index.tz_convert(original_tz)
        
        return result
    
    def align_multiple(
        self,
        dataframes: Dict[str, pd.DataFrame]
    ) -> Dict[str, pd.DataFrame]:
        """
        Align multiple DataFrames to common dates.
        
        This method finds the intersection of dates across all DataFrames
        and filters each DataFrame to only include those common dates.
        
        Args:
            dataframes: Dictionary mapping symbol names to DataFrames.
        
        Returns:
            Dictionary of aligned DataFrames with common dates.
        """
        if not dataframes:
            return {}
        
        # Make copies
        result = {symbol: df.copy() for symbol, df in dataframes.items()}
        
        # Find common dates (date-only, ignoring time)
        common_dates = None
        
        for symbol, df in result.items():
            if not isinstance(df.index, pd.DatetimeIndex):
                continue
            
            # Get unique dates (without time component)
            dates = set(df.index.date)
            
            if common_dates is None:
                common_dates = dates
            else:
                common_dates = common_dates.intersection(dates)
        
        if common_dates is None or len(common_dates) == 0:
            return result
        
        # Filter each DataFrame to common dates
        for symbol, df in result.items():
            if isinstance(df.index, pd.DatetimeIndex):
                date_mask = [d.date() in common_dates for d in df.index]
                result[symbol] = df[date_mask]
        
        return result
    
    def get_trading_hours(
        self,
        df: pd.DataFrame,
        calendar: str = 'NYSE'
    ) -> pd.DataFrame:
        """
        Filter DataFrame to only include trading hours.
        
        This is useful for intraday data where you want to exclude
        pre-market and after-hours trading.
        
        Args:
            df: Input DataFrame with intraday OHLCV data.
            calendar: Exchange calendar to use.
        
        Returns:
            DataFrame filtered to trading hours.
        """
        result = df.copy()
        
        if not isinstance(result.index, pd.DatetimeIndex):
            return result
        
        if calendar not in EXCHANGE_CALENDARS:
            calendar = 'NYSE'
        
        cal_info = EXCHANGE_CALENDARS[calendar]
        open_time = cal_info['open_time']
        close_time = cal_info['close_time']
        target_tz = cal_info['timezone']
        
        # Convert to calendar's timezone
        if result.index.tz is not None:
            temp_index = result.index.tz_convert(target_tz)
        else:
            temp_index = result.index.tz_localize('UTC').tz_convert(target_tz)
        
        # Filter to trading hours
        trading_mask = (temp_index.time >= open_time) & (temp_index.time <= close_time)
        
        return result[trading_mask]
