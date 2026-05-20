"""
常量定义模块

集中管理所有硬编码的常量、配置路径和默认值
"""

from enum import Enum
from typing import Dict, List, Set
from pathlib import Path


class AssetType(str, Enum):
    """资产类型枚举"""
    # 简化类型
    CN_STOCK = "cn_stock"
    CN_FUND = "cn_fund"
    US_EQUITY = "us_equity"
    
    # 向后兼容类型 - 中国股票
    CN_STOCK_SH = "cn_stock_sh"
    CN_STOCK_SZ = "cn_stock_sz"
    HK_STOCK = "hk_stock"
    
    # 向后兼容类型 - 中国基金
    CN_FUND_OPEN = "cn_fund_open"
    CN_FUND_ETF = "cn_fund_etf"
    CN_FUND_QDII = "cn_fund_qdii"
    CN_FUND_MONEY = "cn_fund_money"
    CN_FUND_LOF = "cn_fund_lof"
    CN_FUND_INDEX = "cn_fund_index"
    
    # 其他
    CURRENCY = "currency"
    US_STOCK = "us_stock"


class Currency(str, Enum):
    """货币类型枚举"""
    CNY = "CNY"  # 人民币
    USD = "USD"  # 美元
    HKD = "HKD"  # 港币
    EUR = "EUR"  # 欧元
    JPY = "JPY"  # 日元
    GBP = "GBP"  # 英镑


# 路径常量
class Paths:
    """路径常量"""
    BASE_DIR = Path(".")
    CONFIG_DIR = BASE_DIR / "config"
    DATA_DIR = BASE_DIR / "data"
    LOGS_DIR = BASE_DIR / "logs"
    
    # 配置文件
    ASSET_REGISTRY = CONFIG_DIR / "asset_registry.yaml"
    CANDIDATES = CONFIG_DIR / "candidates.yaml"
    PORTFOLIO = CONFIG_DIR / "portfolio.yaml"
    SETTINGS = CONFIG_DIR / "settings.yaml"
    SECRETS = CONFIG_DIR / "secrets.yaml"
    
    # 数据目录
    RAW_DATA = DATA_DIR / "raw"
    PROCESSED_DATA = DATA_DIR / "processed"
    
    @classmethod
    def ensure_directories(cls):
        """确保所有必要的目录存在"""
        for path in [cls.CONFIG_DIR, cls.RAW_DATA, cls.PROCESSED_DATA, cls.LOGS_DIR]:
            path.mkdir(parents=True, exist_ok=True)


# 资产类型映射
ASSET_TYPE_CURRENCY_MAP: Dict[str, str] = {
    # 简化类型
    AssetType.CN_STOCK: Currency.CNY,
    AssetType.CN_FUND: Currency.CNY,
    AssetType.US_EQUITY: Currency.USD,
    
    # 向后兼容类型
    AssetType.CN_STOCK_SH: Currency.CNY,
    AssetType.CN_STOCK_SZ: Currency.CNY,
    AssetType.CN_FUND_OPEN: Currency.CNY,
    AssetType.CN_FUND_ETF: Currency.CNY,
    AssetType.CN_FUND_QDII: Currency.CNY,
    AssetType.CN_FUND_MONEY: Currency.CNY,
    AssetType.CN_FUND_LOF: Currency.CNY,
    AssetType.CN_FUND_INDEX: Currency.CNY,
    AssetType.US_STOCK: Currency.USD,
    AssetType.HK_STOCK: Currency.HKD,
    AssetType.CURRENCY: Currency.USD,
}


# 有效的资产类型集合
VALID_ASSET_TYPES: Set[str] = {
    AssetType.CN_STOCK,
    AssetType.CN_FUND,
    AssetType.US_EQUITY,
}

COMPATIBLE_ASSET_TYPES: Set[str] = {
    AssetType.CN_STOCK_SH,
    AssetType.CN_STOCK_SZ,
    AssetType.HK_STOCK,
    AssetType.CN_FUND_OPEN,
    AssetType.CN_FUND_ETF,
    AssetType.CN_FUND_QDII,
    AssetType.CN_FUND_MONEY,
    AssetType.CN_FUND_LOF,
    AssetType.CN_FUND_INDEX,
    AssetType.US_STOCK,
    AssetType.CURRENCY,
}

ALL_ASSET_TYPES: Set[str] = VALID_ASSET_TYPES | COMPATIBLE_ASSET_TYPES


# 缓存配置
class CacheConfig:
    """缓存配置"""
    DEFAULT_TTL = 3600  # 1小时
    LONG_TTL = 86400   # 24小时
    SHORT_TTL = 300    # 5分钟
    
    # 命名空间
    NAMESPACE_ASSET = "asset"
    NAMESPACE_PRICE = "price"
    NAMESPACE_PORTFOLIO = "portfolio"
    NAMESPACE_FX = "fx"


# API配置
class APIConfig:
    """API配置"""
    TIMEOUT = 30  # 秒
    RETRY_COUNT = 3
    RETRY_DELAY = 1  # 秒
    
    # 数据源
    SOURCE_AKSHARE = "akshare"
    SOURCE_YFINANCE = "yfinance"
    SOURCE_MANUAL = "manual"


# 数据处理配置
class DataConfig:
    """数据处理配置"""
    DEFAULT_START_DATE = "2020-01-01"
    MIN_DATA_POINTS = 30  # 最小数据点数量
    MAX_MISSING_RATIO = 0.1  # 最大缺失值比例
    
    # 频率映射
    FREQUENCY_MAP = {
        "daily": "1d",
        "weekly": "1wk",
        "monthly": "1mo",
    }


# 组合配置
class PortfolioConfig:
    """组合配置"""
    DEFAULT_BASE_CURRENCY = Currency.CNY
    REBALANCE_THRESHOLD = 0.05  # 再平衡阈值
    MAX_POSITIONS = 50  # 最大持仓数量


# 错误代码
class ErrorCode:
    """错误代码"""
    ASSET_NOT_FOUND = "ASSET_NOT_FOUND"
    INVALID_ASSET_TYPE = "INVALID_ASSET_TYPE"
    DATA_FETCH_ERROR = "DATA_FETCH_ERROR"
    DATA_VALIDATION_ERROR = "DATA_VALIDATION_ERROR"
    CALCULATION_ERROR = "CALCULATION_ERROR"
    CONFIG_ERROR = "CONFIG_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"


# 日志级别映射
LOG_LEVEL_MAP = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


# 股票代码规则
class StockRules:
    """股票代码规则"""
    # 上海交易所前缀
    SH_PREFIXES = ("600", "601", "603", "605", "688")
    # 深圳交易所前缀
    SZ_PREFIXES = ("000", "001", "002", "003", "300")
    
    @classmethod
    def get_exchange_prefix(cls, code: str) -> str:
        """
        根据代码获取交易所前缀
        
        Args:
            code: 6位股票代码
            
        Returns:
            'sh' 或 'sz'
        """
        if code.startswith(cls.SH_PREFIXES):
            return "sh"
        elif code.startswith(cls.SZ_PREFIXES):
            return "sz"
        return "sh"  # 默认上海


# 币种检测关键词
CURRENCY_KEYWORDS = {
    Currency.USD: ["美元", "usd", "US Dollar", "美元现汇", "美元现钞"],
    Currency.HKD: ["港币", "hkd", "HK Dollar", "港元"],
    Currency.EUR: ["欧元", "eur", "Euro"],
    Currency.JPY: ["日元", "jpy", "Yen"],
    Currency.GBP: ["英镑", "gbp", "Pound"],
}