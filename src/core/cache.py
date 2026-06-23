"""
缓存模块 - 实现简单的内存缓存，支持TTL和命名空间

设计特点：
1. 内存缓存为主，未来可扩展为Redis等
2. 支持TTL（生存时间）
3. 支持命名空间隔离
4. 线程安全（使用锁）
"""

import time
import threading
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta


class MemoryCache:
    """内存缓存实现"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._default_ttl = 3600  # 1小时
        
    def _get_namespace_lock(self, namespace: str) -> threading.Lock:
        """获取命名空间锁"""
        if namespace not in self._locks:
            self._locks[namespace] = threading.Lock()
        return self._locks[namespace]
    
    def _get_full_key(self, key: str, namespace: str) -> str:
        """获取完整缓存键"""
        return f"{namespace}:{key}"
    
    def get(self, key: str, namespace: str = "default") -> Optional[Any]:
        """获取缓存值"""
        full_key = self._get_full_key(key, namespace)
        
        with self._get_namespace_lock(namespace):
            if full_key not in self._cache:
                return None
                
            entry = self._cache[full_key]
            expire_time = entry.get("expire_time")
            
            # 检查是否过期
            if expire_time and time.time() > expire_time:
                # 过期，删除并返回None
                del self._cache[full_key]
                return None
                
            return entry.get("value")
    
    def set(self, key: str, value: Any, ttl: int = 3600, 
           namespace: str = "default") -> bool:
        """设置缓存值"""
        full_key = self._get_full_key(key, namespace)
        
        with self._get_namespace_lock(namespace):
            expire_time = None
            if ttl > 0:
                expire_time = time.time() + ttl
                
            self._cache[full_key] = {
                "value": value,
                "expire_time": expire_time,
                "created_at": time.time(),
                "namespace": namespace,
                "key": key
            }
            return True
    
    def delete(self, key: str, namespace: str = "default") -> bool:
        """删除缓存值"""
        full_key = self._get_full_key(key, namespace)
        
        with self._get_namespace_lock(namespace):
            if full_key in self._cache:
                del self._cache[full_key]
                return True
            return False
    
    def clear_namespace(self, namespace: str = "default") -> bool:
        """清除命名空间下的所有缓存"""
        keys_to_delete = []
        
        with self._get_namespace_lock(namespace):
            for full_key in list(self._cache.keys()):
                if full_key.startswith(f"{namespace}:"):
                    keys_to_delete.append(full_key)
            
            for full_key in keys_to_delete:
                del self._cache[full_key]
                
            return len(keys_to_delete) > 0
    
    def get_stats(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with threading.Lock():
            total_entries = len(self._cache)
            namespaces: Dict[str, int] = {}
            expired_count = 0
            
            current_time = time.time()
            
            for full_key, entry in self._cache.items():
                # 提取命名空间
                ns = entry.get("namespace", "unknown")
                namespaces[ns] = namespaces.get(ns, 0) + 1
                
                # 检查是否过期
                expire_time = entry.get("expire_time")
                if expire_time and current_time > expire_time:
                    expired_count += 1
            
            # 如果指定了命名空间，只统计该命名空间
            if namespace:
                ns_count = namespaces.get(namespace, 0)
                return {
                    "namespace": namespace,
                    "entries": ns_count,
                    "expired_entries": expired_count,
                    "total_entries": total_entries
                }
            else:
                return {
                    "total_entries": total_entries,
                    "expired_entries": expired_count,
                    "namespaces": namespaces,
                    "memory_usage": f"{self._estimate_memory_usage()} bytes"
                }
    
    def _estimate_memory_usage(self) -> int:
        """粗略估计内存使用量"""
        import sys
        total_size = 0
        for key, value in self._cache.items():
            total_size += sys.getsizeof(key)
            total_size += sys.getsizeof(value)
        return total_size
    
    def cleanup_expired(self) -> int:
        """清理过期缓存，返回清理的数量"""
        expired_keys = []
        current_time = time.time()
        
        with threading.Lock():
            for full_key, entry in self._cache.items():
                expire_time = entry.get("expire_time")
                if expire_time and current_time > expire_time:
                    expired_keys.append(full_key)
            
            for full_key in expired_keys:
                del self._cache[full_key]
            
            return len(expired_keys)


# 全局缓存实例（单例模式）
_cache_instance: Optional[MemoryCache] = None

def get_cache() -> MemoryCache:
    """获取全局缓存实例"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MemoryCache()
    return _cache_instance


# 缓存键生成器
class CacheKeys:
    """预定义的缓存键"""
    
    @staticmethod
    def asset_info(symbol: str) -> str:
        """资产信息缓存键"""
        return f"asset_info:{symbol}"
    
    @staticmethod
    def asset_prices(symbol: str, start_date: str, end_date: str) -> str:
        """资产价格数据缓存键"""
        return f"asset_prices:{symbol}:{start_date}:{end_date}"
    
    @staticmethod
    def portfolio_value(base_currency: str) -> str:
        """组合价值缓存键"""
        return f"portfolio_value:{base_currency}"
    
    @staticmethod
    def asset_list(filter_type: Optional[str] = None) -> str:
        """资产列表缓存键"""
        if filter_type:
            return f"asset_list:{filter_type}"
        return "asset_list:all"
    
    @staticmethod
    def fx_rate(from_currency: str, to_currency: str) -> str:
        """汇率缓存键"""
        return f"fx_rate:{from_currency}:{to_currency}"
    
    @staticmethod
    def asset_metrics(symbol: str, period: str) -> str:
        """资产指标缓存键"""
        return f"asset_metrics:{symbol}:{period}"


# 缓存装饰器
def cached(ttl: int = 3600, namespace: str = "default", key_prefix: str = ""):
    """
    缓存装饰器 - 自动缓存函数结果
    
    使用示例：
    @cached(ttl=1800, namespace="asset")
    def get_asset_info(symbol: str) -> Dict:
        # 实际获取逻辑
        pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache = get_cache()
            
            # 生成缓存键
            if key_prefix:
                cache_key = f"{key_prefix}:{args}:{kwargs}"
            else:
                cache_key = f"{func.__name__}:{args}:{kwargs}"
            
            # 尝试从缓存获取
            cached_result = cache.get(cache_key, namespace)
            if cached_result is not None:
                return cached_result
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 缓存结果
            cache.set(cache_key, result, ttl, namespace)
            
            return result
        return wrapper
    return decorator