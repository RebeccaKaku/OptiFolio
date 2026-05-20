# 文件路径: src/data_core/fetchers/us_equity.py
import yfinance as yf
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from src.data_core.interface import BaseFetcher

class TimeoutHTTPAdapter(HTTPAdapter):
    def __init__(self, *args, timeout=2.0, **kwargs):
        self.timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        kwargs["timeout"] = self.timeout
        return super().send(request, **kwargs)

class UsEquityFetcher(BaseFetcher):
    def fetch(self, symbol: str, start_date: str, end_date: str, 
              interval: str = "1d", adjust_price: bool = True) -> pd.DataFrame:
        
        print(f"    [采购-US] 下载 {symbol} | 频率: {interval}...")
        try:
            # 创建带有 2.0 秒超时设置的 session，防止在中国或无网环境下无限挂起
            session = requests.Session()
            adapter = TimeoutHTTPAdapter(timeout=2.0)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            
            ticker = yf.Ticker(symbol, session=session)
            # actions=True 获取分红和拆股信息
            df = ticker.history(
                start=start_date, 
                end=end_date, 
                interval=interval,
                auto_adjust=adjust_price, 
                actions=True
            )
            
            if df.empty:
                return pd.DataFrame()

            # 清洗时区
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            return df

        except Exception as e:
            print(f"    [Error] {symbol} 下载失败 (将使用本地数据缓存): {e}")
            return pd.DataFrame()