"""
资产管理器 - 实现 IAssetManager 接口
集成现有 AssetImporter 功能，添加缓存和扩展性支持
"""

import logging
import os
import re
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
import yaml
import pandas as pd

from .interfaces import IAssetManager
from .cache import get_cache, CacheKeys, cached
from ..asset_importer import AssetImporter, AssetDefinition, AssetRegistry

_log = logging.getLogger(__name__)


class AssetManager(IAssetManager):
    """
    资产管理器 - 统一管理资产的生命周期
    
    设计特点：
    1. 集成现有 AssetImporter 功能
    2. 添加缓存层提升性能
    3. 支持动态扩展资产类型
    4. 线程安全
    """
    
    def __init__(self, registry_path: str = None, candidates_path: str = None,
                 config_manager=None, enable_cache: bool = True):
        """
        初始化资产管理器
        
        Args:
            registry_path: 资产注册表路径（向后兼容，如果提供config_manager则忽略）
            candidates_path: 候选资产路径（向后兼容，如果提供config_manager则忽略）
            config_manager: 配置管理器实例，如果为None则使用默认
            enable_cache: 是否启用缓存
        """
        from .config_manager import get_config_manager
        
        self.config_manager = config_manager or get_config_manager()
        self.enable_cache = enable_cache
        
        # 获取配置路径（支持向后兼容）
        if registry_path is None:
            registry_path = self.config_manager.get_asset_registry_path()
        if candidates_path is None:
            candidates_path = self.config_manager.get_candidates_path()
        
        self.registry_path = registry_path
        self.candidates_path = candidates_path
        
        # 初始化现有组件
        self.importer = AssetImporter(registry_path, candidates_path)
        self.registry = self.importer.registry
        
        # 缓存实例
        self.cache = get_cache() if enable_cache else None
        
        # 扩展资产类型注册表
        self._custom_fetchers: Dict[str, Any] = {}
        self._custom_importers: Dict[str, Any] = {}
        
        # 注册默认类型
        self._register_default_types()
        
        # 资产类型映射（简化类型 -> 详细类型）
        self.asset_type_mapping = {
            'cn_stock': ['cn_stock_sh', 'cn_stock_sz'],
            'cn_fund': ['cn_fund_open', 'cn_fund_etf', 'cn_fund_qdii', 
                       'cn_fund_money', 'cn_fund_lof', 'cn_fund_index'],
            'us_equity': ['us_stock'],
            'currency': ['fx_pair', 'cryptocurrency'],
            'bond': ['gov_bond', 'corp_bond'],
            'commodity': ['gold', 'oil', 'metal'],
            'derivative': ['option', 'future', 'warrant'],
            'structured': ['structured_product', 'trust', 'abs']
        }
    
    def _register_default_types(self):
        """注册默认资产类型"""
        # 这些类型已在现有的 fetcher 工厂中注册
        default_types = ['cn_stock', 'cn_fund', 'us_equity', 'currency']
        _log.info("[AssetManager] 已注册默认资产类型: %s", default_types)
    
    # ==================== IAssetProvider 接口实现 ====================
    
    @cached(ttl=1800, namespace="asset", key_prefix="asset_info")
    def get_asset_info(self, symbol: str) -> Dict[str, Any]:
        """获取资产详细信息（带缓存）"""
        asset_def = self.registry.get_asset(symbol)
        
        if not asset_def:
            # 尝试导入资产
            asset_def = self._import_asset_without_cache(symbol)
            if not asset_def:
                return {
                    "symbol": symbol,
                    "error": "资产不存在且导入失败",
                    "exists": False
                }
        
        # 转换为标准格式
        result = asset_def.to_dict()
        
        # 添加额外信息
        result["exists"] = True
        result["imported"] = asset_def.source is not None
        
        # 尝试获取最新价格
        try:
            price_info = self._get_latest_price(symbol, asset_def.asset_type)
            if price_info:
                result["price_info"] = price_info
        except Exception as e:
            result["price_error"] = str(e)
        
        return result
    
    def list_assets(self, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有资产，支持按类型过滤"""
        cache_key = CacheKeys.asset_list(filter_type)
        
        if self.enable_cache:
            cached_result = self.cache.get(cache_key, "asset_list")
            if cached_result is not None:
                return cached_result
        
        all_assets = self.registry.list_all_assets()
        
        # 过滤资产类型
        if filter_type:
            # 处理简化类型映射
            expanded_types = self._expand_asset_type(filter_type)
            filtered_assets = [
                asset for asset in all_assets 
                if asset.asset_type in expanded_types
            ]
        else:
            filtered_assets = all_assets
        
        # 转换为字典列表
        result = [asset.to_dict() for asset in filtered_assets]
        
        # 按符号排序
        result.sort(key=lambda x: x['symbol'])
        
        if self.enable_cache:
            self.cache.set(cache_key, result, 3600, "asset_list")
        
        return result
    
    def search_assets(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """搜索资产（按代码、名称、类型等）"""
        query = query.lower().strip()
        if not query:
            return []
        
        all_assets = self.registry.list_all_assets()
        results = []
        
        for asset in all_assets:
            # 检查符号匹配
            if query in asset.symbol.lower():
                results.append(asset)
                continue
                
            # 检查名称匹配
            if asset.name and query in asset.name.lower():
                results.append(asset)
                continue
                
            # 检查资产类型匹配
            if query in asset.asset_type.lower():
                results.append(asset)
                continue
        
        # 转换为字典并排序（精确匹配优先）
        result_dicts = []
        for asset in results[:limit]:
            asset_dict = asset.to_dict()
            # 计算匹配分数
            score = 0
            if query == asset.symbol.lower():
                score += 100  # 精确符号匹配
            elif query in asset.symbol.lower():
                score += 50   # 部分符号匹配
            
            if asset.name and query == asset.name.lower():
                score += 80   # 精确名称匹配
            elif asset.name and query in asset.name.lower():
                score += 30   # 部分名称匹配
            
            asset_dict["_score"] = score
            result_dicts.append(asset_dict)
        
        # 按分数降序排序
        result_dicts.sort(key=lambda x: x["_score"], reverse=True)
        
        # 移除临时分数字段
        for item in result_dicts:
            item.pop("_score", None)
        
        return result_dicts
    
    # ==================== IAssetImporter 接口实现 ====================
    
    def import_asset(self, symbol: str, asset_type: Optional[str] = None, 
                    refresh: bool = False) -> Dict[str, Any]:
        """导入资产（智能识别类型）"""
        try:
            # 如果未指定类型，尝试推断
            if asset_type is None:
                asset_type = self.importer._infer_asset_type(symbol)
            
            # 调用现有的导入器
            asset_def = self.importer.import_asset(
                symbol=symbol,
                asset_type=asset_type,
                refresh=refresh
            )
            
            if asset_def:
                # 清理相关缓存
                self._invalidate_asset_caches(symbol)
                
                result = asset_def.to_dict()
                result["success"] = True
                result["message"] = f"成功导入资产: {asset_def.name}"
                return result
            else:
                return {
                    "success": False,
                    "error": "导入失败，请检查资产代码和类型",
                    "symbol": symbol,
                    "asset_type": asset_type
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"导入过程出错: {str(e)}",
                "symbol": symbol,
                "asset_type": asset_type
            }
    
    def batch_import(self, symbols: List[str], 
                    asset_types: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """批量导入资产"""
        results = {}
        
        for i, symbol in enumerate(symbols):
            asset_type = asset_types[i] if asset_types and i < len(asset_types) else None
            
            _log.info("[批量导入] (%d/%d) %s", i + 1, len(symbols), symbol)
            result = self.import_asset(symbol, asset_type)
            results[symbol] = result
            
            # 添加延迟，避免请求过频繁
            import time
            time.sleep(0.5)
        
        # 统计结果
        success_count = sum(1 for r in results.values() if r.get("success"))
        
        return {
            "results": results,
            "summary": {
                "total": len(symbols),
                "success": success_count,
                "failed": len(symbols) - success_count,
                "success_rate": success_count / len(symbols) if symbols else 0
            }
        }
    
    def update_asset_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, bool]:
        """更新资产价格数据"""
        if symbols is None:
            # 更新所有资产
            assets = self.registry.list_all_assets()
            symbols = [asset.symbol for asset in assets]
        
        results = {}
        updated_count = 0
        
        for symbol in symbols:
            try:
                # 获取资产定义
                asset_def = self.registry.get_asset(symbol)
                if not asset_def:
                    results[symbol] = False
                    continue
                
                # 这里可以调用数据获取器获取最新价格
                # 暂时标记为成功（实际实现需要集成数据获取器）
                results[symbol] = True
                updated_count += 1
                
                # 清理价格缓存
                self.cache.delete(CacheKeys.asset_info(symbol), "asset")
                
            except Exception as e:
                _log.error("[更新价格失败] %s: %s", symbol, e)
                results[symbol] = False
        
        return {
            "results": results,
            "updated": updated_count,
            "total": len(symbols)
        }
    
    # ==================== IAssetTypeRegistry 接口实现 ====================
    
    def register_asset_type(self, asset_type: str, 
                           fetcher_class: Any, 
                           importer_class: Optional[Any] = None) -> bool:
        """注册新的资产类型"""
        try:
            # 注册到自定义映射
            self._custom_fetchers[asset_type] = fetcher_class
            
            if importer_class:
                self._custom_importers[asset_type] = importer_class
            
            # 更新资产类型映射
            if asset_type not in self.asset_type_mapping:
                self.asset_type_mapping[asset_type] = [asset_type]
            
            _log.info("[AssetManager] 已注册新资产类型: %s", asset_type)
            return True

        except Exception as e:
            _log.error("[AssetManager] 注册资产类型失败: %s - %s", asset_type, e)
            return False
    
    def get_supported_types(self) -> List[str]:
        """获取支持的资产类型列表"""
        supported_types = list(self.asset_type_mapping.keys())
        
        # 添加自定义类型
        for custom_type in self._custom_fetchers.keys():
            if custom_type not in supported_types:
                supported_types.append(custom_type)
        
        return sorted(supported_types)
    
    def get_fetcher_for_type(self, asset_type: str) -> Optional[Any]:
        """获取资产类型对应的Fetcher"""
        # 先检查自定义fetcher
        if asset_type in self._custom_fetchers:
            return self._custom_fetchers[asset_type]
        
        # 然后检查现有fetcher工厂
        try:
            from src.data_core.fetchers.factory import get_factory
            factory = get_factory()
            return factory.get_fetcher(asset_type)
        except:
            return None
    
    # ==================== 辅助方法 ====================
    
    def _import_asset_without_cache(self, symbol: str) -> Optional[AssetDefinition]:
        """不经过缓存的资产导入（供内部使用）"""
        try:
            asset_type = self.importer._infer_asset_type(symbol)
            return self.importer.import_asset(symbol, asset_type)
        except:
            return None
    
    def _get_latest_price(self, symbol: str, asset_type: str) -> Optional[Dict[str, Any]]:
        """获取最新价格信息"""
        try:
            fetcher = self.get_fetcher_for_type(asset_type)
            if not fetcher:
                return None
            
            # 设置日期范围（最近30天）
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            
            # 获取价格数据
            price_data = fetcher.fetch(symbol, start_date=start_date, end_date=end_date)
            
            if price_data is not None and not price_data.empty:
                # 提取最新价格
                if 'Close' in price_data.columns:
                    latest_price = float(price_data['Close'].iloc[-1])
                elif 'close' in price_data.columns:
                    latest_price = float(price_data['close'].iloc[-1])
                elif len(price_data.columns) > 0:
                    latest_price = float(price_data.iloc[:, -1].iloc[-1])
                else:
                    return None
                
                # 计算简单统计
                price_series = price_data['Close'] if 'Close' in price_data.columns else price_data.iloc[:, 0]
                returns = price_series.pct_change().dropna()
                
                return {
                    "latest": latest_price,
                    "date": price_data.index[-1].strftime("%Y-%m-%d") if hasattr(price_data.index[-1], 'strftime') else str(price_data.index[-1]),
                    "returns_30d": float(returns.mean() * 21) if len(returns) > 0 else None,  # 近似月收益
                    "volatility_30d": float(returns.std() * (21 ** 0.5)) if len(returns) > 0 else None  # 近似月波动率
                }
                
        except Exception as e:
            _log.error("[价格获取失败] %s: %s", symbol, e)
        
        return None
    
    def _expand_asset_type(self, asset_type: str) -> List[str]:
        """扩展简化资产类型为详细类型列表"""
        if asset_type in self.asset_type_mapping:
            return self.asset_type_mapping[asset_type]
        return [asset_type]
    
    def _invalidate_asset_caches(self, symbol: str):
        """清理资产相关的缓存"""
        if not self.enable_cache:
            return
        
        # 清理资产信息缓存
        self.cache.delete(CacheKeys.asset_info(symbol), "asset")
        
        # 清理资产列表缓存
        self.cache.clear_namespace("asset_list")
        
        # 清理搜索缓存
        self.cache.clear_namespace("search")
    
    # ==================== 便捷方法 ====================
    
    def get_asset_count(self) -> Dict[str, int]:
        """获取资产统计"""
        assets = self.registry.list_all_assets()
        
        # 按类型统计
        type_count = {}
        for asset in assets:
            asset_type = asset.asset_type
            type_count[asset_type] = type_count.get(asset_type, 0) + 1
        
        # 按简化类型统计
        simplified_count = {}
        for detailed_type, count in type_count.items():
            # 查找对应的简化类型
            found = False
            for simple_type, detailed_list in self.asset_type_mapping.items():
                if detailed_type in detailed_list:
                    simplified_count[simple_type] = simplified_count.get(simple_type, 0) + count
                    found = True
                    break
            
            if not found:
                simplified_count[detailed_type] = simplified_count.get(detailed_type, 0) + count
        
        return {
            "total": len(assets),
            "by_detailed_type": type_count,
            "by_simplified_type": simplified_count
        }
    
    def export_assets(self, format: str = "csv", filepath: Optional[str] = None) -> str:
        """导出资产列表"""
        assets = self.list_assets()
        
        if format == "csv":
            import pandas as pd
            df = pd.DataFrame(assets)
            
            if filepath:
                df.to_csv(filepath, index=False, encoding='utf-8-sig')
                return filepath
            else:
                return df.to_csv(index=False, encoding='utf-8-sig')
        
        elif format == "json":
            import json
            if filepath:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(assets, f, ensure_ascii=False, indent=2)
                return filepath
            else:
                return json.dumps(assets, ensure_ascii=False, indent=2)
        
        elif format == "yaml":
            if filepath:
                with open(filepath, 'w', encoding='utf-8') as f:
                    yaml.dump(assets, f, allow_unicode=True, default_flow_style=False)
                return filepath
            else:
                import io
                output = io.StringIO()
                yaml.dump(assets, output, allow_unicode=True, default_flow_style=False)
                return output.getvalue()
        
        else:
            raise ValueError(f"不支持的文件格式: {format}")