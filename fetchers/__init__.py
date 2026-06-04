# fetchers/__init__.py
"""
OptiFolio 数据抓取模块

提供统一的数据抓取接口，支持多种数据源：
- CnFundFetcher: 中国公募基金数据 (基于 akshare)
- IcbcFetcher: 工商银行理财产品数据
- BocFetcher: 中国银行理财产品数据
- BoscFetcher: 上海银行理财产品数据
"""

from .interfaces import AsyncBaseFetcher
from .cn_fund import CnFundFetcher
from .icbc import IcbcFetcher
from .boc import BocFetcher
from .bosc import BoscFetcher

__all__ = [
    "AsyncBaseFetcher",
    "CnFundFetcher",
    "IcbcFetcher",
    "BocFetcher",
    "BoscFetcher",
]
