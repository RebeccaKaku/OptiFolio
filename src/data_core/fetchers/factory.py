# src/data_core/fetchers/factory.py
"""
Fetcher工厂类，根据资产类型创建对应的Fetcher实例。
支持注册自定义的Fetcher类。
"""

from typing import Dict, Type, Optional
from src.data_core.interface import BaseFetcher
from .us_equity import UsEquityFetcher
from .open_end_fund import CnFundFetcher
from .cn_stock import CnStockFetcher
from .currency import CurrencyFetcher
import importlib


class FetcherFactory:
    """
    Fetcher工厂，负责根据资产类型创建对应的Fetcher实例。
    """
    
    # 默认映射：资产类型 -> Fetcher类
    _default_mappings = {
        # 简化类型（新配置使用）
        'cn_stock': CnStockFetcher,
        'cn_fund': CnFundFetcher,
        'us_equity': UsEquityFetcher,
        
        # 中国股票（旧类型，向后兼容）
        'cn_stock_sh': CnStockFetcher,
        'cn_stock_sz': CnStockFetcher,
        
        # 港股
        'hk_stock': CnStockFetcher,  # 暂时用CnStockFetcher
        
        # 中国基金（旧类型，向后兼容）
        'cn_fund_open': CnFundFetcher,
        'cn_fund_etf': CnFundFetcher,
        'cn_fund_qdii': CnFundFetcher,
        'cn_fund_money': CnFundFetcher,
        'cn_fund_lof': CnFundFetcher,
        'cn_fund_index': CnFundFetcher,
        
        # 货币
        'currency': CurrencyFetcher,
        
        # 指数
        'cn_index': CnStockFetcher,  # 暂时用CnStockFetcher
        
        # 向后兼容映射（其他旧类型）
        'cn_equity': CnStockFetcher,
        'a_share': CnStockFetcher,
        'cn_etf': CnFundFetcher,
        'us_stock': UsEquityFetcher,
        'cn_stock_a': CnStockFetcher,
        'cn_a_stock': CnStockFetcher,
    }
    
    def __init__(self):
        # 从默认映射开始，允许后续注册覆盖
        self._mappings = self._default_mappings.copy()
        
        # 缓存已创建的Fetcher实例 (singleton模式)
        self._fetcher_cache: Dict[str, BaseFetcher] = {}
    
    def register(self, asset_type: str, fetcher_class: Type[BaseFetcher]) -> None:
        """
        注册新的资产类型和对应的Fetcher类。
        
        Args:
            asset_type: 资产类型标识符
            fetcher_class: 对应的Fetcher类
        """
        self._mappings[asset_type] = fetcher_class
        print(f"    [Factory] 注册 {asset_type} -> {fetcher_class.__name__}")
    
    def register_from_module(self, module_path: str, class_name: str, asset_types: list) -> None:
        """
        从模块动态导入并注册Fetcher类。
        
        Args:
            module_path: 模块路径 (如 "src.data_core.fetchers.custom")
            class_name: 类名
            asset_types: 要关联的资产类型列表
        """
        try:
            module = importlib.import_module(module_path)
            fetcher_class = getattr(module, class_name)
            for asset_type in asset_types:
                self.register(asset_type, fetcher_class)
        except Exception as e:
            print(f"    [Factory Error] 无法从 {module_path} 导入 {class_name}: {e}")
    
    def get_fetcher(self, asset_type: str) -> Optional[BaseFetcher]:
        """
        根据资产类型获取Fetcher实例（单例模式）。
        
        Args:
            asset_type: 资产类型
        
        Returns:
            Fetcher实例，如果没有找到则返回None
        """
        # 首先检查缓存
        if asset_type in self._fetcher_cache:
            return self._fetcher_cache[asset_type]
        
        # 查找对应的Fetcher类
        if asset_type not in self._mappings:
            print(f"    [Factory Error] 未注册的资产类型: {asset_type}")
            return None
        
        fetcher_class = self._mappings[asset_type]
        
        try:
            # 创建实例并缓存
            fetcher = fetcher_class()
            self._fetcher_cache[asset_type] = fetcher
            return fetcher
        except Exception as e:
            print(f"    [Factory Error] 无法创建 {fetcher_class.__name__} 实例: {e}")
            return None
    
    def get_fetcher_for_asset(self, asset_config: dict) -> Optional[BaseFetcher]:
        """
        根据资产配置获取Fetcher实例。
        
        Args:
            asset_config: 资产配置字典，必须包含'type'键
        
        Returns:
            Fetcher实例
        """
        asset_type = asset_config.get('type')
        if not asset_type:
            print(f"    [Factory Error] 资产配置缺少'type'字段: {asset_config}")
            return None
        
        return self.get_fetcher(asset_type)
    
    def create_all_fetchers(self) -> Dict[str, BaseFetcher]:
        """
        创建所有已注册类型的Fetcher实例。
        
        Returns:
            资产类型到Fetcher实例的字典
        """
        fetchers = {}
        for asset_type in self._mappings:
            fetcher = self.get_fetcher(asset_type)
            if fetcher:
                fetchers[asset_type] = fetcher
        
        return fetchers
    
    def get_supported_asset_types(self) -> list:
        """
        获取所有支持的资产类型。
        
        Returns:
            资产类型列表
        """
        return list(self._mappings.keys())
    
    def clear_cache(self) -> None:
        """清除Fetcher缓存"""
        self._fetcher_cache.clear()
        print("    [Factory] 已清除Fetcher缓存")


# 全局单例工厂实例
_factory_instance = None

def get_factory() -> FetcherFactory:
    """
    获取全局Fetcher工厂实例（单例模式）。
    
    Returns:
        FetcherFactory实例
    """
    global _factory_instance
    if _factory_instance is None:
        _factory_instance = FetcherFactory()
    return _factory_instance

def register_fetcher(asset_type: str, fetcher_class: Type[BaseFetcher]) -> None:
    """
    向全局工厂注册Fetcher类。
    
    Args:
        asset_type: 资产类型
        fetcher_class: Fetcher类
    """
    factory = get_factory()
    factory.register(asset_type, fetcher_class)

def get_fetcher(asset_type: str) -> Optional[BaseFetcher]:
    """
    从全局工厂获取Fetcher实例。
    
    Args:
        asset_type: 资产类型
    
    Returns:
        Fetcher实例
    """
    factory = get_factory()
    return factory.get_fetcher(asset_type)