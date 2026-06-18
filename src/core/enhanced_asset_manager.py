"""
增强版资产管理器 - 集成数据库和关注机制

设计目标：
1. 集成 SQLite 数据库存储
2. 实现"关注即导入"的自动化流程
3. 提供实时价格曲线和波动率计算
4. 保持向后兼容性
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from .interfaces import IAssetManager
from .cache import get_cache, cached
from .database import get_database, DatabaseManager
from ..asset_importer import AssetImporter, AssetDefinition


class EnhancedAssetManager(IAssetManager):
    """
    增强版资产管理器 - 支持数据库存储和关注机制
    
    核心功能：
    1. 自动导入用户关注的资产
    2. 存储历史价格数据到数据库
    3. 实时计算波动率和指标
    4. 提供人类友好的交互接口
    """
    
    def __init__(self, registry_path: str = "config/asset_registry.yaml",
                 enable_cache: bool = True):
        """
        初始化增强资产管理器
        
        Args:
            registry_path: 资产注册表路径（用于向后兼容）
            enable_cache: 是否启用缓存
        """
        self.enable_cache = enable_cache
        self.cache = get_cache() if enable_cache else None
        
        # 数据库管理器
        self.db = get_database()
        
        # 传统导入器（用于向后兼容）
        self.importer = AssetImporter(registry_path)
        
        # 数据获取器工厂 (factory module removed; legacy path kept for compatibility)
        try:
            from src.data_core.fetchers.factory import get_factory
            self.fetcher_factory = get_factory()
        except ImportError:
            self.fetcher_factory = None
        
        # 迁移现有数据到数据库
        self._migrate_legacy_data()
        
        # 缓存配置
        self.price_cache_ttl = 300  # 5分钟
        self.metric_cache_ttl = 3600  # 1小时
        
    def _migrate_legacy_data(self):
        """迁移现有文件系统数据到数据库"""
        try:
            migrated_count = self.db.migrate_from_file_system()
            if migrated_count > 0:
                print(f"[EnhancedAssetManager] 已从文件系统迁移 {migrated_count} 个资产到数据库")
        except Exception as e:
            print(f"[EnhancedAssetManager] 数据迁移失败: {e}")
    
    # ==================== IAssetProvider 接口实现 ====================
    
    def get_asset_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取资产详细信息（集成数据库）
        
        流程：
        1. 查询数据库中的资产信息
        2. 如果不存在，自动导入并保存到数据库
        3. 获取最新价格和指标
        4. 返回完整信息
        """
        # 首先尝试从数据库获取
        db_asset = self.db.get_asset(symbol)
        
        if not db_asset:
            # 资产不存在，尝试自动导入
            print(f"[自动导入] 资产 {symbol} 不存在，正在导入...")
            result = self.import_asset(symbol)
            if not result.get("success"):
                return {
                    "symbol": symbol,
                    "error": f"资产不存在且导入失败: {result.get('error', '未知错误')}",
                    "exists": False
                }
            
            # 重新从数据库获取
            db_asset = self.db.get_asset(symbol)
            if not db_asset:
                return {
                    "symbol": symbol,
                    "error": "导入成功但数据库记录未找到",
                    "exists": False
                }
        
        # 构建返回结果
        result = {
            "symbol": db_asset['symbol'],
            "name": db_asset['name'],
            "asset_type": db_asset['asset_type'],
            "currency": db_asset['currency'],
            "source": db_asset['source'],
            "last_updated": db_asset['last_updated'],
            "exists": True,
            "imported": True,
            "attributes": db_asset.get('attributes', {}),
            "database_id": db_asset['id']
        }
        
        # 获取价格信息
        price_info = self._get_enhanced_price_info(symbol)
        if price_info:
            result["price_info"] = price_info
        
        # 计算并获取波动率
        volatility = self.db.calculate_and_save_volatility(symbol, days=30)
        if volatility:
            result["volatility_30d"] = volatility
            result["volatility_info"] = {
                "value": volatility,
                "period": "30天",
                "annualized": True,
                "calculation_method": "历史收益率标准差",
                "last_calculated": datetime.now().isoformat()
            }
        
        return result
    
    def list_assets(self, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有资产（从数据库）"""
        all_assets = self.db.list_assets(limit=1000)  # 假设不超过1000个资产
        
        if filter_type:
            filtered = []
            for asset in all_assets:
                # 检查资产类型是否匹配
                asset_type = asset.get('asset_type', '')
                if filter_type.lower() == asset_type.lower():
                    filtered.append(asset)
                elif self._is_asset_type_match(asset_type, filter_type):
                    filtered.append(asset)
            
            return filtered
        
        return all_assets
    
    def search_assets(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """搜索资产（优先从数据库）"""
        # 首先尝试数据库搜索
        db_results = self.db.search_assets(query, limit)
        
        if db_results:
            return db_results
        
        # 如果数据库没有结果，使用传统方法
        from src.core.asset_manager import AssetManager
        legacy_manager = AssetManager()
        return legacy_manager.search_assets(query, limit)
    
    # ==================== IAssetImporter 接口实现 ====================
    
    def import_asset(self, symbol: str, asset_type: Optional[str] = None,
                    refresh: bool = False) -> Dict[str, Any]:
        """
        导入资产（保存到数据库）
        
        流程：
        1. 使用传统导入器获取资产信息
        2. 保存到数据库
        3. 获取历史价格数据
        4. 保存价格到数据库
        5. 计算初始指标
        """
        try:
            # 1. 使用传统导入器
            print(f"[导入] 开始导入资产: {symbol}")
            asset_def = self.importer.import_asset(
                symbol=symbol,
                asset_type=asset_type,
                refresh=refresh
            )
            
            if not asset_def:
                return {
                    "success": False,
                    "error": f"无法导入资产 {symbol}",
                    "symbol": symbol
                }
            
            # 2. 保存到数据库
            asset_data = asset_def.to_dict()
            asset_id = self.db.add_or_update_asset(asset_data)
            
            print(f"[导入] 资产已保存到数据库，ID: {asset_id}")
            
            # 3. 获取历史价格数据
            price_data_fetched = self._fetch_and_save_price_history(symbol, asset_def.asset_type)
            
            # 4. 计算初始指标
            metrics_calculated = self._calculate_initial_metrics(symbol)
            
            # 返回结果
            result = {
                "success": True,
                "message": f"成功导入资产: {asset_def.name}",
                "data": asset_data,
                "database": {
                    "asset_id": asset_id,
                    "price_records_added": price_data_fetched,
                    "metrics_calculated": metrics_calculated
                }
            }
            
            # 清理缓存
            self._invalidate_caches(symbol)
            
            return result
            
        except Exception as e:
            import traceback
            traceback.print_exc()
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
            
            print(f"[批量导入] ({i+1}/{len(symbols)}) {symbol}")
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
            # 获取所有资产
            assets = self.db.list_assets(limit=1000)
            symbols = [asset['symbol'] for asset in assets]
        
        results = {}
        updated_count = 0
        
        for symbol in symbols:
            try:
                # 获取资产信息
                asset = self.db.get_asset(symbol)
                if not asset:
                    results[symbol] = False
                    continue
                
                # 获取最新的价格数据
                price_added = self._fetch_and_save_latest_price(symbol, asset['asset_type'])
                
                results[symbol] = price_added > 0
                if price_added > 0:
                    updated_count += 1
                
                # 重新计算指标
                self._calculate_initial_metrics(symbol)
                
                # 清理缓存
                self._invalidate_caches(symbol)
                
            except Exception as e:
                print(f"[更新价格失败] {symbol}: {e}")
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
        """注册新的资产类型（委托给工厂）"""
        try:
            from src.data_core.fetchers.factory import register_fetcher
            register_fetcher(asset_type, fetcher_class)
            print(f"[EnhancedAssetManager] 已注册新资产类型: {asset_type}")
            return True
        except Exception as e:
            print(f"[EnhancedAssetManager] 注册资产类型失败: {e}")
            return False
    
    def get_supported_types(self) -> List[str]:
        """获取支持的资产类型列表"""
        try:
            from src.data_core.fetchers.factory import get_factory
            factory = get_factory()
            return factory.get_supported_asset_types()
        except:
            return ['cn_stock', 'cn_fund', 'us_equity', 'currency']
    
    def get_fetcher_for_type(self, asset_type: str) -> Optional[Any]:
        """获取资产类型对应的Fetcher"""
        if self.fetcher_factory is None:
            return None
        return self.fetcher_factory.get_fetcher(asset_type)
    
    # ==================== 关注机制相关方法 ====================
    
    def add_to_watchlist(self, symbol: str, user_id: str = 'default',
                        notes: str = '') -> Dict[str, Any]:
        """
        添加资产到关注列表（关注即导入）
        
        流程：
        1. 检查资产是否存在，如果不存在则自动导入
        2. 添加到用户关注列表
        3. 开始定期价格更新
        """
        try:
            # 1. 确保资产存在
            asset = self.db.get_asset(symbol)
            if not asset:
                # 自动导入资产
                import_result = self.import_asset(symbol)
                if not import_result.get("success"):
                    return {
                        "success": False,
                        "error": f"无法导入资产: {import_result.get('error', '未知错误')}",
                        "symbol": symbol
                    }
                
                # 重新获取资产
                asset = self.db.get_asset(symbol)
                if not asset:
                    return {
                        "success": False,
                        "error": "导入成功但无法获取资产信息",
                        "symbol": symbol
                    }
            
            # 2. 添加到关注列表
            success = self.db.add_to_watchlist(symbol, user_id, notes)
            
            if success:
                # 3. 触发首次价格更新
                self.update_asset_prices([symbol])
                
                # 4. 计算指标
                self._calculate_initial_metrics(symbol)
                
                return {
                    "success": True,
                    "message": f"已关注资产: {asset['name']} ({symbol})",
                    "data": {
                        "symbol": symbol,
                        "name": asset['name'],
                        "asset_type": asset['asset_type'],
                        "added_at": datetime.now().isoformat(),
                        "notes": notes,
                        "initial_metrics_calculated": True
                    }
                }
            else:
                return {
                    "success": False,
                    "error": "无法添加到关注列表",
                    "symbol": symbol
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"关注资产失败: {str(e)}",
                "symbol": symbol
            }
    
    def remove_from_watchlist(self, symbol: str, user_id: str = 'default') -> Dict[str, Any]:
        """从关注列表中移除资产"""
        success = self.db.remove_from_watchlist(symbol, user_id)
        
        if success:
            return {
                "success": True,
                "message": f"已取消关注资产: {symbol}",
                "symbol": symbol
            }
        else:
            return {
                "success": False,
                "error": f"无法从关注列表移除资产: {symbol}",
                "symbol": symbol
            }
    
    def get_watchlist(self, user_id: str = 'default') -> List[Dict[str, Any]]:
        """获取用户的关注列表"""
        return self.db.get_watchlist(user_id)
    
    def get_watchlist_with_metrics(self, user_id: str = 'default') -> List[Dict[str, Any]]:
        """获取关注列表并包含最新指标"""
        watchlist = self.db.get_watchlist(user_id)
        
        for item in watchlist:
            symbol = item['symbol']
            
            # 添加价格信息
            price_info = self._get_enhanced_price_info(symbol)
            if price_info:
                item['price_info'] = price_info
            
            # 添加波动率
            volatility = self.db.get_recent_volatility(symbol, days=30)
            if volatility:
                item['volatility_30d'] = volatility
            
            # 添加其他指标
            metrics = self._get_asset_metrics(symbol)
            item['metrics'] = metrics
        
        return watchlist
    
    def is_in_watchlist(self, symbol: str, user_id: str = 'default') -> bool:
        """检查资产是否在用户关注列表中"""
        return self.db.is_in_watchlist(symbol, user_id)
    
    # ==================== 价格曲线和指标相关方法 ====================
    
    def get_price_history_with_analysis(self, symbol: str, days: int = 30) -> Dict[str, Any]:
        """
        获取价格历史并进行技术分析
        
        返回：
        - 原始价格数据
        - 移动平均线
        - RSI指标
        - 波动率带
        - 支撑阻力位
        """
        # 获取价格历史
        price_df = self.db.get_price_history(symbol, days)
        
        if price_df.empty:
            return {
                "success": False,
                "error": f"无法获取 {symbol} 的价格历史",
                "symbol": symbol
            }
        
        try:
            # 计算技术指标
            analysis = self._calculate_technical_analysis(price_df)
            
            # 计算波动率
            returns = price_df['Close'].pct_change().dropna()
            volatility = returns.std() * (252 ** 0.5) if len(returns) > 0 else 0
            
            # 构建返回结果
            result = {
                "success": True,
                "symbol": symbol,
                "period_days": days,
                "data_points": len(price_df),
                "date_range": {
                    "start": price_df.index[0].strftime("%Y-%m-%d"),
                    "end": price_df.index[-1].strftime("%Y-%m-%d")
                },
                "price_data": price_df.reset_index().to_dict('records'),
                "analysis": analysis,
                "volatility": {
                    "daily": float(returns.std()) if len(returns) > 0 else 0,
                    "annualized": float(volatility),
                    "period": f"{days}天"
                },
                "performance": {
                    "total_return": float((price_df['Close'].iloc[-1] / price_df['Close'].iloc[0] - 1)),
                    "avg_daily_return": float(returns.mean()) if len(returns) > 0 else 0,
                    "max_drawdown": float(self._calculate_max_drawdown(price_df['Close']))
                }
            }
            
            return result
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": f"分析价格数据失败: {str(e)}",
                "symbol": symbol,
                "price_data": price_df.reset_index().to_dict('records')  # 至少返回原始数据
            }
    
    def get_asset_metrics_dashboard(self, symbol: str) -> Dict[str, Any]:
        """
        获取资产指标仪表板
        
        包含：
        1. 基本信息
        2. 价格信息
        3. 波动率指标
        4. 技术指标
        5. 风险指标
        """
        # 获取基本信息
        asset_info = self.get_asset_info(symbol)
        
        # 获取价格历史分析
        price_analysis = self.get_price_history_with_analysis(symbol, days=90)
        
        # 获取关注状态
        watchlist_status = self.db.is_in_watchlist(symbol)
        
        # 组合结果
        result = {
            "symbol": symbol,
            "basic_info": {
                "name": asset_info.get('name', symbol),
                "asset_type": asset_info.get('asset_type', 'unknown'),
                "currency": asset_info.get('currency', 'CNY'),
                "last_updated": asset_info.get('last_updated'),
                "exists": asset_info.get('exists', False)
            },
            "price_info": asset_info.get('price_info', {}),
            "watchlist_status": watchlist_status,
            "price_analysis": price_analysis if price_analysis.get('success') else None,
            "calculated_metrics": self._get_all_metrics(symbol),
            "recommendations": self._generate_recommendations(symbol, asset_info)
        }
        
        return result
    
    # ==================== 辅助方法 ====================
    
    def _fetch_and_save_price_history(self, symbol: str, asset_type: str, 
                                     days: int = 365, force_refresh: bool = False) -> int:
        """获取并保存历史价格数据（优化版：优先使用数据库已有数据）"""
        try:
            # 首先检查数据库是否已经有最近的价格数据
            if not force_refresh:
                latest_price = self.db.get_latest_price(symbol)
                if latest_price:
                    # 检查最新价格是否在最近3天内
                    latest_date_str = latest_price.get('date')
                    if latest_date_str:
                        try:
                            latest_date = datetime.strptime(latest_date_str, '%Y-%m-%d')
                            days_since_last = (datetime.now() - latest_date).days
                            if days_since_last <= 3:
                                print(f"[价格获取] 数据库已有最近价格 ({days_since_last}天前)，跳过下载: {symbol}")
                                return 0
                        except:
                            pass
            
            # 如果数据库没有最近数据，或者强制刷新，则获取价格数据
            # 获取fetcher
            fetcher = self.get_fetcher_for_type(asset_type)
            if not fetcher:
                print(f"[价格获取] 无对应fetcher: {asset_type}")
                return 0
            
            # 设置日期范围：如果没有数据库数据，下载30天；如果有但比较旧，下载缺失的天数
            end_date = datetime.now().strftime("%Y-%m-%d")
            
            # 如果数据库有数据，计算需要补充的天数
            if latest_price and not force_refresh:
                try:
                    latest_date = datetime.strptime(latest_price.get('date'), '%Y-%m-%d')
                    days_since_last = (datetime.now() - latest_date).days
                    # 如果数据比较旧（超过3天），但还不是特别旧，只下载最近10天
                    if days_since_last > 3 and days_since_last < 30:
                        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
                        print(f"[价格获取] 数据库数据较旧 ({days_since_last}天)，下载最近10天价格: {symbol}")
                    else:
                        # 数据太旧或者没有数据，下载30天
                        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                        print(f"[价格获取] 下载 {symbol} ({asset_type}) 历史价格: {start_date} 至 {end_date}")
                except:
                    # 解析日期失败，下载30天
                    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                    print(f"[价格获取] 下载 {symbol} ({asset_type}) 历史价格: {start_date} 至 {end_date}")
            else:
                # 没有数据库数据，下载30天
                start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                print(f"[价格获取] 下载 {symbol} ({asset_type}) 历史价格: {start_date} 至 {end_date}")
            
            # 获取价格数据
            price_df = fetcher.fetch(symbol, start_date=start_date, end_date=end_date)
            
            if price_df is None or price_df.empty:
                print(f"[价格获取] 无数据: {symbol}")
                return 0
            
            # 保存到数据库
            added_count = self.db.add_price_history(symbol, price_df)
            print(f"[价格获取] 已保存 {added_count} 条价格记录: {symbol}")
            
            return added_count
            
        except Exception as e:
            print(f"[价格获取失败] {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return 0
    
    def _fetch_and_save_latest_price(self, symbol: str, asset_type: str) -> int:
        """获取并保存最新价格数据"""
        try:
            # 获取fetcher
            fetcher = self.get_fetcher_for_type(asset_type)
            if not fetcher:
                return 0
            
            # 获取最近30天数据以获取最新价格
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            
            price_df = fetcher.fetch(symbol, start_date=start_date, end_date=end_date)
            
            if price_df is None or price_df.empty:
                return 0
            
            # 只保存最新的几条记录
            recent_df = price_df.tail(5)
            
            price_data_list = []
            for idx, row in recent_df.iterrows():
                date_str = idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)
                
                price_data_list.append({
                    'date': date_str,
                    'open': float(row.get('open', row.get('Close', 0))),
                    'high': float(row.get('high', row.get('Close', 0))),
                    'low': float(row.get('low', row.get('Close', 0))),
                    'close': float(row.get('close', row.get('Close', 0))),
                    'volume': float(row.get('volume', 0)),
                    'source': 'fetcher'
                })
                
            try:
                # 使用批量添加方法提升性能
                added_count = self.db.add_price_data_batch(symbol, price_data_list)
            except Exception as e:
                print(f"[最新价格保存失败] {symbol}: {e}")
                added_count = 0
            
            return added_count
            
        except Exception as e:
            print(f"[最新价格获取失败] {symbol}: {e}")
            return 0
    
    def _calculate_initial_metrics(self, symbol: str) -> Dict[str, float]:
        """计算初始指标"""
        metrics = {}
        
        try:
            # 计算30天波动率
            volatility_30d = self.db.calculate_and_save_volatility(symbol, days=30)
            if volatility_30d:
                metrics['volatility_30d'] = volatility_30d
            
            # 计算60天波动率
            volatility_60d = self.db.calculate_and_save_volatility(symbol, days=60)
            if volatility_60d:
                metrics['volatility_60d'] = volatility_60d
            
            # 计算90天波动率
            volatility_90d = self.db.calculate_and_save_volatility(symbol, days=90)
            if volatility_90d:
                metrics['volatility_90d'] = volatility_90d
            
            print(f"[指标计算] {symbol}: 计算了 {len(metrics)} 个指标")
            
        except Exception as e:
            print(f"[指标计算失败] {symbol}: {e}")
        
        return metrics
    
    def _get_enhanced_price_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取增强的价格信息"""
        try:
            # 获取最新价格
            latest_price = self.db.get_latest_price(symbol)
            if not latest_price:
                return None
            
            # 获取价格历史用于计算
            price_df = self.db.get_price_history(symbol, days=30)
            if price_df.empty:
                return {
                    'latest': latest_price['close'],
                    'date': latest_price['date'],
                    'source': 'database'
                }
            
            # 计算收益和波动率
            returns = price_df['Close'].pct_change().dropna()
            
            return {
                'latest': latest_price['close'],
                'date': latest_price['date'],
                'open': latest_price.get('open'),
                'high': latest_price.get('high'),
                'low': latest_price.get('low'),
                'volume': latest_price.get('volume'),
                'returns_30d': float(returns.mean() * 21) if len(returns) > 0 else None,
                'volatility_30d': float(returns.std() * (21 ** 0.5)) if len(returns) > 0 else None,
                'source': 'database'
            }
            
        except Exception as e:
            print(f"[价格信息获取失败] {symbol}: {e}")
            return None
    
    def _calculate_technical_analysis(self, price_df: pd.DataFrame) -> Dict[str, Any]:
        """计算技术分析指标"""
        try:
            close_series = price_df['Close']
            
            # 移动平均线
            ma20 = close_series.rolling(window=20).mean()
            ma50 = close_series.rolling(window=50).mean()
            ma200 = close_series.rolling(window=200).mean()
            
            # RSI指标（简化版）
            delta = close_series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            # 布林带
            bb_middle = close_series.rolling(window=20).mean()
            bb_std = close_series.rolling(window=20).std()
            bb_upper = bb_middle + 2 * bb_std
            bb_lower = bb_middle - 2 * bb_std
            
            return {
                "moving_averages": {
                    "ma20": ma20.dropna().tolist(),
                    "ma50": ma50.dropna().tolist(),
                    "ma200": ma200.dropna().tolist()
                },
                "rsi": rsi.dropna().tolist(),
                "bollinger_bands": {
                    "upper": bb_upper.dropna().tolist(),
                    "middle": bb_middle.dropna().tolist(),
                    "lower": bb_lower.dropna().tolist()
                },
                "support_resistance": self._calculate_support_resistance(price_df)
            }
            
        except Exception as e:
            print(f"[技术分析计算失败]: {e}")
            return {}
    
    def _calculate_support_resistance(self, price_df: pd.DataFrame) -> Dict[str, Any]:
        """计算支撑阻力位（简化版）"""
        try:
            close_prices = price_df['Close'].tolist()
            high_prices = price_df['High'].tolist() if 'High' in price_df.columns else close_prices
            low_prices = price_df['Low'].tolist() if 'Low' in price_df.columns else close_prices
            
            # 使用近期高低点
            recent_high = max(high_prices[-20:]) if len(high_prices) >= 20 else max(high_prices)
            recent_low = min(low_prices[-20:]) if len(low_prices) >= 20 else min(low_prices)
            current_price = close_prices[-1]
            
            return {
                "resistance": float(recent_high),
                "support": float(recent_low),
                "current": float(current_price),
                "distance_to_resistance": float((recent_high - current_price) / current_price),
                "distance_to_support": float((current_price - recent_low) / current_price)
            }
        except:
            return {}
    
    def _calculate_max_drawdown(self, price_series: pd.Series) -> float:
        """计算最大回撤"""
        try:
            cumulative_max = price_series.expanding().max()
            drawdown = (price_series - cumulative_max) / cumulative_max
            return float(drawdown.min())
        except:
            return 0.0
    
    def _get_asset_metrics(self, symbol: str) -> Dict[str, Any]:
        """获取资产的所有指标"""
        metrics = {}
        
        # 从数据库获取已计算的指标
        metric_names = ['volatility', 'returns', 'sharpe', 'max_drawdown']
        
        for metric_name in metric_names:
            for period in [30, 60, 90]:
                value = self.db.get_metric(symbol, metric_name, period)
                if value:
                    key = f"{metric_name}_{period}d"
                    metrics[key] = value
        
        return metrics
    
    def _get_all_metrics(self, symbol: str) -> Dict[str, Any]:
        """获取所有指标（包括实时计算）"""
        metrics = self._get_asset_metrics(symbol)
        
        # 添加实时计算的指标
        price_df = self.db.get_price_history(symbol, days=30)
        if not price_df.empty:
            returns = price_df['Close'].pct_change().dropna()
            
            # 夏普比率（简化版，假设无风险利率为4%）
            if len(returns) > 0:
                annual_return = returns.mean() * 252
                annual_volatility = returns.std() * (252 ** 0.5)
                risk_free_rate = 0.04
                
                if annual_volatility > 0:
                    sharpe_ratio = (annual_return - risk_free_rate) / annual_volatility
                    metrics['sharpe_ratio'] = float(sharpe_ratio)
                
                # 索提诺比率
                negative_returns = returns[returns < 0]
                downside_std = negative_returns.std() * (252 ** 0.5) if len(negative_returns) > 0 else 0
                
                if downside_std > 0:
                    sortino_ratio = (annual_return - risk_free_rate) / downside_std
                    metrics['sortino_ratio'] = float(sortino_ratio)
        
        return metrics
    
    def _generate_recommendations(self, symbol: str, asset_info: Dict[str, Any]) -> List[str]:
        """生成投资建议"""
        recommendations = []
        
        # 检查是否在关注列表
        if not self.db.is_in_watchlist(symbol):
            recommendations.append("该资产尚未关注，建议添加到关注列表以获取定期更新")
        
        # 检查价格信息
        price_info = asset_info.get('price_info')
        if not price_info:
            recommendations.append("缺乏价格信息，建议更新价格数据")
        
        # 检查波动率
        volatility = asset_info.get('volatility_30d')
        if volatility:
            if volatility > 0.3:
                recommendations.append("波动率较高（>30%），适合风险承受能力强的投资者")
            elif volatility < 0.1:
                recommendations.append("波动率较低（<10%），适合稳健型投资者")
        
        # 检查资产类型
        asset_type = asset_info.get('asset_type', '')
        if asset_type == 'cn_fund_qdii':
            recommendations.append("QDII基金涉及外汇风险，需关注汇率变化")
        elif asset_type == 'currency':
            recommendations.append("货币对交易需关注宏观经济和央行政策")
        
        return recommendations
    
    def _is_asset_type_match(self, detailed_type: str, simplified_type: str) -> bool:
        """检查资产类型是否匹配（简化类型 vs 详细类型）"""
        type_mapping = {
            'cn_stock': ['cn_stock_sh', 'cn_stock_sz'],
            'cn_fund': ['cn_fund_open', 'cn_fund_etf', 'cn_fund_qdii', 
                       'cn_fund_money', 'cn_fund_lof', 'cn_fund_index'],
            'us_equity': ['us_stock'],
            'currency': ['fx_pair']
        }
        
        if simplified_type in type_mapping:
            return detailed_type in type_mapping[simplified_type]
        
        return detailed_type == simplified_type
    
    def _invalidate_caches(self, symbol: str):
        """清理缓存"""
        if self.enable_cache and self.cache:
            # 清理资产相关缓存
            cache_keys = [
                f"asset_info:{symbol}",
                f"price_history:{symbol}",
                f"metrics:{symbol}"
            ]
            
            for key in cache_keys:
                self.cache.delete(key, "asset")
            
            # 清理关注列表缓存
            self.cache.clear_namespace("watchlist")


# 全局增强资产管理器实例
_enhanced_asset_manager_instance = None

def get_enhanced_asset_manager() -> EnhancedAssetManager:
    """
    获取全局增强资产管理器实例（单例模式）
    
    Returns:
        EnhancedAssetManager实例
    """
    global _enhanced_asset_manager_instance
    if _enhanced_asset_manager_instance is None:
        _enhanced_asset_manager_instance = EnhancedAssetManager()
    return _enhanced_asset_manager_instance