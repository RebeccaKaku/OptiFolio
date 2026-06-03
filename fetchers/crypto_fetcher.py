import asyncio
import pandas as pd
import ccxt.async_support as ccxt  # 需要安装: pip install ccxt
from datetime import datetime
from typing import Optional

# 导入你之前定义的接口
from .interfaces import AsyncBaseFetcher

class CryptoFetcher(AsyncBaseFetcher):
    """
    基于 CCXT 库的通用加密货币数据抓取器。
    支持 Binance, OKX, Kraken 等主流交易所。
    """

    def __init__(self, exchange_id: str = 'binance'):
        self.exchange_id = exchange_id
        # 动态加载交易所类 (如 ccxt.binance)
        self.exchange_class = getattr(ccxt, exchange_id)

    async def fetch(
        self, 
        symbol: str, 
        start_date: str, 
        end_date: str, 
        timeframe: str = '1d',
        exchange: Optional[str] = None, # 这里的 exchange 参数可用于覆盖初始化的交易所
        **kwargs
    ) -> pd.DataFrame:
        
        # 如果传入了特定的 exchange，使用它；否则使用默认的
        exchange_id = exchange if exchange else self.exchange_id
        
        # 实例化交易所客户端
        exchange_client = getattr(ccxt, exchange_id)({
            'enableRateLimit': True,  # 自动处理 API 频率限制，防止被封 IP
            # 'apiKey': '...',      # 如果需要抓取私有数据，可以在这里传入
            # 'secret': '...',
        })

        try:
            # 1. 时间格式转换: 字符串 -> Unix Timestamp (毫秒)
            # CCXT 和大多数交易所使用毫秒级时间戳
            since = exchange_client.parse8601(f"{start_date}T00:00:00Z")
            end_ts = exchange_client.parse8601(f"{end_date}T23:59:59Z")
            
            all_ohlcv = []
            
            print(f"[{exchange_id}] 开始抓取 {symbol} ({timeframe}) 从 {start_date} 到 {end_date}...")

            # 2. 循环分页抓取 (Pagination Loop)
            while since < end_ts:
                try:
                    # fetch_ohlcv(symbol, timeframe, since, limit)
                    ohlcv = await exchange_client.fetch_ohlcv(symbol, timeframe, since, limit=1000)
                    
                    if not ohlcv:
                        print(f"[{exchange_id}] {symbol} 在 {pd.to_datetime(since, unit='ms')} 之后没有更多数据了。")
                        break
                    
                    # 累加数据
                    all_ohlcv.extend(ohlcv)
                    
                    # 更新 since: 取最后一条数据的时间戳 + 1个 timeframe 的毫秒数
                    # 简单起见，直接取最后一条的时间戳作为下一次的起点（CCXT会自动处理重叠）
                    last_timestamp = ohlcv[-1][0]
                    
                    # 如果获取到的数据时间没有推进，说明已经到头了或者交易所卡住了，强制退出
                    if last_timestamp == since:
                        break
                        
                    since = last_timestamp + 1 # +1ms 避免包含上一条
                    
                    # 如果抓取到的最新时间已经超过结束时间，停止
                    if since >= end_ts:
                        break
                        
                    # 稍微打印一下进度
                    current_date = pd.to_datetime(last_timestamp, unit='ms')
                    print(f"  -> 已抓取至: {current_date} (共 {len(all_ohlcv)} 条)")

                except Exception as e:
                    print(f"抓取中断 (Network Error): {e}")
                    # 可以在这里加入重试逻辑
                    await asyncio.sleep(5)
                    continue

            # 3. 数据转换为 DataFrame
            if not all_ohlcv:
                return pd.DataFrame()

            df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # 转换 Unix ms 时间戳为 UTC datetime（CCXT 返回 UTC 时间戳）
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
            df.set_index('timestamp', inplace=True)
            
            # 截取用户需要的最终时间段
            df = df.loc[start_date:end_date]
            
            return df

        finally:
            # 必须关闭连接，否则会报 "Unclosed client session" 警告
            await exchange_client.close()