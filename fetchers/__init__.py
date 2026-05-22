# fetchers/__init__.py
"""
OptiFolio 数据抓取模块

提供统一的数据抓取接口，支持多种数据源：
- CryptoFetcher: 加密货币数据 (基于 CCXT)
- YahooFinanceFetcher: 美股/港股/ETF 数据 (基于 yfinance)
- CnFundFetcher: 中国公募基金数据 (基于 akshare)
"""

from .interfaces import AsyncBaseFetcher
from .crypto_fetcher import CryptoFetcher
from .yahoo_fetcher import YahooFinanceFetcher
from .cn_fund import CnFundFetcher
from .icbc import IcbcFetcher
from .boc import BocFetcher
from .bosc import BoscFetcher

# 别名，方便使用
YFinanceFetcher = YahooFinanceFetcher
AkshareFetcher = CnFundFetcher

__all__ = [
    # 核心接口
    'AsyncBaseFetcher',
    # 具体实现
    'CryptoFetcher',
    'YahooFinanceFetcher',
    'CnFundFetcher',
    'IcbcFetcher',
    'BocFetcher',
    'BoscFetcher',
    # 别名
    'YFinanceFetcher',
    'AkshareFetcher',
]
