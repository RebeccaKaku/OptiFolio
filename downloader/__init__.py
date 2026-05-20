# downloader/__init__.py
"""
OptiFolio Downloader Module

Provides raw data download with batch processing and caching capabilities.

Main Components:
- DownloadManager: Main orchestrator for data downloads
- DataCache: File-based caching system
- DownloadTask: Dataclass for download requests
- DownloadResult: Dataclass for download responses
- BatchDownloader: Utilities for batch download operations

Usage:
    from downloader import DownloadManager, DownloadTask
    from fetchers import YahooFinanceFetcher
    
    # Create manager and register fetcher
    manager = DownloadManager()
    manager.register_fetcher('yahoo', YahooFinanceFetcher())
    
    # Create a download task
    task = DownloadTask(
        symbol='AAPL',
        source='yahoo',
        start_date='2024-01-01',
        end_date='2024-12-31',
        timeframe='1d',
    )
    
    # Download data
    result = await manager.download(task)
    if result.success:
        print(result.data)
"""

from .models import DownloadTask, DownloadResult
from .cache import DataCache
from .manager import DownloadManager
from .batch import BatchDownloader, create_progress_printer

__all__ = [
    # Core classes
    'DownloadManager',
    'DataCache',
    'BatchDownloader',
    # Data models
    'DownloadTask',
    'DownloadResult',
    # Utilities
    'create_progress_printer',
]
