# downloader/models.py
"""
Data models for the downloader module.

Contains DownloadTask for download requests and DownloadResult for download responses.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
import pandas as pd


@dataclass
class DownloadTask:
    """
    Dataclass for download request.
    
    Attributes:
        symbol: The symbol to download (e.g., 'BTC/USDT', 'AAPL')
        source: The data source name (e.g., 'crypto', 'yahoo', 'cn_fund')
        start_date: Start date in 'YYYY-MM-DD' format
        end_date: End date in 'YYYY-MM-DD' format
        timeframe: Time interval (e.g., '1d', '1h', '1m')
        exchange: Optional exchange name (mainly for crypto)
    """
    symbol: str
    source: str
    start_date: str
    end_date: str
    timeframe: str = '1d'
    exchange: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary representation."""
        return {
            'symbol': self.symbol,
            'source': self.source,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'timeframe': self.timeframe,
            'exchange': self.exchange,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DownloadTask':
        """Create DownloadTask from dictionary."""
        return cls(
            symbol=data['symbol'],
            source=data['source'],
            start_date=data['start_date'],
            end_date=data['end_date'],
            timeframe=data.get('timeframe', '1d'),
            exchange=data.get('exchange'),
        )
    
    def get_cache_key(self) -> str:
        """
        Generate a cache key for this task.
        
        Format: {source}_{symbol}_{start}_{end}_{timeframe}.parquet
        """
        # Sanitize symbol for filesystem (replace / with _)
        safe_symbol = self.symbol.replace('/', '_')
        return f"{self.source}_{safe_symbol}_{self.start_date}_{self.end_date}_{self.timeframe}.parquet"


@dataclass
class DownloadResult:
    """
    Dataclass for download response.
    
    Attributes:
        task: The original DownloadTask
        data: The downloaded DataFrame (or None if failed)
        success: Whether the download was successful
        error_message: Error message if download failed
        latency_ms: Time taken for download in milliseconds
        is_cached: Whether the data was retrieved from cache
        timestamp: When the result was created
    """
    task: DownloadTask
    data: Optional[pd.DataFrame]
    success: bool
    error_message: Optional[str] = None
    latency_ms: float = 0.0
    is_cached: bool = False
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary representation (without DataFrame)."""
        return {
            'task': self.task.to_dict(),
            'success': self.success,
            'error_message': self.error_message,
            'latency_ms': self.latency_ms,
            'is_cached': self.is_cached,
            'timestamp': self.timestamp.isoformat(),
            'rows': len(self.data) if self.data is not None else 0,
        }
