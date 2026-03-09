import asyncio
import pandas as pd
import yfinance as yf
from typing import Optional

# 导入你之前定义的接口 (假设在 interfaces.py 中)
from .interfaces import AsyncBaseFetcher

class YahooFinanceFetcher(AsyncBaseFetcher):
    """
    基于 yfinance 的传统资产抓取器。
    适用于美股、部分非美股、ETF、外汇和部分期货。
    """
    
    # yfinance 支持的 timeframe 列表: 
    # 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
    TIMEFRAME_MAP = {
        '1m': '1m', '5m': '5m', '15m': '15m', '1h': '1h',
        '1d': '1d', '1w': '1wk', '1M': '1mo'
    }

    async def fetch(
        self, 
        symbol: str, 
        start_date: str, 
        end_date: str, 
        timeframe: str = '1d',
        exchange: Optional[str] = None,
        **kwargs
    ) -> pd.DataFrame:
        
        # 1. 转换 timeframe 为 yfinance 认识的格式
        yf_interval = self.TIMEFRAME_MAP.get(timeframe, '1d')
        
        # 2. 拼接交易所前缀 (yfinance 针对非美股通常使用后缀，比如港股腾讯是 '0700.HK')
        # 这里为了保持接口通用性，允许通过传入 exchange 参数或直接在 symbol 中指定
        fetch_symbol = symbol
        if exchange and ":" not in symbol and "." not in symbol:
            # 这是一个简单的示例，实际情况可能需要更复杂的映射字典
            if exchange.upper() == 'HK':
                fetch_symbol = f"{symbol}.HK"
            elif exchange.upper() == 'LSE':
                fetch_symbol = f"{symbol}.L"

        print(f"[Yahoo] 开始抓取 {fetch_symbol} ({yf_interval}) 从 {start_date} 到 {end_date}...")

        # 3. 核心：将同步的 yfinance 调用放入后台线程执行，避免阻塞事件循环
        try:
            # yf.download 默认返回包含 Open, High, Low, Close, Adj Close, Volume 的 DataFrame
            df = await asyncio.to_thread(
                yf.download,
                tickers=fetch_symbol,
                start=start_date,
                end=end_date,
                interval=yf_interval,
                progress=False, # 关闭 yfinance 自带的进度条以保持终端整洁
                **kwargs
            )
        except Exception as e:
            print(f"[Yahoo] 抓取 {fetch_symbol} 失败: {e}")
            return pd.DataFrame()

        # 4. 数据清洗与标准化 (对齐我们在 interfaces.py 中的契约)
        if df.empty:
            print(f"[Yahoo] 警告: {fetch_symbol} 返回了空数据。")
            return pd.DataFrame()

        # 处理多重索引 (yfinance 2.0+ 版本有时会返回 MultiIndex 列)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        # 统一列名为小写
        df.columns = [col.lower() for col in df.columns]
        
        # 提取我们需要的基础列 (如果 yfinance 返回了 'adj close'，我们通常保留原始 'close'，
        # 或者你可以通过 kwargs 控制是否使用前复权价格覆盖 close)
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        available_cols = [c for c in required_cols if c in df.columns]
        df = df[available_cols]

        # 统一索引名称
        df.index.name = 'timestamp'
        
        # 将时区统一转换为无时区 (tz-naive) 或 UTC，避免不同数据源混合时报错
        if df.index.tz is not None:
            df.index = df.index.tz_convert('UTC').tz_localize(None)

        print(f"[Yahoo] {fetch_symbol} 抓取完成！共 {len(df)} 条数据。")
        return df