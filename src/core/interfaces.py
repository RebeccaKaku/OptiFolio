"""
抽象接口层 - 定义核心业务接口，支持未来扩展

设计原则：
1. 接口隔离 - 每个接口职责单一
2. 依赖倒置 - 高层模块不依赖低层模块，都依赖抽象
3. 开闭原则 - 对扩展开放，对修改封闭
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union
import pandas as pd


class IAssetProvider(ABC):
    """资产数据提供者接口 - 获取资产基本信息"""
    
    @abstractmethod
    def get_asset_info(self, symbol: str) -> Dict[str, Any]:
        """获取资产详细信息"""
        pass
    
    @abstractmethod
    def list_assets(self, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有资产，支持按类型过滤"""
        pass
    
    @abstractmethod
    def search_assets(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """搜索资产（按代码、名称、类型等）"""
        pass


class IAssetImporter(ABC):
    """资产导入接口 - 从外部源导入资产"""
    
    @abstractmethod
    def import_asset(self, symbol: str, asset_type: Optional[str] = None, 
                    refresh: bool = False) -> Dict[str, Any]:
        """导入资产（智能识别类型）"""
        pass
    
    @abstractmethod
    def batch_import(self, symbols: List[str], 
                    asset_types: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """批量导入资产"""
        pass
    
    @abstractmethod
    def update_asset_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, bool]:
        """更新资产价格数据"""
        pass


class IPortfolioData(ABC):
    """组合数据接口 - 获取组合相关信息"""
    
    @abstractmethod
    def get_current_holdings(self) -> Dict[str, float]:
        """获取当前持仓（symbol -> shares）"""
        pass
    
    @abstractmethod
    def get_target_weights(self) -> Dict[str, float]:
        """从策略引擎获取目标权重"""
        pass
    
    @abstractmethod
    def get_portfolio_value(self, base_currency: str = "CNY") -> Dict[str, float]:
        """获取组合价值（多货币支持）"""
        pass
    
    @abstractmethod
    def get_cash_balances(self) -> Dict[str, float]:
        """获取现金余额（按货币）"""
        pass


class IPortfolioAnalytics(ABC):
    """组合分析接口 - 计算各种指标"""
    
    @abstractmethod
    def calculate_rebalance_orders(self) -> List[Dict[str, Any]]:
        """计算再平衡订单（目标 vs 当前）"""
        pass
    
    @abstractmethod
    def get_portfolio_metrics(self) -> Dict[str, Any]:
        """计算组合指标：收益率、波动率、回撤、夏普比率等"""
        pass
    
    @abstractmethod
    def get_risk_metrics(self, confidence_level: float = 0.95) -> Dict[str, Any]:
        """计算风险指标：VaR, CVaR等"""
        pass
    
    @abstractmethod
    def get_performance_attribution(self) -> Dict[str, Any]:
        """业绩归因分析"""
        pass


class IDataFetcher(ABC):
    """数据获取接口 - 抽象数据源"""
    
    @abstractmethod
    def fetch_price_data(self, symbol: str, start_date: str, 
                        end_date: str, frequency: str = "daily") -> pd.DataFrame:
        """获取价格数据"""
        pass
    
    @abstractmethod
    def fetch_metadata(self, symbol: str, asset_type: str) -> Dict[str, Any]:
        """获取元数据（名称、类型、币种等）"""
        pass


class ICacheProvider(ABC):
    """缓存接口 - 提升性能"""
    
    @abstractmethod
    def get(self, key: str, namespace: str = "default") -> Optional[Any]:
        """获取缓存值"""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: int = 3600, 
           namespace: str = "default") -> bool:
        """设置缓存值"""
        pass
    
    @abstractmethod
    def delete(self, key: str, namespace: str = "default") -> bool:
        """删除缓存值"""
        pass
    
    @abstractmethod
    def clear_namespace(self, namespace: str = "default") -> bool:
        """清除命名空间下的所有缓存"""
        pass


class IAssetTypeRegistry(ABC):
    """资产类型注册接口 - 支持动态扩展"""
    
    @abstractmethod
    def register_asset_type(self, asset_type: str, 
                           fetcher_class: Any, 
                           importer_class: Optional[Any] = None) -> bool:
        """注册新的资产类型"""
        pass
    
    @abstractmethod
    def get_supported_types(self) -> List[str]:
        """获取支持的资产类型列表"""
        pass
    
    @abstractmethod
    def get_fetcher_for_type(self, asset_type: str) -> Optional[Any]:
        """获取资产类型对应的Fetcher"""
        pass


class IStorageProvider(ABC):
    """存储接口 - 支持多种存储后端"""
    
    @abstractmethod
    def save_asset_definition(self, asset_def: Dict[str, Any]) -> bool:
        """保存资产定义"""
        pass
    
    @abstractmethod
    def load_asset_definition(self, symbol: str) -> Optional[Dict[str, Any]]:
        """加载资产定义"""
        pass
    
    @abstractmethod
    def save_portfolio_state(self, portfolio_data: Dict[str, Any]) -> bool:
        """保存组合状态"""
        pass
    
    @abstractmethod
    def load_portfolio_state(self) -> Optional[Dict[str, Any]]:
        """加载组合状态"""
        pass


# 复合接口 - 组合多个单一接口
class IAssetManager(IAssetProvider, IAssetImporter, IAssetTypeRegistry):
    """资产管理复合接口"""
    pass


class IPortfolioManager(IPortfolioData, IPortfolioAnalytics):
    """组合管理复合接口"""
    pass


class IAnalyticsEngine(ABC):
    """分析引擎接口 - 统一分析功能"""
    
    @abstractmethod
    def analyze_asset(self, symbol: str, period: str = "1y") -> Dict[str, Any]:
        """分析单个资产"""
        pass
    
    @abstractmethod
    def analyze_portfolio(self, portfolio_symbols: List[str], 
                         weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """分析组合"""
        pass
    
    @abstractmethod
    def compare_assets(self, symbols: List[str], 
                      metrics: List[str] = ["return", "volatility", "sharpe"]) -> pd.DataFrame:
        """比较多个资产"""
        pass