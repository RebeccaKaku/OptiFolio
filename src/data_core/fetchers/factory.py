# src/data_core/fetchers/factory.py
"""
Fetcher工厂类，根据资产类型创建对应的Fetcher实例。
支持注册自定义的Fetcher类。
"""

from typing import Dict, Type, Optional, Union, Tuple
from src.data_core.interface import BaseFetcher
import importlib

FetcherSpec = Union[Type[BaseFetcher], Tuple[str, str]]


class FetcherFactory:
    """
    Fetcher工厂，负责根据资产类型创建对应的Fetcher实例。
    """
    
    # 默认映射：资产类型 -> Fetcher类
    _default_mappings: Dict[str, FetcherSpec] = {
        # 简化类型（新配置使用）
        'cn_stock': ('.cn_stock', 'CnStockFetcher'),
        'cn_fund': ('.open_end_fund', 'CnFundFetcher'),
        'us_equity': ('.us_equity', 'UsEquityFetcher'),
        
        # 中国股票（旧类型，向后兼容）
        'cn_stock_sh': ('.cn_stock', 'CnStockFetcher'),
        'cn_stock_sz': ('.cn_stock', 'CnStockFetcher'),
        
        # 港股
        'hk_stock': ('.cn_stock', 'CnStockFetcher'),  # 暂时用CnStockFetcher
        
        # 中国基金（旧类型，向后兼容）
        'cn_fund_open': ('.open_end_fund', 'CnFundFetcher'),
        'cn_fund_etf': ('.open_end_fund', 'CnFundFetcher'),
        'cn_fund_qdii': ('.open_end_fund', 'CnFundFetcher'),
        'cn_fund_money': ('.open_end_fund', 'CnFundFetcher'),
        'cn_fund_lof': ('.open_end_fund', 'CnFundFetcher'),
        'cn_fund_index': ('.open_end_fund', 'CnFundFetcher'),
        
        # 货币
        'currency': ('.currency', 'CurrencyFetcher'),
        
        # 指数
        'cn_index': ('.cn_stock', 'CnStockFetcher'),  # 暂时用CnStockFetcher
        
        # 向后兼容映射（其他旧类型）
        'cn_equity': ('.cn_stock', 'CnStockFetcher'),
        'a_share': ('.cn_stock', 'CnStockFetcher'),
        'cn_etf': ('.open_end_fund', 'CnFundFetcher'),
        'us_stock': ('.us_equity', 'UsEquityFetcher'),
        'cn_stock_a': ('.cn_stock', 'CnStockFetcher'),
        'cn_a_stock': ('.cn_stock', 'CnStockFetcher'),
    }
    
    def __init__(self):
        # 从默认映射开始，允许后续注册覆盖
        self._mappings: Dict[str, FetcherSpec] = self._default_mappings.copy()
        
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
        
        fetcher_class = self._resolve_fetcher_class(self._mappings[asset_type])
        if fetcher_class is None:
            return None
        
        try:
            # 创建实例并缓存
            fetcher = fetcher_class()
            self._fetcher_cache[asset_type] = fetcher
            return fetcher
        except Exception as e:
            print(f"    [Factory Error] 无法创建 {fetcher_class.__name__} 实例: {e}")
            return None

    def _resolve_fetcher_class(self, spec: FetcherSpec) -> Optional[Type[BaseFetcher]]:
        """延迟导入Fetcher类，避免缺少某个数据源依赖时拖垮整个工厂。"""
        if isinstance(spec, tuple):
            module_path, class_name = spec
            try:
                module = importlib.import_module(module_path, package=__package__)
                return getattr(module, class_name)
            except Exception as e:
                print(f"    [Factory Error] 无法导入 {class_name}: {e}")
                return None

        return spec
    
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
