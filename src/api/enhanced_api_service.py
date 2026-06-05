"""
增强版API服务 - 集成数据库和关注机制

设计目标：
1. 替换原有API服务，提供更强大的功能
2. 集成EnhancedAssetManager
3. 支持"关注即导入"的完整工作流
4. 提供人类友好的交互接口
"""

from typing import Dict, List, Any, Optional
from .portfolio_api import PortfolioAPI
from .dashboard_api import DashboardAPI
from src.core.enhanced_asset_manager import get_enhanced_asset_manager


class EnhancedAPIService:
    """
    增强版API服务 - 整合所有增强功能
    
    新增功能：
    1. 资产自动导入和关注机制
    2. 数据库持久化存储
    3. 增强的价格曲线和波动率计算
    4. 用户友好的交互接口
    """
    
    def __init__(self):
        """初始化增强API服务"""
        self.asset_manager = get_enhanced_asset_manager()
        self.portfolio_api = PortfolioAPI()
        self.dashboard_api = DashboardAPI()
    
    # ==================== 资产相关API（增强版）====================
    
    def import_asset(self, symbol: str, asset_type: Optional[str] = None,
                    refresh: bool = False) -> Dict[str, Any]:
        """
        导入资产（保存到数据库）
        
        与原有API兼容，但会保存到数据库并获取历史价格
        """
        return self.asset_manager.import_asset(symbol, asset_type, refresh)
    
    def batch_import_assets(self, symbols: List[str],
                           asset_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        批量导入资产（保存到数据库）
        """
        try:
            result = self.asset_manager.batch_import(symbols, asset_types)
            summary = result.get("summary", {})
            return {
                "success": True,
                "data": result,
                "message": (
                    f"批量导入完成: {summary.get('success', 0)}/"
                    f"{summary.get('total', len(symbols))} 个资产成功"
                )
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"批量导入资产失败: {str(e)}",
                "symbols": symbols
            }
    
    def get_asset_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取资产信息（自动导入如果不存在）
        
        新功能：如果资产不存在，自动导入并保存到数据库
        """
        try:
            asset_info = self.asset_manager.get_asset_info(symbol)
            if asset_info.get("exists") is False or asset_info.get("error"):
                return {
                    "success": False,
                    "error": asset_info.get("error", f"资产 {symbol} 不存在"),
                    "data": asset_info,
                    "symbol": symbol
                }

            # 包装成统一响应格式
            return {
                "success": True,
                "data": asset_info,
                "message": f"资产 {symbol} 信息获取成功"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取资产信息失败: {str(e)}",
                "symbol": symbol
            }
    
    def list_assets(self, filter_type: Optional[str] = None,
                   page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """
        列出资产（从数据库）
        
        新功能：从数据库获取，支持分页
        """
        all_assets = self.asset_manager.list_assets(filter_type)
        
        # 分页处理
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_assets = all_assets[start_idx:end_idx]
        
        return {
            "success": True,
            "data": {
                "assets": paginated_assets,
                "total": len(all_assets),
                "page": page,
                "page_size": page_size,
                "total_pages": (len(all_assets) + page_size - 1) // page_size
            }
        }
    
    def search_assets(self, query: str, limit: int = 50) -> Dict[str, Any]:
        """搜索资产（从数据库）"""
        results = self.asset_manager.search_assets(query, limit)
        return {
            "success": True,
            "data": {
                "assets": results,
                "query": query,
                "count": len(results)
            }
        }
    
    def get_asset_metrics_dashboard(self, symbol: str) -> Dict[str, Any]:
        """
        获取资产指标仪表板（新增）
        
        包含：
        - 基本信息
        - 价格信息
        - 波动率指标
        - 技术指标
        - 投资建议
        """
        try:
            dashboard = self.asset_manager.get_asset_metrics_dashboard(symbol)
            return {
                "success": True,
                "data": dashboard,
                "message": f"资产 {symbol} 指标仪表板获取成功"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取资产指标仪表板失败: {str(e)}",
                "symbol": symbol
            }
    
    def get_price_history_with_analysis(self, symbol: str, days: int = 30) -> Dict[str, Any]:
        """
        获取价格历史并进行技术分析（新增）
        
        包含：
        - 原始价格数据
        - 技术指标
        - 波动率计算
        - 性能指标
        """
        try:
            result = self.asset_manager.get_price_history_with_analysis(symbol, days)
            if result.get("success"):
                return {
                    "success": True,
                    "data": result,
                    "message": f"价格历史分析获取成功 ({days}天)"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "未知错误"),
                    "symbol": symbol
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取价格历史分析失败: {str(e)}",
                "symbol": symbol
            }
    
    # ==================== 关注机制API（新增）====================
    
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
            result = self.asset_manager.add_to_watchlist(symbol, user_id, notes)
            if result.get("success"):
                return {
                    "success": True,
                    "data": result,
                    "message": f"成功关注资产: {symbol}"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "关注失败"),
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
        try:
            result = self.asset_manager.remove_from_watchlist(symbol, user_id)
            if result.get("success"):
                return {
                    "success": True,
                    "data": result,
                    "message": f"成功取消关注资产: {symbol}"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "取消关注失败"),
                    "symbol": symbol
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"取消关注失败: {str(e)}",
                "symbol": symbol
            }
    
    def get_watchlist(self, user_id: str = 'default') -> Dict[str, Any]:
        """获取用户的关注列表（包含指标）"""
        try:
            watchlist = self.asset_manager.get_watchlist_with_metrics(user_id)
            return {
                "success": True,
                "data": {
                    "watchlist": watchlist,
                    "count": len(watchlist),
                    "user_id": user_id
                },
                "message": "关注列表获取成功"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取关注列表失败: {str(e)}",
                "user_id": user_id
            }
    
    def is_in_watchlist(self, symbol: str, user_id: str = 'default') -> Dict[str, Any]:
        """检查资产是否在用户关注列表中"""
        try:
            in_list = self.asset_manager.is_in_watchlist(symbol, user_id)
            return {
                "success": True,
                "data": {
                    "in_watchlist": in_list,
                    "symbol": symbol,
                    "user_id": user_id
                },
                "message": f"资产 {symbol} {'在' if in_list else '不在'}关注列表中"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"检查关注状态失败: {str(e)}",
                "symbol": symbol,
                "user_id": user_id
            }
    
    # ==================== 组合相关API（保持兼容）====================
    
    def add_position(self, symbol: str, shares: float) -> Dict[str, Any]:
        """添加或更新持仓"""
        return self.portfolio_api.add_position(symbol, shares)
    
    def remove_position(self, symbol: str) -> Dict[str, Any]:
        """移除持仓"""
        return self.portfolio_api.remove_position(symbol)
    
    def update_cash(self, currency: str, amount: float) -> Dict[str, Any]:
        """更新现金余额"""
        return self.portfolio_api.update_cash(currency, amount)
    
    def get_portfolio_value(self, base_currency: Optional[str] = None) -> Dict[str, Any]:
        """获取组合价值"""
        return self.portfolio_api.get_portfolio_value(base_currency)
    
    def get_current_holdings(self) -> Dict[str, Any]:
        """获取当前持仓"""
        return self.portfolio_api.get_current_holdings()
    
    def get_cash_balances(self) -> Dict[str, Any]:
        """获取现金余额"""
        return self.portfolio_api.get_cash_balances()
    
    def get_portfolio_metrics(self) -> Dict[str, Any]:
        """获取组合指标"""
        return self.portfolio_api.get_portfolio_metrics()
    
    def get_risk_metrics(self, confidence_level: float = 0.95) -> Dict[str, Any]:
        """获取风险指标"""
        return self.portfolio_api.get_risk_metrics(confidence_level)
    
    def calculate_rebalance_orders(self) -> Dict[str, Any]:
        """计算再平衡订单"""
        return self.portfolio_api.calculate_rebalance_orders()
    
    def get_portfolio_ledger(self, start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
        """获取组合账本数据"""
        try:
            from FinData.store.portfolio_ledger import PortfolioLedgerStore
            from datetime import datetime

            store = PortfolioLedgerStore()

            start_dt = datetime.fromisoformat(start) if start else None
            end_dt = datetime.fromisoformat(end) if end else None

            df = store.load_entries(start_dt, end_dt)

            # Convert to list of dicts for API response
            ledger_entries = df.to_dict(orient='records')

            # Format datetime objects for JSON serialization if necessary
            for entry in ledger_entries:
                if isinstance(entry.get('as_of'), datetime):
                    entry['as_of'] = entry['as_of'].isoformat()

            return {
                "success": True,
                "data": ledger_entries,
                "message": f"成功获取账本数据: {len(ledger_entries)} 条记录"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取账本数据失败: {str(e)}"
            }

    # ==================== 仪表板相关API（保持兼容）====================
    
    def get_asset_overview(self) -> Dict[str, Any]:
        """获取资产概览"""
        return self.dashboard_api.get_asset_overview()
    
    def get_portfolio_snapshot(self) -> Dict[str, Any]:
        """获取组合快照"""
        return self.dashboard_api.get_portfolio_snapshot()
    
    def get_performance_chart_data(self, days: int = 365) -> Dict[str, Any]:
        """获取历史表现图表数据"""
        return self.dashboard_api.get_performance_chart_data(days)
    
    def get_risk_metrics_data(self) -> Dict[str, Any]:
        """获取风险指标数据"""
        return self.dashboard_api.get_risk_metrics_data()
    
    def get_rebalance_recommendations(self) -> Dict[str, Any]:
        """获取再平衡建议"""
        return self.dashboard_api.get_rebalance_recommendations()
    
    def get_asset_type_distribution(self) -> Dict[str, Any]:
        """获取资产类型分布"""
        return self.dashboard_api.get_asset_type_distribution()
    
    def analyze_asset(self, symbol: str, period: str = "1y") -> Dict[str, Any]:
        """分析单个资产"""
        return self.dashboard_api.analyze_asset(symbol, period)
    
    def compare_assets(self, symbols: List[str],
                      metrics: Optional[List[str]] = None) -> Dict[str, Any]:
        """比较多个资产"""
        return self.dashboard_api.compare_assets(symbols, metrics)
    
    def get_dashboard_status(self) -> Dict[str, Any]:
        """获取仪表板状态"""
        return self.dashboard_api.get_dashboard_status()
    
    # ==================== 综合API（增强版）====================
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        获取系统状态（包含数据库信息）
        
        新增：包含数据库统计信息
        """
        try:
            from src.core.database import get_database
            
            # 获取数据库统计
            db = get_database()
            db_stats = db.get_database_stats()

            holdings_count = len(self.portfolio_api.portfolio_core.get_current_holdings())
            cash_count = len(self.portfolio_api.portfolio_core.get_cash_balances())
            
            enhanced_status = {
                "asset_system": {
                    "status": "OK",
                    "total_assets": db_stats.get("total_assets", 0)
                },
                "portfolio_system": {
                    "status": "OK",
                    "positions_count": holdings_count,
                    "cash_currencies": cash_count
                },
                "dashboard_system": {"status": "OK"},
                "overall_status": "OK",
                "version": "2.0.0"
            }
            enhanced_status["database"] = {
                "status": "OK",
                "stats": db_stats,
                "file_path": db_stats.get("database_file", str(db.db_path))
            }
            
            return {
                "success": True,
                "message": "系统状态获取完成",
                "data": enhanced_status,
                "timestamp": self._get_timestamp()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"获取系统状态时发生错误: {str(e)}",
                "error_code": "SYSTEM_STATUS_ERROR",
                "timestamp": self._get_timestamp()
            }
    
    def _get_original_system_status(self) -> Dict[str, Any]:
        """获取原有系统状态"""
        try:
            from .api_service import APIService
            original_service = APIService()
            return original_service.get_system_status()
        except:
            # 如果失败，返回简化版本
            from datetime import datetime
            return {
                "success": True,
                "data": {
                    "asset_system": {"status": "OK", "total_assets": 0},
                    "portfolio_system": {"status": "OK", "total_value": 0},
                    "dashboard_system": {"status": "OK"},
                    "overall_status": "OK",
                    "version": "2.0.0"
                }
            }
    
    def clear_cache(self, cache_type: str = "all") -> Dict[str, Any]:
        """清理缓存"""
        try:
            from src.core.cache import get_cache
            
            cache = get_cache()
            cleared_namespaces = []
            
            if cache_type == "all" or cache_type == "asset":
                cache.clear_namespace("asset")
                cache.clear_namespace("asset_list")
                cache.clear_namespace("search")
                cache.clear_namespace("watchlist")
                cleared_namespaces.append("asset")
            
            if cache_type == "all" or cache_type == "portfolio":
                cache.clear_namespace("portfolio")
                cache.clear_namespace("prices")
                cache.clear_namespace("fx")
                cleared_namespaces.append("portfolio")
            
            if cache_type == "all" or cache_type == "dashboard":
                cache.clear_namespace("dashboard")
                cache.clear_namespace("analysis")
                cache.clear_namespace("charts")
                cleared_namespaces.append("dashboard")
            
            cache_stats = cache.get_stats()
            
            return {
                "success": True,
                "message": f"缓存清理完成: {', '.join(cleared_namespaces)}",
                "data": {
                    "cleared_namespaces": cleared_namespaces,
                    "cache_stats": cache_stats,
                    "cache_type": cache_type
                },
                "timestamp": self._get_timestamp()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"清理缓存时发生错误: {str(e)}",
                "error_code": "CACHE_CLEAR_ERROR",
                "timestamp": self._get_timestamp()
            }
    
    def export_system_data(self, format: str = "json") -> Dict[str, Any]:
        """导出系统数据（包含数据库数据）"""
        try:
            # 收集所有数据
            db_stats = self._get_database_stats()
            watchlist = self.get_watchlist()
            asset_overview = self.get_asset_overview()
            
            system_data = {
                "export_timestamp": self._get_timestamp(),
                "system_version": "2.0.0",
                "database_stats": db_stats,
                "watchlist_data": watchlist.get("data") if watchlist["success"] else None,
                "asset_overview": asset_overview.get("data") if asset_overview["success"] else None,
                "export_status": {
                    "database": "success" if db_stats["success"] else "failed",
                    "watchlist": "success" if watchlist["success"] else "failed",
                    "asset_overview": "success" if asset_overview["success"] else "failed"
                }
            }
            
            # 格式转换
            if format == "json":
                import json
                export_content = json.dumps(system_data, ensure_ascii=False, indent=2)
            elif format == "csv":
                # 简化的CSV导出
                import pandas as pd
                import io
                
                # 创建资产数据表
                asset_rows = []
                if asset_overview["success"]:
                    overview_data = asset_overview["data"]
                    if isinstance(overview_data, dict):
                        for type_name, count in overview_data.get("by_type", {}).items():
                            asset_rows.append({
                                "category": "asset",
                                "type": type_name,
                                "count": count
                            })
                
                # 创建关注列表数据表
                watchlist_rows = []
                if watchlist["success"]:
                    watchlist_data = watchlist["data"]
                    if isinstance(watchlist_data, dict) and "watchlist" in watchlist_data:
                        for item in watchlist_data["watchlist"]:
                            watchlist_rows.append({
                                "category": "watchlist",
                                "symbol": item.get("symbol", ""),
                                "name": item.get("name", ""),
                                "asset_type": item.get("asset_type", ""),
                                "added_at": item.get("added_at", "")
                            })
                
                # 合并数据
                df_assets = pd.DataFrame(asset_rows) if asset_rows else pd.DataFrame()
                df_watchlist = pd.DataFrame(watchlist_rows) if watchlist_rows else pd.DataFrame()
                
                output = io.StringIO()
                if not df_assets.empty:
                    df_assets.to_csv(output, index=False)
                    output.write("\n")
                if not df_watchlist.empty:
                    df_watchlist.to_csv(output, index=False)
                
                export_content = output.getvalue()
            else:
                return {
                    "success": False,
                    "error": f"不支持的导出格式: {format}",
                    "error_code": "UNSUPPORTED_FORMAT",
                    "timestamp": self._get_timestamp()
                }
            
            return {
                "success": True,
                "message": "系统数据导出完成",
                "data": {
                    "format": format,
                    "content": export_content,
                    "size_bytes": len(export_content.encode('utf-8'))
                },
                "timestamp": self._get_timestamp()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"导出系统数据时发生错误: {str(e)}",
                "error_code": "EXPORT_ERROR",
                "timestamp": self._get_timestamp()
            }
    
    def _get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计"""
        try:
            from src.core.database import get_database
            db = get_database()
            stats = db.get_database_stats()
            return {
                "success": True,
                "data": stats
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==================== 辅助方法 ====================
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def get_supported_asset_types(self) -> Dict[str, Any]:
        """获取支持的资产类型列表"""
        try:
            types = self.asset_manager.get_supported_types()
            return {
                "success": True,
                "data": {
                    "supported_types": types,
                    "count": len(types)
                },
                "message": "支持的资产类型列表获取成功"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取支持的资产类型失败: {str(e)}"
            }
    
    def update_asset_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """更新资产价格数据"""
        try:
            result = self.asset_manager.update_asset_prices(symbols)
            return {
                "success": True,
                "data": result,
                "message": f"价格更新完成: {result.get('updated', 0)}个资产已更新"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"更新资产价格失败: {str(e)}"
            }


# 全局增强API服务实例
_enhanced_api_service_instance = None

def get_enhanced_api_service() -> EnhancedAPIService:
    """
    获取全局增强API服务实例（单例模式）
    
    Returns:
        EnhancedAPIService实例
    """
    global _enhanced_api_service_instance
    if _enhanced_api_service_instance is None:
        _enhanced_api_service_instance = EnhancedAPIService()
    return _enhanced_api_service_instance
