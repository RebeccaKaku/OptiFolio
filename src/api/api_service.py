"""
统一API服务 - 为UI层提供完整的API接口
"""

from typing import Dict, List, Any, Optional
from .asset_api import AssetAPI
from .portfolio_api import PortfolioAPI
from .dashboard_api import DashboardAPI


class APIService:
    """
    统一API服务 - 整合所有API功能
    
    设计目标：
    1. 提供一站式API访问
    2. 简化UI层调用
    3. 统一错误处理
    4. 支持模块化扩展
    """
    
    def __init__(self):
        """初始化API服务"""
        self.asset_api = AssetAPI()
        self.portfolio_api = PortfolioAPI()
        self.dashboard_api = DashboardAPI()
    
    # ==================== 资产相关API ====================
    
    def import_asset(self, symbol: str, asset_type: Optional[str] = None, 
                    refresh: bool = False) -> Dict[str, Any]:
        """
        导入资产
        """
        return self.asset_api.import_asset(symbol, asset_type, refresh)
    
    def batch_import_assets(self, symbols: List[str], 
                           asset_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        批量导入资产
        """
        return self.asset_api.batch_import_assets(symbols, asset_types)
    
    def get_asset_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取资产信息
        """
        return self.asset_api.get_asset_info(symbol)
    
    def list_assets(self, filter_type: Optional[str] = None, 
                   page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """
        列出资产（支持分页）
        """
        return self.asset_api.list_assets(filter_type, page, page_size)
    
    def search_assets(self, query: str, limit: int = 50) -> Dict[str, Any]:
        """
        搜索资产
        """
        return self.asset_api.search_assets(query, limit)
    
    def get_supported_asset_types(self) -> Dict[str, Any]:
        """
        获取支持的资产类型
        """
        return self.asset_api.get_supported_asset_types()
    
    def get_asset_statistics(self) -> Dict[str, Any]:
        """
        获取资产统计
        """
        return self.asset_api.get_asset_statistics()
    
    # ==================== 组合相关API ====================
    
    def add_position(self, symbol: str, shares: float) -> Dict[str, Any]:
        """
        添加或更新持仓
        """
        return self.portfolio_api.add_position(symbol, shares)
    
    def remove_position(self, symbol: str) -> Dict[str, Any]:
        """
        移除持仓
        """
        return self.portfolio_api.remove_position(symbol)
    
    def update_cash(self, currency: str, amount: float) -> Dict[str, Any]:
        """
        更新现金余额
        """
        return self.portfolio_api.update_cash(currency, amount)
    
    def get_portfolio_value(self, base_currency: Optional[str] = None) -> Dict[str, Any]:
        """
        获取组合价值
        """
        return self.portfolio_api.get_portfolio_value(base_currency)
    
    def get_current_holdings(self) -> Dict[str, Any]:
        """
        获取当前持仓
        """
        return self.portfolio_api.get_current_holdings()
    
    def get_cash_balances(self) -> Dict[str, Any]:
        """
        获取现金余额
        """
        return self.portfolio_api.get_cash_balances()
    
    def get_portfolio_metrics(self) -> Dict[str, Any]:
        """
        获取组合指标
        """
        return self.portfolio_api.get_portfolio_metrics()
    
    def get_risk_metrics(self, confidence_level: float = 0.95) -> Dict[str, Any]:
        """
        获取风险指标
        """
        return self.portfolio_api.get_risk_metrics(confidence_level)
    
    def calculate_rebalance_orders(self) -> Dict[str, Any]:
        """
        计算再平衡订单
        """
        return self.portfolio_api.calculate_rebalance_orders()
    
    # ==================== 仪表板相关API ====================
    
    def get_asset_overview(self) -> Dict[str, Any]:
        """
        获取资产概览
        """
        return self.dashboard_api.get_asset_overview()
    
    def get_portfolio_snapshot(self) -> Dict[str, Any]:
        """
        获取组合快照
        """
        return self.dashboard_api.get_portfolio_snapshot()
    
    def get_performance_chart_data(self, days: int = 365) -> Dict[str, Any]:
        """
        获取历史表现图表数据
        """
        return self.dashboard_api.get_performance_chart_data(days)
    
    def get_risk_metrics_data(self) -> Dict[str, Any]:
        """
        获取风险指标数据
        """
        return self.dashboard_api.get_risk_metrics_data()
    
    def get_rebalance_recommendations(self) -> Dict[str, Any]:
        """
        获取再平衡建议
        """
        return self.dashboard_api.get_rebalance_recommendations()
    
    def get_asset_type_distribution(self) -> Dict[str, Any]:
        """
        获取资产类型分布
        """
        return self.dashboard_api.get_asset_type_distribution()
    
    def analyze_asset(self, symbol: str, period: str = "1y") -> Dict[str, Any]:
        """
        分析单个资产
        """
        return self.dashboard_api.analyze_asset(symbol, period)
    
    def compare_assets(self, symbols: List[str], 
                      metrics: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        比较多个资产
        """
        return self.dashboard_api.compare_assets(symbols, metrics)
    
    def get_dashboard_status(self) -> Dict[str, Any]:
        """
        获取仪表板状态
        """
        return self.dashboard_api.get_dashboard_status()
    
    # ==================== 综合API ====================
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        获取系统状态（综合信息）
        
        Returns:
            系统状态信息
        """
        try:
            # 获取关键系统状态
            asset_stats = self.asset_api.get_asset_statistics()
            portfolio_status = self.portfolio_api.get_portfolio_status()
            dashboard_status = self.dashboard_api.get_dashboard_status()
            
            # 合并状态信息
            system_status = {
                "asset_system": {
                    "status": "OK" if asset_stats["success"] else "ERROR",
                    "total_assets": asset_stats["data"]["total"] if asset_stats["success"] else 0,
                    "timestamp": asset_stats.get("timestamp")
                },
                "portfolio_system": {
                    "status": "OK" if portfolio_status["success"] else "ERROR",
                    "total_value": portfolio_status["data"]["portfolio_value"]["total_value"] if portfolio_status["success"] else 0,
                    "positions_count": portfolio_status["data"]["position_summary"]["total_positions"] if portfolio_status["success"] else 0,
                    "timestamp": portfolio_status.get("timestamp")
                },
                "dashboard_system": {
                    "status": "OK" if dashboard_status["success"] else "ERROR",
                    "timestamp": dashboard_status.get("timestamp")
                },
                "overall_status": "OK" if all([
                    asset_stats["success"],
                    portfolio_status["success"],
                    dashboard_status["success"]
                ]) else "DEGRADED",
                "version": "1.0.0",
                "timestamp": self._get_timestamp()
            }
            
            return {
                "success": True,
                "message": "系统状态获取完成",
                "data": system_status,
                "timestamp": system_status["timestamp"]
            }
            
        except Exception as e:
            from datetime import datetime
            return {
                "success": False,
                "error": f"获取系统状态时发生错误: {str(e)}",
                "error_code": "SYSTEM_STATUS_ERROR",
                "timestamp": datetime.now().isoformat()
            }
    
    def clear_cache(self, cache_type: str = "all") -> Dict[str, Any]:
        """
        清理缓存
        
        Args:
            cache_type: 缓存类型 (all, asset, portfolio, dashboard)
        
        Returns:
            清理结果
        """
        try:
            from ..core.cache import get_cache
            
            cache = get_cache()
            cleared_namespaces = []
            
            if cache_type == "all" or cache_type == "asset":
                cache.clear_namespace("asset")
                cache.clear_namespace("asset_list")
                cache.clear_namespace("search")
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
                "timestamp": self._get_timestamp(),
                "details": {"cache_type": cache_type}
            }
    
    def export_system_data(self, format: str = "json") -> Dict[str, Any]:
        """
        导出系统数据
        
        Args:
            format: 导出格式 (json, csv)
        
        Returns:
            导出数据
        """
        try:
            # 收集所有数据
            asset_stats = self.asset_api.get_asset_statistics()
            portfolio_status = self.portfolio_api.get_portfolio_status()
            dashboard_status = self.dashboard_api.get_dashboard_status()
            
            system_data = {
                "export_timestamp": self._get_timestamp(),
                "system_version": "1.0.0",
                "asset_data": asset_stats["data"] if asset_stats["success"] else None,
                "portfolio_data": portfolio_status["data"] if portfolio_status["success"] else None,
                "dashboard_data": dashboard_status["data"] if dashboard_status["success"] else None,
                "export_status": {
                    "asset": "success" if asset_stats["success"] else "failed",
                    "portfolio": "success" if portfolio_status["success"] else "failed",
                    "dashboard": "success" if dashboard_status["success"] else "failed"
                }
            }
            
            # 格式转换
            if format == "json":
                import json
                export_content = json.dumps(system_data, ensure_ascii=False, indent=2)
            elif format == "csv":
                # 简化的CSV导出（主要数据）
                import pandas as pd
                import io
                
                # 创建资产数据表
                asset_rows = []
                if asset_stats["success"]:
                    asset_data = asset_stats["data"]
                    for type_name, stats in asset_data.get("by_simplified_type", {}).items():
                        if isinstance(stats, dict):
                            asset_rows.append({
                                "category": "asset",
                                "type": type_name,
                                "count": stats.get("count", 0),
                                "percentage": stats.get("percentage", 0)
                            })
                
                # 创建组合数据表
                portfolio_rows = []
                if portfolio_status["success"]:
                    portfolio_data = portfolio_status["data"]
                    if portfolio_data.get("portfolio_value"):
                        portfolio_rows.append({
                            "category": "portfolio",
                            "metric": "total_value",
                            "value": portfolio_data["portfolio_value"].get("total_value", 0)
                        })
                        portfolio_rows.append({
                            "category": "portfolio",
                            "metric": "cash_value",
                            "value": portfolio_data["portfolio_value"].get("cash_value", 0)
                        })
                
                # 合并数据
                df_assets = pd.DataFrame(asset_rows) if asset_rows else pd.DataFrame()
                df_portfolio = pd.DataFrame(portfolio_rows) if portfolio_rows else pd.DataFrame()
                
                output = io.StringIO()
                if not df_assets.empty:
                    df_assets.to_csv(output, index=False)
                    output.write("\n")
                if not df_portfolio.empty:
                    df_portfolio.to_csv(output, index=False)
                
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
                "timestamp": self._get_timestamp(),
                "details": {"format": format}
            }
    
    # ==================== 辅助方法 ====================
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()


# 全局API服务实例
_api_service_instance: Optional[APIService] = None

def get_api_service() -> APIService:
    """
    获取全局API服务实例（单例模式）
    
    Returns:
        APIService实例
    """
    global _api_service_instance
    if _api_service_instance is None:
        _api_service_instance = APIService()
    return _api_service_instance