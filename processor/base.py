"""
Base classes for data processing pipeline.

This module provides the abstract base class for processing steps
and a pipeline to chain multiple steps together.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import pandas as pd


class ProcessingStep(ABC):
    """
    Abstract base class for all processing steps.
    
    Each processing step takes a DataFrame and returns a processed DataFrame.
    Steps can be chained together in a ProcessingPipeline.
    """
    
    @abstractmethod
    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Process the input DataFrame.
        
        Args:
            df: Input DataFrame with OHLCV data.
                Expected format:
                - Index: DatetimeIndex named 'timestamp'
                - Columns: open, high, low, close, volume (lowercase)
        
        Returns:
            Processed DataFrame with the same structure.
        """
        pass
    
    def validate_input(self, df: pd.DataFrame) -> bool:
        """
        Validate that the input DataFrame has the expected format.
        
        Args:
            df: Input DataFrame to validate.
        
        Returns:
            True if valid, False otherwise.
        """
        if not isinstance(df, pd.DataFrame):
            return False
        
        if not isinstance(df.index, pd.DatetimeIndex):
            return False
        
        required_columns = {'open', 'high', 'low', 'close', 'volume'}
        if not required_columns.issubset(set(df.columns.str.lower())):
            return False
        
        return True
    
    def get_name(self) -> str:
        """
        Get the name of this processing step.
        
        Returns:
            Name of the processing step.
        """
        return self.__class__.__name__


class ProcessingPipeline:
    """
    Chain multiple processing steps together.
    
    The pipeline executes steps in sequence, passing the output of each
    step as input to the next step.
    
    Example:
        >>> pipeline = ProcessingPipeline()
        >>> pipeline.add_step(DataCleaner())
        >>> pipeline.add_step(DataAligner())
        >>> pipeline.add_step(DataStandardizer())
        >>> processed_df = pipeline.run(raw_df)
    """
    
    def __init__(self, steps: Optional[List[ProcessingStep]] = None):
        """
        Initialize the processing pipeline.
        
        Args:
            steps: Optional list of processing steps to initialize with.
        """
        self._steps: List[ProcessingStep] = steps if steps else []
    
    def add_step(self, step: ProcessingStep) -> 'ProcessingPipeline':
        """
        Add a processing step to the pipeline.
        
        Args:
            step: Processing step to add.
        
        Returns:
            Self for method chaining.
        """
        self._steps.append(step)
        return self
    
    def remove_step(self, step_name: str) -> 'ProcessingPipeline':
        """
        Remove a processing step by name.
        
        Args:
            step_name: Name of the step to remove.
        
        Returns:
            Self for method chaining.
        """
        self._steps = [s for s in self._steps if s.get_name() != step_name]
        return self
    
    def run(self, df: pd.DataFrame, verbose: bool = False) -> pd.DataFrame:
        """
        Run all processing steps in sequence.
        
        Args:
            df: Input DataFrame to process.
            verbose: If True, print step names during processing.
        
        Returns:
            Processed DataFrame after all steps have been applied.
        
        Raises:
            ValueError: If input DataFrame is invalid.
        """
        result = df.copy()
        
        for step in self._steps:
            if verbose:
                print(f"Running step: {step.get_name()}")
            
            if not step.validate_input(result):
                raise ValueError(
                    f"Invalid input for step {step.get_name()}. "
                    f"Expected DataFrame with DatetimeIndex and OHLCV columns."
                )
            
            result = step.process(result)
        
        return result
    
    def get_steps(self) -> List[str]:
        """
        Get the names of all steps in the pipeline.
        
        Returns:
            List of step names in order.
        """
        return [step.get_name() for step in self._steps]
    
    def clear(self) -> 'ProcessingPipeline':
        """
        Remove all steps from the pipeline.
        
        Returns:
            Self for method chaining.
        """
        self._steps.clear()
        return self
    
    def __len__(self) -> int:
        """Return the number of steps in the pipeline."""
        return len(self._steps)
    
    def __repr__(self) -> str:
        """Return string representation of the pipeline."""
        steps_str = " -> ".join(self.get_steps())
        return f"ProcessingPipeline({steps_str})"
