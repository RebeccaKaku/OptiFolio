import asyncio
from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional

# ==========================================
# 1. 核心基类：定义异步抓取接口
# ==========================================
class AsyncBaseFetcher(ABC):
    """
    异步数据抓取器基类。

    数据返回规范约定:
    - 常规K线 (timeframe='1d', '1m' 等):
        返回 OHLCV 格式。Index 必须是 pd.DatetimeIndex。允许时间不连续（如缺漏某分钟的数据）。
    - 逐笔数据 (timeframe='tick'):
        返回交易明细 (price, size, side)。Index 为发生时间，属于事件驱动型数据。
    """

    @abstractmethod
    async def fetch(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        timeframe: str = '1d',
        exchange: Optional[str] = None,
        **kwargs
    ) -> pd.DataFrame:
        pass
