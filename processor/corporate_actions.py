"""
Corporate actions handling module for OHLCV data.

This module provides the CorpActionHandler class for adjusting prices
for stock splits and dividends.
"""

from typing import Optional
from dataclasses import dataclass
from datetime import datetime
import pandas as pd
import numpy as np

from .base import ProcessingStep


@dataclass
class CorpAction:
    """
    Represents a corporate action.
    
    Attributes:
        symbol: Stock symbol.
        action_type: Type of action ('split' or 'dividend').
        date: Ex-date of the corporate action.
        ratio: Split ratio (e.g., 2.0 for 2:1 split) or dividend amount per share.
        currency: Currency of the dividend (default 'USD').
    """
    symbol: str
    action_type: str  # 'split' or 'dividend'
    date: datetime
    ratio: float
    currency: str = "USD"


class CorpActionHandler(ProcessingStep):
    """
    Handler for corporate actions on OHLCV data.
    
    Handles:
    - Stock splits adjustments
    - Dividend adjustments
    - Full adjusted price calculations
    
    Note: Yahoo Finance already provides adjusted close prices. This module
    provides the logic for manual adjustments when needed.
    
    Example:
        >>> handler = CorpActionHandler()
        >>> adjusted_df = handler.adjust_for_splits(df, split_ratio=2.0)
        >>> adjusted_df = handler.adjust_for_dividends(df, dividend_per_share=0.50)
    """
    
    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Process DataFrame - returns unchanged as corporate actions require
        specific action data.
        
        Use specific methods like adjust_for_splits() or calculate_adjusted_prices()
        for actual adjustments.
        
        Args:
            df: Input DataFrame with OHLCV data.
        
        Returns:
            Unchanged DataFrame.
        """
        return df.copy()
    
    def adjust_for_splits(
        self,
        df: pd.DataFrame,
        split_ratio: float,
        split_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Adjust historical prices for stock splits.
        
        When a stock splits, historical prices need to be adjusted to maintain
        price continuity. For a 2:1 split, all prices before the split date
        are divided by 2.
        
        Args:
            df: Input DataFrame with OHLCV data.
            split_ratio: Split ratio (e.g., 2.0 for 2:1 split, 0.5 for 1:2 reverse split).
            split_date: Ex-date of the split. If None, adjusts all data.
        
        Returns:
            DataFrame with adjusted prices.
        
        Example:
            For a 2:1 split on 2024-01-15:
            >>> df = handler.adjust_for_splits(df, split_ratio=2.0, split_date=pd.Timestamp('2024-01-15'))
        """
        result = df.copy()
        
        # Get column names (case-insensitive)
        col_map = {col.lower(): col for col in result.columns}
        
        price_cols = ['open', 'high', 'low', 'close']
        volume_col = col_map.get('volume')
        
        # Determine which rows to adjust
        if split_date is not None and isinstance(result.index, pd.DatetimeIndex):
            # Adjust only prices before the split date
            mask = result.index < split_date
        else:
            # Adjust all rows
            mask = pd.Series(True, index=result.index)
        
        # Adjust prices (divide by split ratio)
        for col in price_cols:
            if col in col_map:
                actual_col = col_map[col]
                result.loc[mask, actual_col] = result.loc[mask, actual_col] / split_ratio
        
        # Adjust volume (multiply by split ratio)
        if volume_col and mask.any():
            result.loc[mask, volume_col] = result.loc[mask, volume_col] * split_ratio
        
        return result
    
    def adjust_for_dividends(
        self,
        df: pd.DataFrame,
        dividend_per_share: float,
        ex_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Adjust prices for dividends.
        
        On the ex-dividend date, the stock price typically drops by approximately
        the dividend amount. This method adjusts historical prices to account
        for this effect.
        
        The adjustment factor is calculated as:
        factor = (close - dividend) / close
        
        All prices before the ex-date are multiplied by this factor.
        
        Args:
            df: Input DataFrame with OHLCV data.
            dividend_per_share: Dividend amount per share.
            ex_date: Ex-dividend date. If None, uses the first date in the DataFrame.
        
        Returns:
            DataFrame with adjusted prices.
        """
        result = df.copy()
        
        # Get column names (case-insensitive)
        col_map = {col.lower(): col for col in result.columns}
        close_col = col_map.get('close')
        
        if close_col is None:
            return result
        
        # Determine ex-date
        if ex_date is None:
            ex_date = result.index[0] if len(result.index) > 0 else None
        
        if ex_date is None:
            return result
        
        # Get the close price on ex-date (or the closest date after)
        if isinstance(result.index, pd.DatetimeIndex):
            # Find the close price on or after ex-date
            ex_date_prices = result.loc[result.index >= ex_date, close_col]
            if len(ex_date_prices) > 0:
                close_on_ex_date = ex_date_prices.iloc[0]
            else:
                close_on_ex_date = result[close_col].iloc[-1]
        else:
            close_on_ex_date = result[close_col].iloc[0]
        
        # Calculate adjustment factor
        # factor = (close - dividend) / close
        adjustment_factor = (close_on_ex_date - dividend_per_share) / close_on_ex_date
        
        # Adjust prices before ex-date
        price_cols = ['open', 'high', 'low', 'close']
        
        if isinstance(result.index, pd.DatetimeIndex):
            mask = result.index < ex_date
        else:
            mask = pd.Series(True, index=result.index)
        
        for col in price_cols:
            if col in col_map:
                actual_col = col_map[col]
                result.loc[mask, actual_col] = result.loc[mask, actual_col] * adjustment_factor
        
        return result
    
    def calculate_adjusted_prices(
        self,
        df: pd.DataFrame,
        splits: Optional[pd.DataFrame] = None,
        dividends: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Calculate fully adjusted prices for all corporate actions.
        
        This method applies both split and dividend adjustments to calculate
        adjusted prices. The result includes an 'adj_close' column.
        
        Expected format for splits DataFrame:
            - Index: DatetimeIndex (ex-dates)
            - Column 'ratio': Split ratio (e.g., 2.0 for 2:1 split)
        
        Expected format for dividends DataFrame:
            - Index: DatetimeIndex (ex-dates)
            - Column 'amount': Dividend amount per share
        
        Args:
            df: Input DataFrame with OHLCV data.
            splits: DataFrame with split information.
            dividends: DataFrame with dividend information.
        
        Returns:
            DataFrame with adjusted prices and 'adj_close' column.
        """
        result = df.copy()
        
        # Get column names (case-insensitive)
        col_map = {col.lower(): col for col in result.columns}
        close_col = col_map.get('close')
        
        if close_col is None:
            return result
        
        # Start with close price as adjusted close
        result['adj_close'] = result[close_col].copy()
        
        # Apply split adjustments (from most recent to oldest)
        if splits is not None and not splits.empty:
            if isinstance(splits.index, pd.DatetimeIndex):
                # Sort by date descending (most recent first)
                sorted_splits = splits.sort_index(ascending=False)
                
                for split_date, split_row in sorted_splits.iterrows():
                    ratio = split_row.get('ratio', split_row.get('split_ratio', 1.0))
                    
                    # Adjust prices before split date
                    mask = result.index < split_date
                    
                    # Adjust all price columns
                    for col in ['open', 'high', 'low', 'close', 'adj_close']:
                        if col in col_map or col == 'adj_close':
                            actual_col = col_map.get(col, col)
                            result.loc[mask, actual_col] = result.loc[mask, actual_col] / ratio
                    
                    # Adjust volume
                    if 'volume' in col_map:
                        result.loc[mask, col_map['volume']] = result.loc[mask, col_map['volume']] * ratio
        
        # Apply dividend adjustments (from most recent to oldest)
        if dividends is not None and not dividends.empty:
            if isinstance(dividends.index, pd.DatetimeIndex):
                # Sort by date descending (most recent first)
                sorted_dividends = dividends.sort_index(ascending=False)
                
                for ex_date, div_row in sorted_dividends.iterrows():
                    dividend_amount = div_row.get('amount', div_row.get('dividend', 0))
                    
                    if dividend_amount <= 0:
                        continue
                    
                    # Get close price on ex-date
                    ex_date_prices = result.loc[result.index >= ex_date, 'adj_close']
                    if len(ex_date_prices) > 0:
                        close_on_ex_date = ex_date_prices.iloc[0]
                    else:
                        continue
                    
                    # Calculate adjustment factor
                    factor = (close_on_ex_date - dividend_amount) / close_on_ex_date
                    
                    # Adjust prices before ex-date
                    mask = result.index < ex_date
                    
                    for col in ['open', 'high', 'low', 'adj_close']:
                        if col in col_map or col == 'adj_close':
                            actual_col = col_map.get(col, col)
                            result.loc[mask, actual_col] = result.loc[mask, actual_col] * factor
        
        return result
    
    def calculate_adjustment_factor(
        self,
        df: pd.DataFrame,
        splits: Optional[pd.DataFrame] = None,
        dividends: Optional[pd.DataFrame] = None
    ) -> pd.Series:
        """
        Calculate the cumulative adjustment factor for each date.
        
        The adjustment factor can be used to convert between adjusted and
        unadjusted prices:
        - adjusted_price = unadjusted_price * adjustment_factor
        - unadjusted_price = adjusted_price / adjustment_factor
        
        Args:
            df: Input DataFrame with OHLCV data.
            splits: DataFrame with split information.
            dividends: DataFrame with dividend information.
        
        Returns:
            Series with adjustment factor for each date.
        """
        result = df.copy()
        
        # Start with factor of 1.0
        adjustment_factor = pd.Series(1.0, index=result.index)
        
        # Apply split adjustments
        if splits is not None and not splits.empty:
            if isinstance(splits.index, pd.DatetimeIndex):
                for split_date, split_row in splits.iterrows():
                    ratio = split_row.get('ratio', split_row.get('split_ratio', 1.0))
                    mask = result.index < split_date
                    adjustment_factor[mask] = adjustment_factor[mask] / ratio
        
        # Apply dividend adjustments
        if dividends is not None and not dividends.empty:
            if isinstance(dividends.index, pd.DatetimeIndex):
                # Get close prices
                col_map = {col.lower(): col for col in result.columns}
                close_col = col_map.get('close')
                
                if close_col:
                    for ex_date, div_row in dividends.iterrows():
                        dividend_amount = div_row.get('amount', div_row.get('dividend', 0))
                        
                        if dividend_amount <= 0:
                            continue
                        
                        # Get close price on ex-date
                        ex_date_prices = result.loc[result.index >= ex_date, close_col]
                        if len(ex_date_prices) > 0:
                            close_on_ex_date = ex_date_prices.iloc[0]
                            factor = (close_on_ex_date - dividend_amount) / close_on_ex_date
                            
                            mask = result.index < ex_date
                            adjustment_factor[mask] = adjustment_factor[mask] * factor
        
        return adjustment_factor
