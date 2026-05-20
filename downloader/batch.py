# downloader/batch.py
"""
Batch download utilities for convenient batch operations.

Provides a BatchDownloader class for creating and executing batch download tasks
with progress reporting support.
"""

import asyncio
from typing import List, Optional, Callable, Dict, Any
from datetime import datetime, timedelta

from .models import DownloadTask, DownloadResult
from .manager import DownloadManager


class BatchDownloader:
    """
    Convenient batch download operations.
    
    Provides factory methods for creating batch tasks and utilities
    for executing downloads with progress reporting.
    
    Attributes:
        manager: DownloadManager instance
        max_concurrent: Maximum concurrent downloads
        retry_count: Number of retries for failed downloads
        retry_delay: Delay between retries in seconds
    """
    
    def __init__(
        self,
        manager: DownloadManager,
        max_concurrent: int = 5,
        retry_count: int = 0,
        retry_delay: float = 1.0,
    ):
        """
        Initialize the batch downloader.
        
        Args:
            manager: DownloadManager instance
            max_concurrent: Maximum concurrent downloads
            retry_count: Number of retries for failed downloads
            retry_delay: Delay between retries in seconds
        """
        self.manager = manager
        self.max_concurrent = max_concurrent
        self.retry_count = retry_count
        self.retry_delay = retry_delay
    
    @staticmethod
    def from_symbols(
        symbols: List[str],
        source: str,
        start_date: str,
        end_date: str,
        timeframe: str = '1d',
        exchange: Optional[str] = None,
    ) -> List[DownloadTask]:
        """
        Create download tasks from a list of symbols.
        
        Args:
            symbols: List of symbol strings
            source: Data source name
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            timeframe: Time interval (default: '1d')
            exchange: Optional exchange name
            
        Returns:
            List of DownloadTask objects
        """
        return [
            DownloadTask(
                symbol=symbol,
                source=source,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe,
                exchange=exchange,
            )
            for symbol in symbols
        ]
    
    @staticmethod
    def from_date_range(
        symbol: str,
        source: str,
        start_date: str,
        end_date: str,
        timeframe: str = '1d',
        exchange: Optional[str] = None,
        chunk_days: int = 30,
    ) -> List[DownloadTask]:
        """
        Create download tasks by splitting a date range into chunks.
        
        Useful for downloading large date ranges that might timeout
        or need to be split for reliability.
        
        Args:
            symbol: Symbol string
            source: Data source name
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            timeframe: Time interval (default: '1d')
            exchange: Optional exchange name
            chunk_days: Number of days per chunk
            
        Returns:
            List of DownloadTask objects
        """
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        tasks = []
        current_start = start
        
        while current_start < end:
            current_end = min(current_start + timedelta(days=chunk_days), end)
            
            tasks.append(DownloadTask(
                symbol=symbol,
                source=source,
                start_date=current_start.strftime('%Y-%m-%d'),
                end_date=current_end.strftime('%Y-%m-%d'),
                timeframe=timeframe,
                exchange=exchange,
            ))
            
            current_start = current_end + timedelta(days=1)
        
        return tasks
    
    async def download_parallel(
        self,
        tasks: List[DownloadTask],
        progress_callback: Optional[Callable[[int, int, DownloadResult], None]] = None,
    ) -> List[DownloadResult]:
        """
        Download tasks in parallel with optional retries.
        
        Args:
            tasks: List of DownloadTask objects
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of DownloadResult objects
        """
        results = await self.manager.download_batch(
            tasks=tasks,
            max_concurrent=self.max_concurrent,
            progress_callback=progress_callback,
        )
        
        # Handle retries for failed downloads
        if self.retry_count > 0:
            results = await self._retry_failed(tasks, results, progress_callback)
        
        return results
    
    async def _retry_failed(
        self,
        tasks: List[DownloadTask],
        results: List[DownloadResult],
        progress_callback: Optional[Callable[[int, int, DownloadResult], None]] = None,
    ) -> List[DownloadResult]:
        """
        Retry failed downloads.
        
        Args:
            tasks: Original list of tasks
            results: Results from initial download
            progress_callback: Optional progress callback
            
        Returns:
            Updated list of DownloadResult objects
        """
        results = list(results)  # Make a copy
        
        for retry in range(self.retry_count):
            # Find failed tasks
            failed_indices = [
                i for i, r in enumerate(results)
                if r is None or not r.success
            ]
            
            if not failed_indices:
                break
            
            # Wait before retry
            await asyncio.sleep(self.retry_delay)
            
            # Retry failed tasks
            for idx in failed_indices:
                result = await self.manager.download(tasks[idx])
                results[idx] = result
                
                if progress_callback:
                    progress_callback(idx + 1, len(tasks), result)
        
        return results
    
    async def download_sequential(
        self,
        tasks: List[DownloadTask],
        progress_callback: Optional[Callable[[int, int, DownloadResult], None]] = None,
    ) -> List[DownloadResult]:
        """
        Download tasks sequentially (one at a time).
        
        Args:
            tasks: List of DownloadTask objects
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of DownloadResult objects
        """
        results = []
        total = len(tasks)
        
        for i, task in enumerate(tasks):
            result = await self.manager.download(task)
            results.append(result)
            
            if progress_callback:
                progress_callback(i + 1, total, result)
        
        return results
    
    def get_summary(self, results: List[DownloadResult]) -> Dict[str, Any]:
        """
        Get a summary of batch download results.
        
        Args:
            results: List of DownloadResult objects
            
        Returns:
            Dictionary with summary statistics
        """
        total = len(results)
        successful = sum(1 for r in results if r and r.success)
        failed = total - successful
        cached = sum(1 for r in results if r and r.is_cached)
        total_rows = sum(len(r.data) if r and r.data is not None else 0 for r in results)
        total_latency = sum(r.latency_ms if r else 0 for r in results)
        
        return {
            'total_tasks': total,
            'successful': successful,
            'failed': failed,
            'cached': cached,
            'total_rows': total_rows,
            'total_latency_ms': total_latency,
            'success_rate': successful / total if total > 0 else 0,
        }


def create_progress_printer(
    prefix: str = "Downloading",
    show_latency: bool = True,
) -> Callable[[int, int, DownloadResult], None]:
    """
    Create a simple progress printer callback.
    
    Args:
        prefix: Prefix string for progress messages
        show_latency: Whether to show latency in output
        
    Returns:
        Callback function for use with download methods
    """
    def callback(completed: int, total: int, result: DownloadResult) -> None:
        status = "✓" if result.success else "✗"
        cached = "(cached)" if result.is_cached else ""
        latency = f"[{result.latency_ms:.0f}ms]" if show_latency else ""
        
        print(f"{prefix}: [{completed}/{total}] {status} {result.task.symbol} {cached} {latency}")
        
        if not result.success and result.error_message:
            print(f"  Error: {result.error_message}")
    
    return callback
