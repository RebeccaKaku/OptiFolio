"""
Dashboard API - 仪表板相关功能实现
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from src.core.logger import get_logger
from src.core.dashboard_engine import DashboardEngine
from src.core.cache import get_cache, cached
import pandas as pd

try:
    from src.api.network_tester import NetworkTester, run_network_test
    NETWORK_TESTER_IMPORT_ERROR = None
except ImportError as e:
    NetworkTester = None
    run_network_test = None
    NETWORK_TESTER_IMPORT_ERROR = e

logger = get_logger(__name__)


class DashboardAPI:
    """仪表板API - 提供仪表板相关功能"""
    
    def __init__(self):
        """初始化仪表板API"""
        self.dashboard_engine = DashboardEngine()
        self.network_tester = NetworkTester() if NetworkTester else None
        self.cache = get_cache()

    def _run_network_test(self) -> Dict[str, Any]:
        """运行网络测试；依赖缺失时返回业务错误而不是导入失败。"""
        if run_network_test is None:
            return {
                "error": f"网络测试依赖不可用: {NETWORK_TESTER_IMPORT_ERROR}",
                "error_code": "NETWORK_TESTER_UNAVAILABLE"
            }
        return run_network_test()
    
    def get_asset_overview(self) -> Dict[str, Any]:
        """获取资产概览"""
        try:
            result = self.dashboard_engine.get_asset_overview_data()
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"获取资产概览失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_portfolio_snapshot(self) -> Dict[str, Any]:
        """获取组合快照"""
        try:
            result = self.dashboard_engine.get_portfolio_snapshot()
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"获取组合快照失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_performance_chart_data(self, days: int = 365) -> Dict[str, Any]:
        """获取历史表现图表数据"""
        try:
            result = self.dashboard_engine.get_performance_chart_data(days)
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"获取历史表现图表数据失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_risk_metrics_data(self) -> Dict[str, Any]:
        """获取风险指标数据"""
        try:
            result = self.dashboard_engine.get_risk_metrics_data()
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"获取风险指标数据失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_rebalance_recommendations(self) -> Dict[str, Any]:
        """获取再平衡建议"""
        try:
            result = self.dashboard_engine.get_rebalance_recommendations()
            # 包装为统一格式
            return {"success": True, "data": {"recommendations": result}}
        except Exception as e:
            logger.error(f"获取再平衡建议失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_asset_type_distribution(self) -> Dict[str, Any]:
        """获取资产类型分布"""
        try:
            result = self.dashboard_engine.get_asset_type_distribution()
            # 包装为统一格式
            if "error" in result:
                return {"success": False, "error": result["error"]}
            else:
                return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"获取资产类型分布失败: {e}")
            return {"success": False, "error": str(e)}
    
    def analyze_asset(self, symbol: str, period: str = "1y") -> Dict[str, Any]:
        """分析单个资产"""
        try:
            return self.dashboard_engine.analyze_asset(symbol, period)
        except Exception as e:
            logger.error(f"分析资产失败: {e}")
            return {"success": False, "error": str(e)}
    
    def compare_assets(self, symbols: List[str], 
                      metrics: Optional[List[str]] = None) -> Dict[str, Any]:
        """比较多个资产"""
        try:
            return self.dashboard_engine.compare_assets(symbols, metrics)
        except Exception as e:
            logger.error(f"比较资产失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_dashboard_status(self) -> Dict[str, Any]:
        """获取仪表板状态"""
        try:
            return self.dashboard_engine.get_dashboard_status()
        except Exception as e:
            logger.error(f"获取仪表板状态失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_portfolio_status(self) -> Dict[str, Any]:
        """获取组合状态"""
        try:
            return self.dashboard_engine.get_portfolio_status()
        except Exception as e:
            logger.error(f"获取组合状态失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_python_version(self) -> str:
        """获取Python版本"""
        import sys
        return sys.version
    
    def get_akshare_version(self) -> str:
        """获取akshare版本"""
        try:
            import akshare as ak
            return ak.__version__
        except:
            return "unknown"
    
    def get_pandas_version(self) -> str:
        """获取pandas版本"""
        import pandas as pd
        return pd.__version__
    
    def get_uptime(self) -> str:
        """获取系统运行时间"""
        import time
        import datetime
        return datetime.datetime.now().isoformat()
    
    # ==================== 网络测试相关API ====================
    
    def test_network_apis(self, async_mode: bool = True) -> Dict[str, Any]:
        """测试网络API接口连通性"""
        try:
            if async_mode:
                report = self._run_network_test()
            else:
                # 同步模式，使用缓存
                cache_key = 'network_test_report'
                report = self.cache.get(cache_key)
                
                if report is None:
                    report = self._run_network_test()
                    # 缓存10分钟
                    self.cache.set(cache_key, report, ttl=600)
            
            if 'error' in report:
                return {"success": False, "error": report['error']}
            
            return {"success": True, "data": report, "message": "网络测试完成"}
            
        except Exception as e:
            logger.error(f"网络测试失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_network_status(self) -> Dict[str, Any]:
        """获取网络状态概览"""
        try:
            # 尝试从缓存获取
            cache_key = 'network_status'
            status = self.cache.get(cache_key)
            
            if status is None:
                # 运行快速测试
                report = self._run_network_test()
                
                if 'error' in report:
                    status = {
                        'overall_status': 'error',
                        'message': report['error'],
                        'last_checked': datetime.now().isoformat()
                    }
                else:
                    summary = report['summary']
                    success_rate = summary['success_rate']
                    
                    if success_rate >= 80:
                        overall_status = 'good'
                    elif success_rate >= 60:
                        overall_status = 'warning'
                    else:
                        overall_status = 'critical'
                    
                    status = {
                        'overall_status': overall_status,
                        'success_rate': success_rate,
                        'total_apis': summary['total_tests'],
                        'working_apis': summary['success_count'],
                        'failed_apis': summary['failed_count'] + summary['error_count'],
                        'avg_response_time': summary['avg_response_time'],
                        'last_checked': datetime.now().isoformat()
                    }
                
                # 缓存5分钟
                self.cache.set(cache_key, status, ttl=300)
            
            return {"success": True, "data": status, "message": "网络状态获取完成"}
            
        except Exception as e:
            logger.error(f"获取网络状态失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_failed_apis(self) -> Dict[str, Any]:
        """获取失败的API列表"""
        try:
            # 运行测试获取失败列表
            report = self._run_network_test()
            
            if 'error' in report:
                return {"success": False, "error": report['error']}
            
            # 获取失败的API
            self.network_tester.test_results = report['details']
            failed_apis = self.network_tester.get_failed_apis()
            
            return {
                "success": True,
                "data": {
                    "failed_apis": failed_apis,
                    "count": len(failed_apis)
                },
                "message": "失败API列表获取完成"
            }
            
        except Exception as e:
            logger.error(f"获取失败API列表失败: {e}")
            return {"success": False, "error": str(e)}
    
    def export_network_test(self) -> Dict[str, Any]:
        """导出网络测试结果"""
        try:
            # 运行完整测试
            report = self._run_network_test()
            
            if 'error' in report:
                return {"success": False, "error": report['error']}
            
            # 转换为DataFrame
            self.network_tester.test_results = report['details']
            df = self.network_tester.export_to_dataframe()
            
            if df.empty:
                return {"success": False, "error": "无测试结果可用", "error_code": "NO_RESULTS"}
            
            # 导出为CSV格式
            csv_content = df.to_csv(index=False, encoding='utf-8-sig')
            
            return {
                "success": True,
                "data": {
                    "csv_data": csv_content,
                    "filename": f'network_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                    "summary": report['summary']
                },
                "message": "网络测试结果导出完成"
            }
            
        except Exception as e:
            logger.error(f"导出网络测试结果失败: {e}")
            return {"success": False, "error": str(e)}
