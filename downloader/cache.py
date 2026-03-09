# downloader/cache.py
"""
File-based caching system for downloaded data.

Provides a DataCache class for storing and retrieving DataFrame data
with TTL (time-to-live) support.
"""

import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd


class DataCache:
    """
    File-based cache for downloaded market data.
    
    Uses parquet format for efficient storage and retrieval of DataFrame data.
    Supports TTL-based cache expiration.
    
    Attributes:
        cache_dir: Directory path for cache storage
    """
    
    def __init__(self, cache_dir: str = ".cache"):
        """
        Initialize the cache.
        
        Args:
            cache_dir: Directory path for cache storage (default: '.cache')
        """
        self.cache_dir = Path(cache_dir)
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get(self, key: str) -> Optional[pd.DataFrame]:
        """
        Retrieve data from cache.
        
        Args:
            key: Cache key (filename)
            
        Returns:
            Cached DataFrame or None if not found/expired
        """
        cache_path = self.cache_dir / key
        
        if not cache_path.exists():
            return None
        
        try:
            # Check if file has metadata about TTL
            metadata = self._read_metadata(cache_path)
            if metadata:
                created_at = metadata.get('created_at')
                ttl_hours = metadata.get('ttl_hours', 24)
                if created_at:
                    created = datetime.fromisoformat(created_at)
                    if datetime.now() > created + timedelta(hours=ttl_hours):
                        # Cache expired, remove file
                        self._remove_cache_file(cache_path)
                        return None
            
            # Read parquet file
            df = pd.read_parquet(cache_path)
            return df
        except Exception:
            # If there's any error reading the cache, return None
            return None
    
    def set(self, key: str, data: pd.DataFrame, ttl_hours: int = 24) -> None:
        """
        Store data in cache.
        
        Args:
            key: Cache key (filename)
            data: DataFrame to cache
            ttl_hours: Time-to-live in hours (default: 24)
        """
        cache_path = self.cache_dir / key
        
        try:
            # Save DataFrame as parquet
            data.to_parquet(cache_path)
            
            # Save metadata
            metadata = {
                'created_at': datetime.now().isoformat(),
                'ttl_hours': ttl_hours,
            }
            self._write_metadata(cache_path, metadata)
        except Exception as e:
            # Log error but don't fail
            print(f"Warning: Failed to cache data: {e}")
    
    def clear(self) -> None:
        """Clear all cache files."""
        if not self.cache_dir.exists():
            return
        
        for file in self.cache_dir.iterdir():
            try:
                if file.is_file():
                    file.unlink()
            except Exception:
                pass
    
    def invalidate(self, key: str) -> bool:
        """
        Invalidate (remove) a specific cache entry.
        
        Args:
            key: Cache key to invalidate
            
        Returns:
            True if entry was removed, False if not found
        """
        cache_path = self.cache_dir / key
        
        if cache_path.exists():
            self._remove_cache_file(cache_path)
            return True
        return False
    
    def get_cache_path(self, key: str) -> Path:
        """
        Get the full path for a cache key.
        
        Args:
            key: Cache key
            
        Returns:
            Full Path object for the cache file
        """
        return self.cache_dir / key
    
    def _read_metadata(self, cache_path: Path) -> Optional[dict]:
        """
        Read metadata for a cache file.
        
        Metadata is stored in a companion .meta file.
        
        Args:
            cache_path: Path to the cache file
            
        Returns:
            Metadata dictionary or None if not found
        """
        meta_path = cache_path.with_suffix('.meta')
        
        if not meta_path.exists():
            return None
        
        try:
            import json
            with open(meta_path, 'r') as f:
                return json.load(f)
        except Exception:
            return None
    
    def _write_metadata(self, cache_path: Path, metadata: dict) -> None:
        """
        Write metadata for a cache file.
        
        Args:
            cache_path: Path to the cache file
            metadata: Metadata dictionary to write
        """
        meta_path = cache_path.with_suffix('.meta')
        
        try:
            import json
            with open(meta_path, 'w') as f:
                json.dump(metadata, f)
        except Exception:
            pass
    
    def _remove_cache_file(self, cache_path: Path) -> None:
        """
        Remove a cache file and its metadata.
        
        Args:
            cache_path: Path to the cache file
        """
        try:
            if cache_path.exists():
                cache_path.unlink()
            
            meta_path = cache_path.with_suffix('.meta')
            if meta_path.exists():
                meta_path.unlink()
        except Exception:
            pass
    
    def clear_expired(self) -> int:
        """
        Clear all expired cache entries.
        
        Returns:
            Number of entries cleared
        """
        if not self.cache_dir.exists():
            return 0
        
        cleared = 0
        for file in self.cache_dir.glob('*.parquet'):
            metadata = self._read_metadata(file)
            if metadata:
                created_at = metadata.get('created_at')
                ttl_hours = metadata.get('ttl_hours', 24)
                if created_at:
                    created = datetime.fromisoformat(created_at)
                    if datetime.now() > created + timedelta(hours=ttl_hours):
                        self._remove_cache_file(file)
                        cleared += 1
        
        return cleared
    
    def get_cache_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        if not self.cache_dir.exists():
            return {
                'total_files': 0,
                'total_size_bytes': 0,
                'cache_dir': str(self.cache_dir),
            }
        
        total_files = 0
        total_size = 0
        
        for file in self.cache_dir.glob('*.parquet'):
            if file.is_file():
                total_files += 1
                total_size += file.stat().st_size
        
        return {
            'total_files': total_files,
            'total_size_bytes': total_size,
            'cache_dir': str(self.cache_dir),
        }
