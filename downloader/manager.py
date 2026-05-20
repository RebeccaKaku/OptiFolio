# downloader/manager.py
"""
Download manager for orchestrating data downloads.

Provides a DownloadManager class that coordinates fetchers, caching,
and batch downloads with concurrency control.
"""

import asyncio
import time
from typing import Dict, List, Optional, Callable, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor

if TYPE_CHECKING:
    from fetchers.interfaces import AsyncBaseFetcher
from .models import DownloadTask, DownloadResult
from .cache import DataCache


class DownloadManager:
    """
    Main orchestrator for data downloads.
    
    Manages fetchers, caching, and coordinates batch downloads with
    concurrency control using asyncio.
    
    Attributes:
        cache: DataCache instance for caching downloaded data
        fetchers: Dictionary of registered fetchers
    """
    
    def __init__(self, cache_dir: str = ".cache"):
        """
        Initialize the download manager.
        
        Args:
            cache_dir: Directory path for cache storage
        """
        self.cache = DataCache(cache_dir)
        self._fetchers: Dict[str, 'AsyncBaseFetcher'] = {}
        self._executor = ThreadPoolExecutor(max_workers=1)
    
    def register_fetcher(self, name: str, fetcher: 'AsyncBaseFetcher') -> None:
        """
        Register a fetcher with the manager.
        
        Args:
            name: Name to identify the fetcher (e.g., 'crypto', 'yahoo')
            fetcher: AsyncBaseFetcher instance
        """
        self._fetchers[name] = fetcher
    
    def get_fetcher(self, name: str) -> Optional[AsyncBaseFetcher]:
        """
        Get a registered fetcher by name.
        
        Args:
            name: Name of the fetcher
            
        Returns:
            AsyncBaseFetcher instance or None if not found
        """
        return self._fetchers.get(name)
    
    def list_fetchers(self) -> List[str]:
        """
        List all registered fetcher names.
        
        Returns:
            List of fetcher names
        """
        return list(self._fetchers.keys())
    
    async def download(self, task: DownloadTask) -> DownloadResult:
        """
        Download data for a single task with caching.
        
        Checks cache first, and only fetches if not cached.
        Saves successful fetches to cache.
        
        Args:
            task: DownloadTask specifying what to download
            
        Returns:
            DownloadResult with data and status
        """
        start_time = time.time()
        
        # Check cache first
        cache_key = task.get_cache_key()
        cached_data = self.cache.get(cache_key)
        
        if cached_data is not None:
            latency_ms = (time.time() - start_time) * 1000
            return DownloadResult(
                task=task,
                data=cached_data,
                success=True,
                latency_ms=latency_ms,
                is_cached=True,
            )
        
        # Get the appropriate fetcher
        fetcher = self._fetchers.get(task.source)
        if fetcher is None:
            latency_ms = (time.time() - start_time) * 1000
            return DownloadResult(
                task=task,
                data=None,
                success=False,
                error_message=f"No fetcher registered for source: {task.source}",
                latency_ms=latency_ms,
            )
        
        # Fetch data
        try:
            data = await fetcher.fetch(
                symbol=task.symbol,
                start_date=task.start_date,
                end_date=task.end_date,
                timeframe=task.timeframe,
                exchange=task.exchange,
            )
            
            # Save to cache
            if data is not None and not data.empty:
                self.cache.set(cache_key, data)
            
            latency_ms = (time.time() - start_time) * 1000
            return DownloadResult(
                task=task,
                data=data,
                success=True,
                latency_ms=latency_ms,
            )
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return DownloadResult(
                task=task,
                data=None,
                success=False,
                error_message=str(e),
                latency_ms=latency_ms,
            )
    
    async def download_batch(
        self,
        tasks: List[DownloadTask],
        max_concurrent: int = 5,
        progress_callback: Optional[Callable[[int, int, DownloadResult], None]] = None,
    ) -> List[DownloadResult]:
        """
        Download data for multiple tasks concurrently.
        
        Uses asyncio.Semaphore for concurrency control.
        
        Args:
            tasks: List of DownloadTask objects
            max_concurrent: Maximum number of concurrent downloads
            progress_callback: Optional callback for progress updates
                Called with (completed_count, total_count, latest_result)
            
        Returns:
            List of DownloadResult objects in the same order as tasks
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        completed_count = 0
        total_count = len(tasks)
        results: List[DownloadResult] = [None] * total_count  # type: ignore
        
        async def download_with_semaphore(index: int, task: DownloadTask) -> tuple:
            nonlocal completed_count
            async with semaphore:
                result = await self.download(task)
                
                if progress_callback:
                    completed_count += 1
                    progress_callback(completed_count, total_count, result)
                
                return index, result
        
        # Create all tasks
        coroutines = [
            download_with_semaphore(i, task)
            for i, task in enumerate(tasks)
        ]
        
        # Execute all tasks concurrently
        completed_results = await asyncio.gather(*coroutines, return_exceptions=True)
        
        # Collect results in order
        for item in completed_results:
            if isinstance(item, Exception):
                # This shouldn't happen as we handle exceptions in download()
                continue
            index, result = item
            results[index] = result
        
        return results
    
    def clear_cache(self) -> None:
        """Clear all cached data."""
        self.cache.clear()
    
    def get_cache_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        return self.cache.get_cache_stats()
