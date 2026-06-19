"""CN Fund fetcher — delegates to akshare for ETFs, open-end, and money market funds."""

from . import FetcherProtocol, FetchResult
import time
import asyncio

# ── Backend implementation ────────────────────────────────────────────

# fetchers/cn_fund.py
"""
中国公募基金抓取器
支持场内ETF、场外公募基金、货币基金的数据抓取
"""

import os
import asyncio
import datetime
import akshare as ak
import pandas as pd
from typing import Optional

# 导入标准接口
import asyncio, pandas as pd
from typing import Optional


class CnFundFetcher:
    """
    中国公募基金抓取器 (带本地持久化缓存)
    
    特性:
    - 智能路由：场内ETF / 场外公募 / 货币基金
    - 本地缓存：每日只下载一次数万只基金的名录，极速启动
    - 数据修复：根治货币基金时间截断Bug、抹平公募分红跳空缺口
    
    符合 AsyncBaseFetcher 标准接口规范
    """
    
    def __init__(self, cache_dir: str = ".cache"):
        """
        初始化时加载基金名录字典。
        优先从本地读取当天的缓存；若无缓存或已过期，则从网络下载并保存。
        
        Args:
            cache_dir: 缓存目录路径
        """
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, "fund_list_cache.csv")
        self.fund_map = {}
        
        # 确保缓存文件夹存在
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 尝试加载名录
        self._load_fund_map()

    def _load_fund_map(self):
        """核心缓存逻辑：按天过期"""
        today_str = datetime.date.today().isoformat()
        need_download = True

        # 1. 检查本地是否存在缓存文件
        if os.path.exists(self.cache_file):
            # 获取文件的最后修改日期
            mtime = os.path.getmtime(self.cache_file)
            file_date = datetime.date.fromtimestamp(mtime).isoformat()
            
            # 如果是今天下载的，直接用本地文件
            if file_date == today_str:
                print(f"[CN Fund] 命中本地名录缓存 ({self.cache_file})，极速加载中...")
                try:
                    df_funds = pd.read_csv(self.cache_file, dtype=str)
                    need_download = False
                except Exception as e:
                    print(f"[CN Fund] 读取本地缓存失败，准备重新下载: {e}")

        # 2. 如果无缓存或已过期，从网络下载
        if need_download:
            print("[CN Fund] 未命中当天缓存，正在从网络下载全市场基金名录...")
            try:
                df_funds = ak.fund_name_em()
                # 下载成功后，保存到本地
                df_funds.to_csv(self.cache_file, index=False, encoding='utf-8-sig')
                print(f"[CN Fund] 名录下载完成！已保存缓存至: {self.cache_file}")
            except Exception as e:
                print(f"[CN Fund] 网络下载名录失败: {e}")
                return  # 如果网络也失败了，self.fund_map 保持为空字典

        # 3. 将 DataFrame 转换为 O(1) 查询字典
        try:
            # 使用正确的中文列名构建字典
            self.fund_map = df_funds.set_index('基金代码')[['基金简称', '基金类型']].to_dict('index')
            print(f"[CN Fund] 初始化成功！已加载 {len(self.fund_map)} 只公募基金信息。\n")
        except Exception as e:
            print(f"[CN Fund] 构建字典映射失败，请检查 Akshare 返回字段是否变动: {e}")

    async def fetch(
        self, 
        symbol: str, 
        start_date: str, 
        end_date: str, 
        timeframe: str = '1d',
        exchange: Optional[str] = None,
        **kwargs
    ) -> pd.DataFrame:
        """
        主抓取入口：负责智能路由
        
        Args:
            symbol: 基金代码
            start_date: 开始日期 (格式: YYYY-MM-DD)
            end_date: 结束日期 (格式: YYYY-MM-DD)
            timeframe: 时间周期 (基金数据仅支持 '1d')
            exchange: 交易所 (可选，基金数据通常不需要)
            **kwargs: 额外参数
            
        Returns:
            pd.DataFrame: OHLCV 格式的数据，索引为 DatetimeIndex (名称: timestamp)
        """
        print(f"    [CN Fund] 准备抓取: {symbol} | 日期: {start_date} -> {end_date}")
        
        fund_info = self.fund_map.get(symbol)
        if not fund_info:
            print(f"    [Error] 路由失败：{symbol} 不在名录中！")
            return pd.DataFrame()
            
        f_name = fund_info['基金简称']
        f_type = fund_info['基金类型']
        
        # 核心路由逻辑 - 使用 asyncio.to_thread 将同步调用转为异步
        try:
            if '货币' in f_type:
                print(f"    [路由判定] 货币型 -> {f_name} ({f_type})")
                df = await asyncio.to_thread(
                    self._fetch_money_fund, symbol, start_date, end_date
                )
            elif 'ETF' in f_name.upper() and '联接' not in f_name:
                print(f"    [路由判定] 场内ETF -> {f_name} ({f_type})")
                df = await asyncio.to_thread(
                    self._fetch_etf, symbol, start_date, end_date
                )
            else:
                print(f"    [路由判定] 场外公募 -> {f_name} ({f_type})")
                df = await asyncio.to_thread(
                    self._fetch_open_fund, symbol, start_date, end_date
                )
            
            # 标准化输出格式
            return self._standardize_output(df)
            
        except Exception as e:
            print(f"    [Error] {symbol} 抓取异常: {e}")
            return pd.DataFrame()

    def _standardize_output(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化输出格式，确保符合 AsyncBaseFetcher 规范
        
        - 索引名称: timestamp
        - 列名: open, high, low, close, volume (小写)
        """
        if df.empty:
            return pd.DataFrame()
        
        # 确保索引是 DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            return pd.DataFrame()
        
        # 重命名索引
        df.index.name = 'timestamp'
        
        # 统一列名为小写
        df.columns = [col.lower() for col in df.columns]
        
        # 确保包含所有必需列
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                df[col] = 0.0
        
        return df[required_cols]

    # ---------------------------------------------------------
    # 具体的抓取分支逻辑 (内部同步方法)
    # ---------------------------------------------------------
    
    def _fetch_etf(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """抓取场内ETF数据"""
        start_str = start_date.replace("-", "")
        end_str = end_date.replace("-", "")
        
        df = ak.fund_etf_hist_em(
            symbol=symbol, period="daily", start_date=start_str, end_date=end_str, adjust="qfq"
        )
        if df.empty:
            return pd.DataFrame()
        
        df = df.rename(columns={
            '日期': 'Date', '开盘': 'Open', '收盘': 'Close',
            '最高': 'High', '最低': 'Low', '成交量': 'Volume'
        })
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        
        return df.loc[start_date:end_date][['Open', 'High', 'Low', 'Close', 'Volume']]

    def _fetch_open_fund(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """抓取场外公募基金数据"""
        df = ak.fund_open_fund_info_em(symbol=symbol, indicator="累计净值走势")
        if df.empty:
            return pd.DataFrame()
        
        df = df.rename(columns={'净值日期': 'Date', '累计净值': 'Close'})
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        
        # 公募基金只有净值，没有 OHLCV，用 Close 填充
        df['Open'] = df['Close']
        df['High'] = df['Close']
        df['Low'] = df['Close']
        df['Volume'] = 0.0
        
        return df.loc[start_date:end_date][['Open', 'High', 'Low', 'Close', 'Volume']]

    def _fetch_money_fund(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """抓取货币基金数据"""
        df = ak.fund_money_fund_info_em(symbol=symbol)
        if df.empty:
            return pd.DataFrame()
        
        df = df.rename(columns={'净值日期': 'Date', '每万份收益': 'Per10kYield'})
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Per10kYield'] = pd.to_numeric(df['Per10kYield'], errors='coerce')
        
        df = df.dropna(subset=['Date', 'Per10kYield'])
        df = df.sort_values('Date')
        df.set_index('Date', inplace=True)
        
        # 全量历史累加计算复利净值 (基准设为 1.0)
        df['Close'] = 1.0 + (df['Per10kYield'].cumsum() / 10000.0)
        
        df['Open'] = df['Close']
        df['High'] = df['Close']
        df['Low'] = df['Close']
        df['Volume'] = 0.0
        
        return df.loc[start_date:end_date][['Open', 'High', 'Low', 'Close', 'Volume']]


# ── FinData adapter wrapper ───────────────────────────────────────────

from . import _run_async
from typing import Optional, Dict, Any

class CnFundFetcherAdapter(FetcherProtocol):
    PROVIDER = "akshare-cn-fund"

    def __init__(self):
        self._fetcher = CnFundFetcher()

    def get_metadata(self, symbol: str) -> Optional[Dict[str, Any]]:
        info = self._fetcher.fund_map.get(symbol)
        if not info:
            return None
        return {
            "symbol": symbol,
            "name": info.get("基金简称"),
            "product_type": info.get("基金类型"),
            "currency": "CNY",  # Default for CN funds, unless it's QDII which might be USD but our current detector/registry handles it.
        }

    def fetch(self, symbol: str, start_date: str, end_date: str, **kwargs) -> FetchResult:
        t0 = time.time()
        try:
            df = _run_async(self._fetcher.fetch(symbol, start_date, end_date, **kwargs))
            return FetchResult(symbol=symbol, provider=self.PROVIDER, data=df,
                               success=True, latency_ms=(time.time() - t0) * 1000)
        except Exception as e:
            return FetchResult(symbol=symbol, provider=self.PROVIDER, data=None,
                               success=False, latency_ms=(time.time() - t0) * 1000,
                               errors=[str(e)])
