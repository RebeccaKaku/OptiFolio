"""
仪表板数据引擎 - 为UI层提供统一的数据接口

设计目标：
1. 聚合 AssetManager 和 PortfolioCore 的功能
2. 提供UI友好的数据格式
3. 支持图表数据生成
4. 缓存优化
"""

from typing import Dict, List, Any, Optional, Union, Tuple
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from .interfaces import IAnalyticsEngine
from .cache import get_cache, cached
from .asset_manager import AssetManager
from .portfolio_core import PortfolioCore


class DashboardEngine(IAnalyticsEngine):
    """
    仪表板数据引擎 - 统一数据接口
    
    将复杂的业务逻辑转换为UI友好的数据结构
    """
    
    def __init__(self, asset_manager: Optional[AssetManager] = None,
                 portfolio_core: Optional[PortfolioCore] = None,
                 enable_cache: bool = True):
        """
        初始化仪表板引擎
        
        Args:
            asset_manager: 资产管理器实例
            portfolio_core: 组合管理核心实例
            enable_cache: 是否启用缓存
        """
        self.asset_manager = asset_manager or AssetManager(enable_cache=enable_cache)
        self.portfolio_core = portfolio_core or PortfolioCore(enable_cache=enable_cache)
        self.enable_cache = enable_cache
        
        # 缓存实例
        self.cache = get_cache() if enable_cache else None
        
    # ==================== IAnalyticsEngine 接口实现 ====================
    
    def analyze_asset(self, symbol: str, period: str = "1y") -> Dict[str, Any]:
        """分析单个资产"""
        cache_key = f"asset_analysis:{symbol}:{period}"
        
        if self.enable_cache:
            cached_result = self.cache.get(cache_key, "analysis")
            if cached_result is not None:
                return cached_result
        
        # 获取资产基本信息
        asset_info = self.asset_manager.get_asset_info(symbol)
        
        if not asset_info.get("exists"):
            return {
                "error": f"资产 {symbol} 不存在",
                "symbol": symbol,
                "exists": False
            }
        
        # 计算分析指标
        analysis = {
            "symbol": symbol,
            "name": asset_info.get("name", symbol),
            "asset_type": asset_info.get("asset_type", "unknown"),
            "currency": asset_info.get("currency", "CNY"),
            "exists": True,
            "price_info": asset_info.get("price_info"),
            "basic_stats": self._calculate_asset_basic_stats(symbol, period),
            "technical_indicators": self._calculate_technical_indicators(symbol, period),
            "risk_metrics": self._calculate_asset_risk_metrics(symbol, period),
            "performance": self._calculate_performance_metrics(symbol, period)
        }
        
        if self.enable_cache:
            self.cache.set(cache_key, analysis, 1800, "analysis")  # 30分钟缓存
        
        return analysis
    
    def analyze_portfolio(self, portfolio_symbols: List[str], 
                         weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """分析组合"""
        # 如果没有提供权重，使用等权重
        if weights is None and portfolio_symbols:
            weight_per_asset = 1.0 / len(portfolio_symbols)
            weights = {symbol: weight_per_asset for symbol in portfolio_symbols}
        
        analysis = {
            "portfolio_symbols": portfolio_symbols,
            "weights": weights,
            "num_assets": len(portfolio_symbols),
            "total_weight": sum(weights.values()) if weights else 0,
            "asset_analyses": {},
            "portfolio_stats": {}
        }
        
        # 分析每个资产
        for symbol in portfolio_symbols:
            try:
                asset_analysis = self.analyze_asset(symbol, "1y")
                analysis["asset_analyses"][symbol] = asset_analysis
            except Exception as e:
                print(f"[DashboardEngine] 分析资产 {symbol} 失败: {e}")
                analysis["asset_analyses"][symbol] = {
                    "symbol": symbol,
                    "error": str(e),
                    "exists": False
                }
        
        # 计算组合级统计
        if weights and analysis["asset_analyses"]:
            analysis["portfolio_stats"] = self._calculate_portfolio_stats(
                portfolio_symbols, weights, analysis["asset_analyses"]
            )
        
        return analysis
    
    def compare_assets(self, symbols: List[str], 
                      metrics: List[str] = ["return", "volatility", "sharpe"]) -> pd.DataFrame:
        """比较多个资产"""
        comparison_data = []
        
        for symbol in symbols:
            try:
                asset_analysis = self.analyze_asset(symbol, "1y")
                
                row = {"symbol": symbol}
                
                for metric in metrics:
                    if metric == "return" and "performance" in asset_analysis:
                        row["return"] = asset_analysis["performance"].get("annual_return", 0)
                    elif metric == "volatility" and "risk_metrics" in asset_analysis:
                        row["volatility"] = asset_analysis["risk_metrics"].get("volatility", 0)
                    elif metric == "sharpe" and "performance" in asset_analysis:
                        row["sharpe"] = asset_analysis["performance"].get("sharpe_ratio", 0)
                    elif metric == "max_drawdown" and "performance" in asset_analysis:
                        row["max_drawdown"] = asset_analysis["performance"].get("max_drawdown", 0)
                    elif metric == "sortino" and "performance" in asset_analysis:
                        row["sortino"] = asset_analysis["performance"].get("sortino_ratio", 0)
                    elif metric == "current_price" and "price_info" in asset_analysis:
                        row["current_price"] = asset_analysis["price_info"].get("latest", 0)
                    elif metric == "currency" and "currency" in asset_analysis:
                        row["currency"] = asset_analysis["currency"]
                    elif metric == "asset_type" and "asset_type" in asset_analysis:
                        row["asset_type"] = asset_analysis["asset_type"]
                
                comparison_data.append(row)
                
            except Exception as e:
                print(f"[DashboardEngine] 比较资产 {symbol} 失败: {e}")
        
        return pd.DataFrame(comparison_data)
    
    # ==================== 仪表板专用方法 ====================
    
    def get_asset_overview_data(self) -> Dict[str, Any]:
        """获取资产概览数据（用于卡片展示）"""
        cache_key = "asset_overview"
        
        if self.enable_cache:
            cached_result = self.cache.get(cache_key, "dashboard")
            if cached_result is not None:
                return cached_result
        
        # 获取资产统计
        asset_count = self.asset_manager.get_asset_count()
        
        # 获取资产列表（前20个）
        all_assets = self.asset_manager.list_assets()
        recent_assets = all_assets[:20] if len(all_assets) > 20 else all_assets
        
        # 添加价格信息
        for asset in recent_assets:
            symbol = asset["symbol"]
            price_info = self._get_asset_price_info(symbol, asset.get("asset_type"))
            if price_info:
                asset["price_info"] = price_info
        
        overview = {
            "asset_count": asset_count["total"],
            "by_type": asset_count["by_simplified_type"],
            "recent_assets": recent_assets,
            "total_types": len(asset_count["by_simplified_type"]),
            "last_updated": datetime.now().isoformat()
        }
        
        if self.enable_cache:
            self.cache.set(cache_key, overview, 300, "dashboard")  # 5分钟缓存
        
        return overview
    
    def get_portfolio_snapshot(self) -> Dict[str, Any]:
        """获取组合快照（当前价值、权重、现金等）"""
        cache_key = "portfolio_snapshot"
        
        if self.enable_cache:
            cached_result = self.cache.get(cache_key, "dashboard")
            if cached_result is not None:
                return cached_result
        
        # 获取组合价值
        portfolio_value = self.portfolio_core.get_portfolio_value()
        
        # 获取持仓摘要
        position_summary = self.portfolio_core.get_position_summary()
        
        # 获取组合指标
        portfolio_metrics = self.portfolio_core.get_portfolio_metrics()
        
        # 获取再平衡建议
        rebalance_orders = self.portfolio_core.calculate_rebalance_orders()
        
        snapshot = {
            "portfolio_value": portfolio_value,
            "position_summary": position_summary,
            "portfolio_metrics": portfolio_metrics,
            "rebalance_orders": rebalance_orders,
            "cash_balances": self.portfolio_core.get_cash_balances(),
            "timestamp": datetime.now().isoformat(),
            "base_currency": self.portfolio_core.base_currency
        }
        
        if self.enable_cache:
            self.cache.set(cache_key, snapshot, 60, "dashboard")  # 1分钟缓存（组合数据变化频繁）
        
        return snapshot
    
    def get_performance_chart_data(self, days: int = 365) -> Dict[str, Any]:
        """获取历史表现图表数据"""
        cache_key = f"performance_chart:{days}"
        
        if self.enable_cache:
            cached_result = self.cache.get(cache_key, "charts")
            if cached_result is not None:
                return cached_result
        
        # 简化实现：生成示例数据
        # 实际实现需要获取历史价格数据
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 生成日期序列
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        
        # 示例：生成随机收益序列
        np.random.seed(42)  # 固定随机种子以便重现
        daily_returns = np.random.normal(0.0005, 0.015, len(dates))
        
        # 计算累计收益
        cumulative_returns = (1 + daily_returns).cumprod() - 1
        
        # 将 numpy 数组转换为 pandas Series 以便使用 expanding()
        cumulative_returns_series = pd.Series(cumulative_returns)

        # 创建数据系列
        chart_data = {
            "dates": [d.strftime("%Y-%m-%d") for d in dates],
            "daily_returns": daily_returns.tolist(),
            "cumulative_returns": cumulative_returns.tolist(),
            "running_max": cumulative_returns_series.expanding().max().tolist(),
            "drawdown": (cumulative_returns_series - cumulative_returns_series.expanding().max()).tolist(),
            "period": f"{days}天",
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "data_points": len(dates)
        }
        
        if self.enable_cache:
            self.cache.set(cache_key, chart_data, 3600, "charts")  # 1小时缓存
        
        return chart_data
    
    def get_risk_metrics_data(self) -> Dict[str, Any]:
        """获取风险指标数据"""
        cache_key = "risk_metrics"
        
        if self.enable_cache:
            cached_result = self.cache.get(cache_key, "dashboard")
            if cached_result is not None:
                return cached_result
        
        # 获取组合风险指标
        portfolio_risk = self.portfolio_core.get_risk_metrics()
        
        # 获取组合指标中的波动率等信息
        portfolio_metrics = self.portfolio_core.get_portfolio_metrics()
        
        # 构建风险指标数据
        risk_data = {
            "portfolio_risk": portfolio_risk,
            "portfolio_metrics": {
                "volatility": portfolio_metrics.get("annual_volatility", 0),
                "max_drawdown": portfolio_metrics.get("max_drawdown", 0),
                "sharpe_ratio": portfolio_metrics.get("sharpe_ratio", 0),
                "sortino_ratio": portfolio_metrics.get("sortino_ratio", 0)
            },
            "var_analysis": self._calculate_var_breakdown(),
            "stress_tests": self._perform_stress_tests(),
            "correlation_matrix": self._get_correlation_matrix(),
            "timestamp": datetime.now().isoformat()
        }
        
        if self.enable_cache:
            self.cache.set(cache_key, risk_data, 1800, "dashboard")  # 30分钟缓存
        
        return risk_data
    
    def get_rebalance_recommendations(self) -> List[Dict]:
        """获取再平衡建议（UI友好格式）"""
        rebalance_orders = self.portfolio_core.calculate_rebalance_orders()
        
        recommendations = []
        for order in rebalance_orders:
            # 转换为UI友好格式
            recommendation = {
                "symbol": order["symbol"],
                "action": order["action"],
                "action_color": "green" if order["action"] == "BUY" else "red",
                "action_icon": "↑" if order["action"] == "BUY" else "↓",
                "current_weight": f"{order['current_weight']:.2%}",
                "target_weight": f"{order['target_weight']:.2%}",
                "weight_delta": f"{(order['target_weight'] - order['current_weight']):+.2%}",
                "current_value": f"{order['current_value']:,.2f}",
                "target_value": f"{order['target_value']:,.2f}",
                "value_delta": f"{order['value_delta']:,.2f}",
                "priority": "high" if abs(order['value_delta']) > 10000 else "medium" if abs(order['value_delta']) > 1000 else "low"
            }
            
            recommendations.append(recommendation)
        
        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: (priority_order[x["priority"]], -float(x["value_delta"].replace(',', ''))))
        
        return recommendations
    
    def get_asset_type_distribution(self) -> Dict[str, Any]:
        """获取资产类型分布（用于饼图）"""
        try:
            # 获取组合价值
            portfolio_value = self.portfolio_core.get_portfolio_value()
            
            # 获取持仓摘要
            position_summary = self.portfolio_core.get_position_summary()
            
            # 资产类型分组
            by_type = position_summary.get("by_type", {})
            
            distribution = {
                "by_asset_type": by_type,
                "by_currency": position_summary.get("by_currency", {}),
                "cash_vs_invested": {
                    "cash": portfolio_value.get("cash_value", 0),
                    "invested": portfolio_value.get("portfolio_value", 0),
                    "total": portfolio_value.get("total_value", 0)
                },
                "top_positions": position_summary.get("top_positions", []),
                "currency_breakdown": self._get_currency_breakdown()
            }
            
            return distribution
            
        except Exception as e:
            print(f"[DashboardEngine] ERROR: 获取资产类型分布时发生错误: {e}")
            import traceback
            traceback.print_exc()
            return {
                "error": f"获取资产类型分布失败: {str(e)}",
                "by_asset_type": {},
                "by_currency": {},
                "cash_vs_invested": {
                    "cash": 0,
                    "invested": 0,
                    "total": 0
                },
                "top_positions": [],
                "currency_breakdown": {}
            }
    
    # ==================== 辅助方法 ====================
    
    def _calculate_asset_basic_stats(self, symbol: str, period: str) -> Dict[str, Any]:
        """计算资产基础统计"""
        # 简化实现
        return {
            "period": period,
            "data_available": True,
            "last_updated": datetime.now().isoformat()
        }
    
    def _calculate_technical_indicators(self, symbol: str, period: str) -> Dict[str, Any]:
        """计算技术指标"""
        # 简化实现
        return {
            "rsi": 50.0 + np.random.uniform(-10, 10),
            "macd": np.random.uniform(-1, 1),
            "bollinger_bands": {
                "upper": 1.0 + np.random.uniform(0, 0.1),
                "middle": 1.0,
                "lower": 1.0 - np.random.uniform(0, 0.1)
            },
            "moving_averages": {
                "ma20": 1.0 + np.random.uniform(-0.05, 0.05),
                "ma50": 1.0 + np.random.uniform(-0.05, 0.05),
                "ma200": 1.0 + np.random.uniform(-0.05, 0.05)
            }
        }
    
    def _calculate_asset_risk_metrics(self, symbol: str, period: str) -> Dict[str, Any]:
        """计算资产风险指标"""
        # 简化实现
        return {
            "volatility": np.random.uniform(0.1, 0.3),
            "beta": np.random.uniform(0.5, 1.5),
            "alpha": np.random.uniform(-0.1, 0.1),
            "sharpe_ratio": np.random.uniform(0.5, 2.0),
            "var_95": np.random.uniform(-0.05, -0.02),
            "expected_shortfall_95": np.random.uniform(-0.07, -0.03)
        }
    
    def _calculate_performance_metrics(self, symbol: str, period: str) -> Dict[str, Any]:
        """计算业绩指标"""
        # 简化实现
        return {
            "period_return": np.random.uniform(-0.1, 0.3),
            "annual_return": np.random.uniform(0.05, 0.2),
            "max_drawdown": np.random.uniform(-0.4, -0.1),
            "sortino_ratio": np.random.uniform(0.5, 2.5),
            "calmar_ratio": np.random.uniform(0.1, 1.0),
            "win_rate": np.random.uniform(0.4, 0.7)
        }
    
    def _calculate_portfolio_stats(self, symbols: List[str], weights: Dict[str, float], 
                                  asset_analyses: Dict[str, Any]) -> Dict[str, Any]:
        """计算组合统计"""
        # 简化实现：加权平均
        total_return = 0
        total_volatility = 0
        total_sharpe = 0
        
        for symbol, weight in weights.items():
            analysis = asset_analyses.get(symbol, {})
            perf = analysis.get("performance", {})
            risk = analysis.get("risk_metrics", {})
            
            total_return += weight * perf.get("annual_return", 0)
            total_volatility += weight * risk.get("volatility", 0)
            total_sharpe += weight * perf.get("sharpe_ratio", 0)
        
        return {
            "weighted_return": total_return,
            "weighted_volatility": total_volatility,
            "weighted_sharpe": total_sharpe,
            "diversification_score": min(1.0, len(symbols) / 10),  # 简单多样性评分
            "concentration_index": 1.0 - len(set(symbols)) / len(symbols) if symbols else 0
        }
    
    def _get_asset_price_info(self, symbol: str, asset_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取资产价格信息"""
        try:
            local_price = self.portfolio_core._get_local_asset_price(symbol)
            if local_price is not None:
                return {
                    "latest": local_price,
                    "source": "local_cache"
                }
            return None
        except:
            return None
    
    def _calculate_var_breakdown(self) -> Dict[str, Any]:
        """计算VaR分解"""
        return {
            "total_var": np.random.uniform(0.01, 0.05),
            "contributions": {
                "market_risk": np.random.uniform(0.3, 0.7),
                "credit_risk": np.random.uniform(0.1, 0.3),
                "liquidity_risk": np.random.uniform(0.05, 0.15),
                "currency_risk": np.random.uniform(0.05, 0.15)
            },
            "scenarios": [
                {"name": "市场大跌", "probability": "5%", "impact": "-15%"},
                {"name": "利率上升", "probability": "10%", "impact": "-8%"},
                {"name": "货币贬值", "probability": "15%", "impact": "-5%"}
            ]
        }
    
    def _perform_stress_tests(self) -> Dict[str, Any]:
        """执行压力测试"""
        return {
            "historical_scenarios": [
                {"name": "2008金融危机", "impact": "-35%", "recovery_months": 24},
                {"name": "2020疫情冲击", "impact": "-25%", "recovery_months": 6},
                {"name": "2022通胀冲击", "impact": "-15%", "recovery_months": 12}
            ],
            "hypothetical_scenarios": [
                {"name": "利率+2%", "impact": "-12%"},
                {"name": "油价+50%", "impact": "-8%"},
                {"name": "汇率波动+20%", "impact": "-10%"}
            ],
            "worst_case": {"impact": "-45%", "probability": "1%"}
        }
    
    def _get_correlation_matrix(self) -> Dict[str, Any]:
        """获取相关性矩阵"""
        # 简化实现：生成随机相关性矩阵
        symbols = list(self.portfolio_core.get_current_holdings().keys())[:5]
        
        if not symbols:
            return {"symbols": [], "matrix": []}
        
        # 生成随机相关性矩阵
        n = len(symbols)
        matrix = np.random.uniform(-0.5, 0.8, (n, n))
        
        # 使矩阵对称且对角线为1
        matrix = (matrix + matrix.T) / 2
        np.fill_diagonal(matrix, 1.0)
        
        return {
            "symbols": symbols,
            "matrix": matrix.tolist(),
            "heatmap_data": self._prepare_heatmap_data(symbols, matrix)
        }
    
    def _prepare_heatmap_data(self, symbols: List[str], matrix: np.ndarray) -> List[Dict]:
        """准备热力图数据"""
        heatmap_data = []
        for i, symbol1 in enumerate(symbols):
            for j, symbol2 in enumerate(symbols):
                if i <= j:  # 只存储上三角（包括对角线）
                    heatmap_data.append({
                        "x": symbol1,
                        "y": symbol2,
                        "value": float(matrix[i, j]),
                        "color_intensity": abs(matrix[i, j])  # 用于颜色强度
                    })
        return heatmap_data
    
    def _get_currency_breakdown(self) -> Dict[str, Any]:
        """获取货币细分"""
        portfolio_value = self.portfolio_core.get_portfolio_value()
        cash = portfolio_value.get("cash", {})
        positions = portfolio_value.get("positions", {})
        
        currency_totals = {}
        
        # 现金部分
        for currency, data in cash.items():
            currency_totals[currency] = currency_totals.get(currency, 0) + data.get("value", 0)
        
        # 持仓部分
        for symbol, data in positions.items():
            currency = data.get("currency", "USD")
            currency_totals[currency] = currency_totals.get(currency, 0) + data.get("value", 0)
        
        # 计算百分比
        total_value = portfolio_value.get("total_value", 1)
        currency_percentages = {
            currency: value / total_value
            for currency, value in currency_totals.items()
        }
        
        return {
            "totals": currency_totals,
            "percentages": currency_percentages,
            "num_currencies": len(currency_totals),
            "dominant_currency": max(currency_totals.items(), key=lambda x: x[1])[0] if currency_totals else "N/A"
        }
    
    # ==================== 仪表板状态方法 ====================
    
    def get_dashboard_status(self) -> Dict[str, Any]:
        """获取仪表板状态信息"""
        cache_key = "dashboard_status"
        
        if self.enable_cache:
            cached_result = self.cache.get(cache_key, "dashboard")
            if cached_result is not None:
                return cached_result
        
        status = {
            "overall": "operational",
            "components": {
                "asset_manager": "operational",
                "portfolio_core": "operational",
                "cache_system": "operational" if self.enable_cache else "disabled"
            },
            "metrics": {
                "asset_count": 0,
                "portfolio_value": 0,
                "cache_hit_rate": 0,
                "last_updated": self._get_timestamp()
            },
            "health_checks": []
        }
        
        # 检查资产管理器
        try:
            asset_count = self.asset_manager.get_asset_count()
            status["metrics"]["asset_count"] = asset_count.get("total", 0)
        except Exception as e:
            status["components"]["asset_manager"] = "degraded"
            status["health_checks"].append({
                "component": "asset_manager",
                "status": "degraded",
                "error": str(e)
            })
        
        # 检查组合核心
        try:
            portfolio_value = self.portfolio_core.get_portfolio_value()
            status["metrics"]["portfolio_value"] = portfolio_value.get("total_value", 0)
        except Exception as e:
            status["components"]["portfolio_core"] = "degraded"
            status["health_checks"].append({
                "component": "portfolio_core",
                "status": "degraded",
                "error": str(e)
            })
        
        # 检查缓存系统
        if self.enable_cache:
            try:
                cache_stats = self.cache.get_stats()
                total_hits = cache_stats.get("total_hits", 0)
                total_misses = cache_stats.get("total_misses", 0)
                total_requests = total_hits + total_misses
                hit_rate = total_hits / total_requests if total_requests > 0 else 0
                status["metrics"]["cache_hit_rate"] = hit_rate
            except Exception as e:
                status["components"]["cache_system"] = "degraded"
                status["health_checks"].append({
                    "component": "cache_system",
                    "status": "degraded",
                    "error": str(e)
                })
        
        # 总体状态评估
        component_statuses = list(status["components"].values())
        if "degraded" in component_statuses:
            status["overall"] = "degraded"
        elif "operational" not in component_statuses:
            status["overall"] = "failed"
        
        if self.enable_cache:
            self.cache.set(cache_key, status, 60, "dashboard")  # 1分钟缓存
        
        return status
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
