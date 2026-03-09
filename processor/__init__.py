"""
Processor module for data cleaning, alignment, and standardization.

This module provides tools for processing OHLCV financial data:
- ProcessingStep: Abstract base class for processing steps
- ProcessingPipeline: Chain multiple processing steps together
- DataCleaner: Handle missing values, outliers, and gaps
- DataAligner: Align timezone, frequency, and business days
- CorpActionHandler: Adjust for stock splits and dividends
- DataStandardizer: Ensure consistent data format

Example:
    >>> from processor import ProcessingPipeline, DataCleaner, DataAligner, DataStandardizer
    >>> 
    >>> # Create a processing pipeline
    >>> pipeline = ProcessingPipeline()
    >>> pipeline.add_step(DataCleaner())
    >>> pipeline.add_step(DataAligner())
    >>> pipeline.add_step(DataStandardizer())
    >>> 
    >>> # Process data
    >>> clean_df = pipeline.run(raw_df)
    >>> 
    >>> # Or use individual processors
    >>> cleaner = DataCleaner()
    >>> df = cleaner.handle_missing_values(df, method='ffill')
    >>> df = cleaner.remove_outliers(df, method='iqr', threshold=1.5)
"""

from .base import ProcessingStep, ProcessingPipeline
from .cleaner import DataCleaner
from .aligner import DataAligner, EXCHANGE_CALENDARS
from .corporate_actions import CorpActionHandler, CorpAction
from .standardizer import DataStandardizer, STANDARD_COLUMNS, COLUMN_MAPPINGS

__all__ = [
    # Base classes
    'ProcessingStep',
    'ProcessingPipeline',
    
    # Data cleaning
    'DataCleaner',
    
    # Data alignment
    'DataAligner',
    'EXCHANGE_CALENDARS',
    
    # Corporate actions
    'CorpActionHandler',
    'CorpAction',
    
    # Data standardization
    'DataStandardizer',
    'STANDARD_COLUMNS',
    'COLUMN_MAPPINGS',
]

__version__ = '0.1.0'
