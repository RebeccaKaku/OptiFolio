"""
组合管理核心 - 实现 IPortfolioManager 接口
集成现有 PortfolioManager 功能，添加分析和扩展性支持
"""

import os
import sys
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime, timedelta
import yaml
import pandas as pd
import numpy as np

from .interfaces import IPortfolioManager
from .cache import get_cache, CacheKeys, cached

# 导入现有模块
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from src.data_core.fetchers.factory import get_factory
    from src.data_core.fetchers.currency import CurrencyFetcher
    from src.math_engine import MathEngine
except ImportError as e:
    print(f"[PortfolioCore] 导入依赖失败: {e}")
    # 创建简单的替代类
    class MathEngine:
        @staticmethod
        def get_stats(returns):
            mu = returns.mean() * 252
            sigma = returns.cov() * 252
            return {'mu': mu, 'sigma': sigma}


class PortfolioCore(IPortfolioManager):
    """
    组合管理核心 - 统一管理组合的生命周期
    
    设计特点：
    1. 集成现有 PortfolioManager 功能
    2. 添加组合分析和风险计算
    3. 支持多货币估值
    4. 线程安全，支持缓存
    """
    
    def __init__(self, config_path: Optional[str] = None, 
                 base_currency: str = "CNY",
                 enable_cache: bool = True):
        """
        初始化组合管理核心
        
        Args:
            config_path: 组合配置文件路径，默认为 config/portfolio.yaml
            base_currency: 基准货币
            enable_cache: 是否启用缓存
        """
        if config_path is None:
            config_path = os.path.join(project_root, "config", "portfolio.yaml")
        
        self.config_path = config_path
        self.base_currency = base_currency
        self.enable_cache = enable_cache
        
        # 缓存实例
        self.cache = get_cache() if enable_cache else None
        
        # 加载组合数据
        self.holdings: Dict[str, float] = {}
        self.cash: Dict[str, float] = {}
        
        # 资产元数据（从 settings.yaml 加载）
        self.asset_meta: Dict[str, str] = {}  # symbol -> currency
        self.asset_type_meta: Dict[str, str] = {}  # symbol -> asset_type
        
        # 数据获取器
        try:
            self.factory = get_factory()
            self.fx_fetcher = CurrencyFetcher()
        except Exception as e:
            print(f"[PortfolioCore] 初始化数据获取器失败: {e}")
            self.factory = None
            self.fx_fetcher = None
        
        # 加载配置
        self._load_portfolio()
        self._load_asset_metadata()
        
        # 数学引擎
        self.math_engine = MathEngine()
    
    def _load_portfolio(self):
        """加载组合配置"""
        if not os.path.exists(self.config_path):
            print(f"[PortfolioCore] 警告: 找不到组合配置文件 {self.config_path}")
            self.holdings = {}
            self.cash = {}
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                
            self.cash = data.get('cash', {})
            self.holdings = data.get('positions', {})
            
            # 确保所有持仓是浮点数
            self.holdings = {str(k): float(v) for k, v in self.holdings.items()}
            
            print(f"[PortfolioCore] 加载组合: {len(self.holdings)} 个持仓, {len(self.cash)} 种货币现金")
            
        except Exception as e:
            print(f"[PortfolioCore] 加载组合配置失败: {e}")
            self.holdings = {}
            self.cash = {}
    
    def _load_asset_metadata(self):
        """加载资产元数据（货币、类型等）"""
        settings_path = os.path.join(project_root, "config", "settings.yaml")
        candidates_path = os.path.join(project_root, "config", "candidates.yaml")
        
        # 优先从candidates.yaml加载资产类型映射
        if os.path.exists(candidates_path):
            try:
                with open(candidates_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                
                self.asset_meta.clear()
                self.asset_type_meta.clear()
                
                for asset in data.get('candidates', {}).get('assets', []):
                    symbol = asset.get('symbol')
                    if symbol:
                        asset_type = asset.get('type', 'us_equity')
                        currency = asset.get('currency')
                        
                        # 如果没有指定货币，根据资产类型设置默认货币
                        if not currency:
                            currency = self._get_default_currency(asset_type)
                        
                        self.asset_meta[symbol] = currency
                        self.asset_type_meta[symbol] = asset_type
                
                print(f"[PortfolioCore] 从candidates.yaml加载资产元数据: {len(self.asset_type_meta)} 个资产")
                
            except Exception as e:
                print(f"[PortfolioCore] 从candidates.yaml加载资产元数据失败: {e}")
        
        # 如果candidates.yaml不存在或加载失败，尝试settings.yaml
        elif os.path.exists(settings_path):
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                
                self.asset_meta.clear()
                self.asset_type_meta.clear()
                
                for asset in data.get('universe', {}).get('assets', []):
                    symbol = asset.get('symbol')
                    if symbol:
                        asset_type = asset.get('type', 'us_equity')
                        currency = asset.get('currency')
                        
                        # 如果没有指定货币，根据资产类型设置默认货币
                        if not currency:
                            currency = self._get_default_currency(asset_type)
                        
                        self.asset_meta[symbol] = currency
                        self.asset_type_meta[symbol] = asset_type
                
                print(f"[PortfolioCore] 从settings.yaml加载资产元数据: {len(self.asset_type_meta)} 个资产")
                
            except Exception as e:
                print(f"[PortfolioCore] 从settings.yaml加载资产元数据失败: {e}")
        
        else:
            print(f"[PortfolioCore] 警告: 找不到设置文件 {settings_path} 或 {candidates_path}")
        
        # 为所有持仓补充缺失的元数据
        self._supplement_missing_metadata()
    
    def _get_fx_rate(self, from_currency: str, to_currency: str) -> float:
        """获取汇率（带缓存）"""
        if from_currency == to_currency:
            return 1.0
        
        cache_key = CacheKeys.fx_rate(from_currency, to_currency)
        
        if self.enable_cache:
            cached_rate = self.cache.get(cache_key, "fx")
            if cached_rate is not None:
                return cached_rate
        
        # 使用 CurrencyFetcher 获取汇率
        if self.fx_fetcher:
            try:
                rate = self.fx_fetcher.get_realtime_rate(from_currency, to_currency)
                
                if self.enable_cache:
                    # 汇率缓存时间较短（5分钟）
                    self.cache.set(cache_key, rate, 300, "fx")
                
                return rate
            except Exception as e:
                print(f"[PortfolioCore] 获取汇率失败 {from_currency}/{to_currency}: {e}")
        
        # 回退：使用简单映射
        simple_rates = {
            ("USD", "CNY"): 7.2,
            ("CNY", "USD"): 1/7.2,
            ("EUR", "USD"): 1.1,
            ("USD", "EUR"): 1/1.1,
            ("USD", "JPY"): 150,
            ("JPY", "USD"): 1/150,
        }
        
        rate = simple_rates.get((from_currency, to_currency), 1.0)
        
        if self.enable_cache:
            self.cache.set(cache_key, rate, 300, "fx")
        
        return rate
    
    def _get_asset_price(self, symbol: str, asset_type: str) -> Optional[float]:
        """获取资产最新价格（带缓存）"""
        cache_key = f"asset_price:{symbol}"
        
        if self.enable_cache:
            cached_price = self.cache.get(cache_key, "prices")
            if cached_price is not None:
                return cached_price
        
        if not self.factory:
            print(f"[PortfolioCore] 无法获取价格：数据获取器工厂未初始化")
            return None
        
        # 获取对应的 fetcher
        fetcher = self.factory.get_fetcher(asset_type)
        if not fetcher:
            print(f"[PortfolioCore] 无法获取 {symbol} 的fetcher (类型: {asset_type})")
            return None
        
        try:
            # 设置日期范围（最近30天）
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            
            # 获取价格数据
            df = fetcher.fetch(symbol, start_date=start_date, end_date=end_date)
            
            if df is not None and not df.empty:
                # 提取最新价格
                if 'Close' in df.columns:
                    price = float(df['Close'].iloc[-1])
                elif 'close' in df.columns:
                    price = float(df['close'].iloc[-1])
                elif len(df.columns) > 0:
                    price = float(df.iloc[:, -1].iloc[-1])
                else:
                    price = None
                
                if price is not None and self.enable_cache:
                    # 价格缓存时间较短（10分钟）
                    self.cache.set(cache_key, price, 600, "prices")
                
                return price
            else:
                print(f"[PortfolioCore] {symbol} 无有效价格数据")
                return None
                
        except Exception as e:
            print(f"[PortfolioCore] 获取 {symbol} 价格失败: {e}")
            return None
    
    # 添加调试方法
    def debug_asset_mapping(self, symbol: str) -> Dict[str, Any]:
        """调试资产映射问题"""
        asset_currency = self.asset_meta.get(symbol, "未知")
        asset_type = self.asset_type_meta.get(symbol, "未知")
        
        result = {
            "symbol": symbol,
            "asset_currency": asset_currency,
            "asset_type": asset_type,
            "factory_available": self.factory is not None,
            "fetcher_available": False
        }
        
        if self.factory and asset_type != "未知":
            fetcher = self.factory.get_fetcher(asset_type)
            result["fetcher_available"] = fetcher is not None
            if fetcher:
                result["fetcher_class"] = fetcher.__class__.__name__
        
        return result
    
    def fix_asset_metadata(self, symbol: str, asset_type: str, currency: str = "USD") -> bool:
        """修复资产元数据"""
        try:
            self.asset_meta[symbol] = currency
            self.asset_type_meta[symbol] = asset_type
            print(f"[PortfolioCore] 修复资产元数据: {symbol} -> {asset_type} ({currency})")
            
            # 清理缓存
            self._invalidate_portfolio_caches()
            return True
        except Exception as e:
            print(f"[PortfolioCore] 修复资产元数据失败: {e}")
            return False

    # ==================== IPortfolioData 接口实现 ====================
    
    def get_current_holdings(self) -> Dict[str, float]:
        """获取当前持仓（symbol -> shares）"""
        return self.holdings.copy()
    
    def get_target_weights(self) -> Dict[str, float]:
        """从策略引擎获取目标权重"""
        # 这里可以集成现有的策略引擎
        # 暂时返回等权重作为示例
        if not self.holdings:
            return {}
        
        target_weights = {}
        for symbol in self.holdings.keys():
            # 示例：等权重
            target_weights[symbol] = 1.0 / len(self.holdings)
        
        return target_weights
    
    @cached(ttl=300, namespace="portfolio", key_prefix="portfolio_value")
    def get_portfolio_value(self, base_currency: str = "CNY") -> Dict[str, float]:
        """获取组合价值（多货币支持）"""
        print(f"[PortfolioCore] DEBUG: 开始计算组合价值，基准货币: {base_currency}")
        print(f"[PortfolioCore] DEBUG: 持仓数量: {len(self.holdings)}，现金货币数量: {len(self.cash)}")
        
        portfolio_value = 0.0
        position_values = {}
        
        for symbol, shares in self.holdings.items():
            # 获取资产类型和货币
            asset_currency = self.asset_meta.get(symbol, "USD")
            asset_type = self.asset_type_meta.get(symbol, "us_equity")
            
            # 详细调试输出
            print(f"[PortfolioCore] DEBUG: 处理资产: {symbol} (股数: {shares}) -> 类型: {asset_type}, 货币: {asset_currency}")
            
            # 检查元数据
            if symbol not in self.asset_meta:
                print(f"[PortfolioCore] WARNING: 资产 {symbol} 没有货币元数据")
            if symbol not in self.asset_type_meta:
                print(f"[PortfolioCore] WARNING: 资产 {symbol} 没有资产类型元数据")
            
            # 获取价格
            print(f"[PortfolioCore] DEBUG: 获取 {symbol} 价格 (类型: {asset_type})...")
            price = self._get_asset_price(symbol, asset_type)
            
            if price is None:
                print(f"[PortfolioCore] ERROR: 无法获取 {symbol} 的价格")
                print(f"[PortfolioCore] DEBUG: 资产元数据: 货币={asset_currency}, 类型={asset_type}")
                
                # 尝试调试资产映射
                if hasattr(self, 'debug_asset_mapping'):
                    debug_info = self.debug_asset_mapping(symbol)
                    print(f"[PortfolioCore] DEBUG: 资产映射调试信息: {debug_info}")
                
                # 尝试使用默认价格作为回退
                default_price = 1.0
                print(f"[PortfolioCore] WARNING: 使用默认价格 {default_price} 作为回退")
                price = default_price
            
            print(f"[PortfolioCore] DEBUG: {symbol} 价格: {price}")
            
            # 汇率换算
            fx_rate = self._get_fx_rate(asset_currency, base_currency)
            print(f"[PortfolioCore] DEBUG: {asset_currency}/{base_currency} 汇率: {fx_rate}")
            
            position_value = shares * price * fx_rate
            print(f"[PortfolioCore] DEBUG: {symbol} 价值: {shares} * {price} * {fx_rate} = {position_value}")
            
            position_values[symbol] = {
                "shares": shares,
                "price": price,
                "currency": asset_currency,
                "fx_rate": fx_rate,
                "value": position_value
            }
            
            portfolio_value += position_value
            print(f"[PortfolioCore] DEBUG: 累计组合价值: {portfolio_value}")
        
        print(f"[PortfolioCore] DEBUG: 持仓总价值: {portfolio_value}")
        
        # 现金价值
        cash_value = 0.0
        cash_details = {}
        
        for currency, amount in self.cash.items():
            print(f"[PortfolioCore] DEBUG: 处理现金: {currency} {amount}")
            
            if currency == base_currency:
                fx_rate = 1.0
            else:
                fx_rate = self._get_fx_rate(currency, base_currency)
            
            cash_amount = amount * fx_rate
            cash_value += cash_amount
            
            cash_details[currency] = {
                "amount": amount,
                "fx_rate": fx_rate,
                "value": cash_amount
            }
            
            print(f"[PortfolioCore] DEBUG: {currency} 现金价值: {cash_amount}")
        
        print(f"[PortfolioCore] DEBUG: 现金总价值: {cash_value}")
        
        total_value = portfolio_value + cash_value
        print(f"[PortfolioCore] DEBUG: 组合总价值: {total_value}")
        
        # 返回结果
        result = {
            "total_value": total_value,
            "portfolio_value": portfolio_value,
            "cash_value": cash_value,
            "base_currency": base_currency,
            "positions": position_values,
            "cash": cash_details
        }
        
        print(f"[PortfolioCore] DEBUG: 组合价值计算完成，持仓数量: {len(position_values)}")
        return result
    
    def get_cash_balances(self) -> Dict[str, float]:
        """获取现金余额（按货币）"""
        return self.cash.copy()
    
    # ==================== IPortfolioAnalytics 接口实现 ====================
    
    def calculate_rebalance_orders(self) -> List[Dict[str, Any]]:
        """计算再平衡订单（目标 vs 当前）"""
        orders = []
        
        # 获取当前组合价值
        portfolio_value_data = self.get_portfolio_value(self.base_currency)
        total_value = portfolio_value_data["total_value"]
        
        if total_value <= 0:
            return orders
        
        # 获取目标权重
        target_weights = self.get_target_weights()
        
        # 计算当前权重
        current_weights = {}
        for symbol, position_data in portfolio_value_data.get("positions", {}).items():
            current_weights[symbol] = position_data["value"] / total_value
        
        # 计算再平衡需求
        for symbol, target_weight in target_weights.items():
            current_weight = current_weights.get(symbol, 0.0)
            
            # 计算目标价值
            target_value = total_value * target_weight
            
            # 获取当前持仓信息
            position_data = portfolio_value_data["positions"].get(symbol)
            if not position_data:
                # 新资产，需要买入
                orders.append({
                    "symbol": symbol,
                    "action": "BUY",
                    "target_weight": target_weight,
                    "current_weight": 0.0,
                    "target_value": target_value,
                    "current_value": 0.0,
                    "value_delta": target_value
                })
                continue
            
            current_value = position_data["value"]
            value_delta = target_value - current_value
            
            if abs(value_delta) < total_value * 0.001:  # 小于总值的0.1%忽略
                continue
            
            action = "BUY" if value_delta > 0 else "SELL"
            
            orders.append({
                "symbol": symbol,
                "action": action,
                "target_weight": target_weight,
                "current_weight": current_weight,
                "target_value": target_value,
                "current_value": current_value,
                "value_delta": abs(value_delta)
            })
        
        # 按调整金额排序
        orders.sort(key=lambda x: abs(x["value_delta"]), reverse=True)
        
        return orders
    
    def get_portfolio_metrics(self) -> Dict[str, Any]:
        """计算组合指标：收益率、波动率、回撤、夏普比率等"""
        metrics = {}
        
        try:
            # 获取组合历史价格数据
            portfolio_returns = self._get_portfolio_returns_history()
            
            if portfolio_returns is not None and len(portfolio_returns) > 0:
                # 计算基础统计
                total_return = (1 + portfolio_returns).prod() - 1
                annual_return = (1 + total_return) ** (252 / len(portfolio_returns)) - 1
                annual_volatility = portfolio_returns.std() * np.sqrt(252)
                
                # 计算夏普比率（假设无风险利率为2%）
                risk_free_rate = 0.02
                excess_return = annual_return - risk_free_rate
                sharpe_ratio = excess_return / annual_volatility if annual_volatility > 0 else 0
                
                # 计算最大回撤
                cumulative = (1 + portfolio_returns).cumprod()
                running_max = cumulative.expanding().max()
                drawdown = (cumulative - running_max) / running_max
                max_drawdown = drawdown.min()
                
                # 计算索提诺比率（只考虑下行波动）
                negative_returns = portfolio_returns[portfolio_returns < 0]
                downside_std = negative_returns.std() * np.sqrt(252) if len(negative_returns) > 0 else 0
                sortino_ratio = excess_return / downside_std if downside_std > 0 else 0
                
                metrics.update({
                    "total_return": float(total_return),
                    "annual_return": float(annual_return),
                    "annual_volatility": float(annual_volatility),
                    "sharpe_ratio": float(sharpe_ratio),
                    "max_drawdown": float(max_drawdown),
                    "sortino_ratio": float(sortino_ratio),
                    "calmar_ratio": float(annual_return / abs(max_drawdown)) if max_drawdown < 0 else 0,
                    "tracking_error": 0.0,  # 需要基准
                    "information_ratio": 0.0,  # 需要基准
                    "beta": 0.0,  # 需要基准
                    "alpha": 0.0,  # 需要基准
                    "r_squared": 0.0,  # 需要基准
                    "data_points": len(portfolio_returns)
                })
        except Exception as e:
            print(f"[PortfolioCore] 计算组合指标失败: {e}")
        
        # 添加组合基本信息
        portfolio_value = self.get_portfolio_value(self.base_currency)
        
        metrics.update({
            "base_currency": self.base_currency,
            "total_value": portfolio_value["total_value"],
            "portfolio_value": portfolio_value["portfolio_value"],
            "cash_value": portfolio_value["cash_value"],
            "cash_percentage": portfolio_value["cash_value"] / portfolio_value["total_value"] if portfolio_value["total_value"] > 0 else 0,
            "num_positions": len(self.holdings),
            "num_currencies": len(self.cash)
        })
        
        return metrics
    
    def get_risk_metrics(self, confidence_level: float = 0.95) -> Dict[str, Any]:
        """计算风险指标：VaR, CVaR等"""
        risk_metrics = {}
        
        try:
            # 获取组合历史收益
            portfolio_returns = self._get_portfolio_returns_history()
            
            if portfolio_returns is not None and len(portfolio_returns) >= 10:
                # 历史模拟法 VaR
                var_historical = np.percentile(portfolio_returns, (1 - confidence_level) * 100)
                cvar_historical = portfolio_returns[portfolio_returns <= var_historical].mean()
                
                # 参数法 VaR（正态分布假设）
                mean_return = portfolio_returns.mean()
                std_return = portfolio_returns.std()
                z_score = abs(np.percentile(np.random.normal(0, 1, 10000), (1 - confidence_level) * 100))
                var_parametric = mean_return - z_score * std_return
                
                risk_metrics.update({
                    "confidence_level": confidence_level,
                    "var_historical": float(var_historical),
                    "cvar_historical": float(cvar_historical),
                    "var_parametric": float(var_parametric),
                    "expected_shortfall": float(cvar_historical),
                    "standard_deviation": float(std_return),
                    "skewness": float(portfolio_returns.skew()),
                    "kurtosis": float(portfolio_returns.kurtosis()),
                    "data_points": len(portfolio_returns)
                })
        except Exception as e:
            print(f"[PortfolioCore] 计算风险指标失败: {e}")
        
        return risk_metrics
    
    def get_performance_attribution(self) -> Dict[str, Any]:
        """业绩归因分析"""
        attribution = {
            "total_return": 0.0,
            "contributions": {},
            "sectors": {},
            "regions": {}
        }
        
        # 简化版：按持仓贡献计算
        portfolio_value = self.get_portfolio_value(self.base_currency)
        total_value = portfolio_value["total_value"]
        
        if total_value <= 0:
            return attribution
        
        # 这里可以添加更复杂的归因逻辑
        # 暂时返回持仓贡献
        for symbol, position_data in portfolio_value.get("positions", {}).items():
            attribution["contributions"][symbol] = {
                "value": position_data["value"],
                "weight": position_data["value"] / total_value,
                "return_contribution": 0.0  # 需要历史数据
            }
        
        return attribution
    
    # ==================== 辅助方法 ====================
    
    def _get_portfolio_returns_history(self, days: int = 365) -> Optional[pd.Series]:
        """获取组合历史收益率序列"""
        # 简化实现：返回空序列
        # 实际实现需要获取每个资产的历史价格并计算组合收益
        return pd.Series(dtype=float)
    
    def add_position(self, symbol: str, shares: float) -> bool:
        """添加或更新持仓"""
        try:
            self.holdings[str(symbol)] = float(shares)
            self._save_portfolio()
            self._invalidate_portfolio_caches()
            return True
        except Exception as e:
            print(f"[PortfolioCore] 添加持仓失败: {e}")
            return False
    
    def remove_position(self, symbol: str) -> bool:
        """移除持仓"""
        if symbol in self.holdings:
            del self.holdings[symbol]
            self._save_portfolio()
            self._invalidate_portfolio_caches()
            return True
        return False
    
    def update_cash(self, currency: str, amount: float) -> bool:
        """更新现金余额"""
        try:
            self.cash[str(currency)] = float(amount)
            self._save_portfolio()
            self._invalidate_portfolio_caches()
            return True
        except Exception as e:
            print(f"[PortfolioCore] 更新现金失败: {e}")
            return False
    
    def _save_portfolio(self):
        """保存组合配置"""
        try:
            portfolio_data = {
                "cash": self.cash,
                "positions": self.holdings,
                "last_updated": datetime.now().isoformat()
            }
            
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(portfolio_data, f, allow_unicode=True, default_flow_style=False)
            
            print(f"[PortfolioCore] 组合配置已保存: {self.config_path}")
            
        except Exception as e:
            print(f"[PortfolioCore] 保存组合配置失败: {e}")
    
    def _invalidate_portfolio_caches(self):
        """清理组合相关的缓存"""
        if not self.enable_cache:
            return
        
        self.cache.clear_namespace("portfolio")
        self.cache.clear_namespace("prices")
    
    # ==================== 便捷方法 ====================
    
    def get_position_summary(self) -> Dict[str, Any]:
        """获取持仓摘要"""
        portfolio_value = self.get_portfolio_value(self.base_currency)
        
        # 按价值排序
        positions = []
        for symbol, data in portfolio_value.get("positions", {}).items():
            positions.append({
                "symbol": symbol,
                "shares": data["shares"],
                "price": data["price"],
                "currency": data["currency"],
                "value": data["value"],
                "weight": data["value"] / portfolio_value["total_value"] if portfolio_value["total_value"] > 0 else 0
            })
        
        # 按价值降序排序
        positions.sort(key=lambda x: x["value"], reverse=True)
        
        # 按资产类型分组
        by_type = {}
        for pos in positions:
            asset_type = self.asset_type_meta.get(pos["symbol"], "unknown")
            if asset_type not in by_type:
                by_type[asset_type] = {"count": 0, "value": 0.0}
            by_type[asset_type]["count"] += 1
            by_type[asset_type]["value"] += pos["value"]
        
        # 按货币分组
        by_currency = {}
        for pos in positions:
            currency = self.asset_meta.get(pos["symbol"], "unknown")
            if currency not in by_currency:
                by_currency[currency] = {"count": 0, "value": 0.0}
            by_currency[currency]["count"] += 1
            by_currency[currency]["value"] += pos["value"]
        
        return {
            "total_positions": len(positions),
            "total_value": portfolio_value["total_value"],
            "cash_value": portfolio_value["cash_value"],
            "positions": positions,
            "by_type": by_type,
            "by_currency": by_currency,
            "top_positions": positions[:10] if len(positions) > 10 else positions
        }
    
    def _get_default_currency(self, asset_type: str) -> str:
        """根据资产类型获取默认货币"""
        currency_mapping = {
            "cn_stock": "CNY",
            "cn_fund": "CNY",
            "us_equity": "USD",
            "currency": "USD",  # 外汇对的基准货币通常是USD
            "hk_stock": "HKD",
            "jp_stock": "JPY",
            "euro_stock": "EUR",
            "gb_stock": "GBP",
        }
        
        return currency_mapping.get(asset_type, "USD")
    
    def _supplement_missing_metadata(self):
        """为持仓中的资产补充缺失的元数据"""
        print(f"[PortfolioCore] DEBUG: 开始补充缺失的元数据")
        
        for symbol in self.holdings.keys():
            # 检查是否缺少元数据
            needs_supplement = False
            
            if symbol not in self.asset_meta:
                print(f"[PortfolioCore] DEBUG: 资产 {symbol} 缺少货币元数据")
                needs_supplement = True
            
            if symbol not in self.asset_type_meta:
                print(f"[PortfolioCore] DEBUG: 资产 {symbol} 缺少资产类型元数据")
                needs_supplement = True
            
            if needs_supplement:
                # 根据符号模式推断资产类型和货币
                asset_type = self._infer_asset_type(symbol)
                currency = self._get_default_currency(asset_type)
                
                print(f"[PortfolioCore] DEBUG: 推断 {symbol} -> 类型: {asset_type}, 货币: {currency}")
                
                # 设置元数据
                self.asset_meta[symbol] = currency
                self.asset_type_meta[symbol] = asset_type
    
    def _infer_asset_type(self, symbol: str) -> str:
        """根据符号推断资产类型"""
        symbol_str = str(symbol)
        
        # 检查是否为美股（字母开头，不含数字前缀）
        if symbol_str.isalpha() or (symbol_str[0].isalpha() and len(symbol_str) <= 5):
            return "us_equity"
        
        # 检查是否为带前缀的中国股票
        if symbol_str.startswith('sh') or symbol_str.startswith('sz'):
            return "cn_stock"
        
        # 检查是否为纯数字的中国基金代码（通常6位）
        if symbol_str.isdigit() and len(symbol_str) == 6:
            # 根据配置文件中已有的基金推断
            known_funds = ["004502", "000198", "003537", "510300", "005827", "002892"]
            if symbol_str in known_funds:
                return "cn_fund"
            else:
                # 6位数字代码，可能是基金或股票，默认为基金
                return "cn_fund"
        
        # 检查是否为货币对
        if '/' in symbol_str and len(symbol_str) <= 7:
            return "currency"
        
        # 默认返回美股（最可能的情况）
        return "us_equity"
    
    def export_portfolio(self, format: str = "csv", filepath: Optional[str] = None) -> str:
        """导出组合信息"""
        summary = self.get_position_summary()
        
        if format == "csv":
            import pandas as pd
            
            # 创建持仓表格
            positions_df = pd.DataFrame(summary["positions"])
            
            if filepath:
                positions_df.to_csv(filepath, index=False, encoding='utf-8-sig')
                return filepath
            else:
                return positions_df.to_csv(index=False, encoding='utf-8-sig')
        
        elif format == "json":
            import json
            if filepath:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(summary, f, ensure_ascii=False, indent=2)
                return filepath
            else:
                return json.dumps(summary, ensure_ascii=False, indent=2)
        
        else:
            raise ValueError(f"不支持的文件格式: {format}")
