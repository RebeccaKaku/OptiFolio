#!/usr/bin/env python3
"""
独立可测试的中国基金数据获取器
整合了 cn_fund.py 和 money_fund_solution.py 的功能

此文件既是一个接口（实现 BaseFetcher），也可以作为独立程序运行。
当作为独立程序运行时，会测试指定的基金代码并打印一周的数据。

要求：
1. cn_fund 不要求支持货币基金
2. 测试对象：
   - cn_fund 测试对象：000071, 000073, 000218, 008285
   - 货币基金测试对象：004502, 003316, 017629
3. 独立测试时只打印一周的净值
"""

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import sys
from typing import Optional, Dict, List
import json

# BaseFetcher 接口定义（复制自 src/data_core/interface.py）
class BaseFetcher:
    """所有数据抓取器的基类"""
    def fetch(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError


class CnFundFetcher(BaseFetcher):
    """
    中国公募基金抓取器 (支持 ETF、场外基金，但不支持货币基金)
    自动识别基金类型：
    1. 优先尝试 ETF 接口 (具备 OHLC)
    2. 失败则尝试 场外基金接口 (仅 Net Value)
    3. 不尝试货币基金接口（根据要求）
    """
    
    def fetch(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取中国基金数据（ETF 或场外基金）
        
        参数:
            symbol: 基金代码
            start_date: 开始日期，格式 "YYYY-MM-DD"
            end_date: 结束日期，格式 "YYYY-MM-DD"
            
        返回:
            DataFrame 包含以下列:
            - Open: 开盘价
            - High: 最高价
            - Low: 最低价
            - Close: 收盘价
            - Volume: 成交量
        """
        print(f"[CnFundFetcher] 尝试下载中国基金 {symbol}...")
        
        # 统一日期格式：Akshare ETF 接口喜欢 'YYYYMMDD'，而 BaseFetcher 传入的是 'YYYY-MM-DD'
        start_str = start_date.replace("-", "")
        end_str = end_date.replace("-", "")
        
        # --- 策略 A: 尝试当作场内 ETF 获取 (包含 OHLC) ---
        try:
            # adjust='qfq' 代表前复权，这对计算收益率至关重要
            df = ak.fund_etf_hist_em(
                symbol=symbol, 
                period="daily", 
                start_date=start_str, 
                end_date=end_str, 
                adjust="qfq" 
            )
            
            if not df.empty:
                # 重命名为标准列名
                df = df.rename(columns={
                    '日期': 'Date',
                    '开盘': 'Open',
                    '收盘': 'Close',
                    '最高': 'High',
                    '最低': 'Low',
                    '成交量': 'Volume'
                })
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.set_index('Date').sort_index()
                
                # 再次过滤日期 (Akshare 有时会返回多余的数据)
                df = df.loc[start_date:end_date]
                
                print(f"    [成功] 识别为 ETF (场内基金)")
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]

        except Exception:
            # 如果报错，说明可能不是 ETF，静默失败，进入策略 B
            pass

        # --- 策略 B: 尝试当作场外公募基金获取 (仅净值) ---
        try:
            # 场外基金接口通常不支持按日期筛选，必须拉全量后自己在本地过滤
            df = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")
            
            if not df.empty:
                # 场外基金只有 '净值日期' 和 '单位净值'
                df = df.rename(columns={
                    '净值日期': 'Date',
                    '单位净值': 'Close'
                })
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.set_index('Date').sort_index()
                
                # 必须在这里做日期切片，因为接口没参数
                df = df.loc[start_date:end_date]
                
                # 填充其他 OHLC 列，确保格式统一 (Open=High=Low=Close)
                df['Open'] = df['Close']
                df['High'] = df['Close']
                df['Low'] = df['Close']
                df['Volume'] = 0.0 # 场外基金通常没有成交量概念
                
                print(f"    [成功] 识别为 Open Fund (场外公募)")
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
                
        except Exception as e:
            print(f"    [Error] {symbol} 场外基金接口失败: {e}")

        print(f"    [Warning] 无法获取 {symbol} (非 ETF 或公募基金，或代码错误)")
        return pd.DataFrame()


class MoneyFundFetcher(BaseFetcher):
    """
    货币基金专门获取器
    解决货币基金数据获取问题：
    1. 使用 fund_money_fund_info_em 接口获取货币基金历史数据
    2. 货币基金没有'单位净值'，只有'每万份收益'和'7日年化收益率'
    3. 需要处理日期格式和数据清洗
    """
    
    def __init__(self):
        self.cache = {}
    
    def fetch(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取货币基金历史数据
        
        参数:
            symbol: 基金代码，如 "004502"
            start_date: 开始日期，格式 "YYYY-MM-DD"
            end_date: 结束日期，格式 "YYYY-MM-DD"
            
        返回:
            DataFrame 包含标准 OHLCV 列，其中 Close 为累计净值
        """
        print(f"[MoneyFundFetcher] 获取货币基金 {symbol} 历史数据...")
        
        try:
            # 使用货币基金专用接口
            df = ak.fund_money_fund_info_em(symbol=symbol)
            
            if df.empty:
                print(f"警告: {symbol} 数据为空")
                return pd.DataFrame()
            
            # 重命名列
            df = df.rename(columns={
                '净值日期': 'Date',
                '每万份收益': 'Per10kYield',
                '7日年化收益率': 'Annualized7d',
                '申购状态': 'PurchaseStatus',
                '赎回状态': 'RedemptionStatus'
            })
            
            # 转换日期格式
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            
            # 转换数值列
            df['Per10kYield'] = pd.to_numeric(df['Per10kYield'], errors='coerce')
            df['Annualized7d'] = pd.to_numeric(df['Annualized7d'], errors='coerce')
            
            # 按日期排序
            df = df.sort_values('Date').reset_index(drop=True)
            df = df.set_index('Date')
            
            # 日期过滤
            df = df.loc[start_date:end_date]
            
            # 对于货币基金，我们需要将每万份收益转换为类似净值的格式
            # 每万份收益是每10000份基金的收益（元），我们可以累计计算
            if not df.empty:
                # 创建累计收益作为Close价格（假设从1开始）
                df['Close'] = 1.0 + (df['Per10kYield'].cumsum() / 10000.0)
                df['Open'] = df['Close']
                df['High'] = df['Close']
                df['Low'] = df['Close']
                df['Volume'] = 0.0
                
                print(f"    [成功] 获取到 {len(df)} 条数据，时间范围: {df.index.min().date()} 到 {df.index.max().date()}")
                print(f"    [信息] 货币基金 {symbol}: 平均每万份收益 {df['Per10kYield'].mean():.4f}, 平均7日年化 {df['Annualized7d'].mean():.3f}%")
                
                # 缓存结果
                self.cache[symbol] = df
                
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
            else:
                return pd.DataFrame()
            
        except Exception as e:
            print(f"获取 {symbol} 数据失败: {e}")
            return pd.DataFrame()
    
    def fetch_fund_info(self, symbol: str) -> Dict:
        """获取基金基本信息"""
        try:
            info = ak.fund_individual_basic_info_xq(symbol=symbol)
            if not info.empty:
                # 转换为字典格式
                info_dict = {}
                for _, row in info.iterrows():
                    info_dict[row['item']] = row['value']
                return info_dict
        except Exception as e:
            print(f"获取 {symbol} 基本信息失败: {e}")
        
        return {}
    
    def calculate_statistics(self, df: pd.DataFrame) -> Dict:
        """计算货币基金统计指标"""
        if df.empty:
            return {}
        
        stats = {
            'total_records': len(df),
            'date_range': f"{df.index.min().date()} 到 {df.index.max().date()}",
            'latest_date': df.index.max().date().isoformat(),
        }
        
        # 数值统计
        if 'Per10kYield' in df.columns:
            stats['per10k_yield_mean'] = df['Per10kYield'].mean()
            stats['per10k_yield_std'] = df['Per10kYield'].std()
            stats['per10k_yield_max'] = df['Per10kYield'].max()
            stats['per10k_yield_min'] = df['Per10kYield'].min()
            stats['per10k_yield_latest'] = df['Per10kYield'].iloc[-1] if not df.empty else None
        
        if 'Annualized7d' in df.columns:
            stats['annualized7d_mean'] = df['Annualized7d'].mean()
            stats['annualized7d_std'] = df['Annualized7d'].std()
            stats['annualized7d_max'] = df['Annualized7d'].max()
            stats['annualized7d_min'] = df['Annualized7d'].min()
            stats['annualized7d_latest'] = df['Annualized7d'].iloc[-1] if not df.empty else None
        
        return stats


def get_last_week_dates() -> tuple:
    """获取最近一周的日期范围（过去7天）"""
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


def test_cn_funds():
    """测试中国公募基金（非货币基金）"""
    print("\n" + "="*60)
    print("测试中国公募基金（非货币基金）")
    print("="*60)
    
    fetcher = CnFundFetcher()
    test_symbols = ["000071", "000073", "000218", "008285"]
    
    start_date, end_date = get_last_week_dates()
    print(f"测试日期范围: {start_date} 到 {end_date}")
    
    for symbol in test_symbols:
        print(f"\n--- 测试基金 {symbol} ---")
        df = fetcher.fetch(symbol, start_date, end_date)
        
        if not df.empty:
            print(f"获取到 {len(df)} 条数据:")
            # 打印净值（Close列）
            print("净值数据（最近一周）:")
            for date, row in df.iterrows():
                print(f"  {date.date()}: {row['Close']:.4f}")
        else:
            print(f"  未获取到数据")


def test_money_funds():
    """测试货币基金"""
    print("\n" + "="*60)
    print("测试货币基金")
    print("="*60)
    
    fetcher = MoneyFundFetcher()
    test_symbols = ["004502", "003316", "017629"]
    
    start_date, end_date = get_last_week_dates()
    print(f"测试日期范围: {start_date} 到 {end_date}")
    
    for symbol in test_symbols:
        print(f"\n--- 测试货币基金 {symbol} ---")
        df = fetcher.fetch(symbol, start_date, end_date)
        
        if not df.empty:
            print(f"获取到 {len(df)} 条数据:")
            # 打印净值（Close列）
            print("净值数据（最近一周）:")
            for date, row in df.iterrows():
                print(f"  {date.date()}: {row['Close']:.6f}")
            
            # 显示额外信息
            if 'Per10kYield' in df.columns and 'Annualized7d' in df.columns:
                print(f"  平均每万份收益: {df['Per10kYield'].mean():.4f}")
                print(f"  平均7日年化收益率: {df['Annualized7d'].mean():.3f}%")
        else:
            print(f"  未获取到数据")


def run_standalone_test():
    """作为独立程序运行时的测试函数"""
    print("独立可测试的中国基金数据获取器")
    print("="*60)
    print("说明：")
    print("1. 此文件既是一个接口（实现 BaseFetcher），也可以作为独立程序运行")
    print("2. 测试以下基金代码：")
    print("   - 中国公募基金: 000071, 000073, 000218, 008285")
    print("   - 货币基金: 004502, 003316, 017629")
    print("3. 只显示最近一周的数据")
    print("="*60)
    
    # 测试中国公募基金
    test_cn_funds()
    
    # 测试货币基金
    test_money_funds()
    
    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


def main():
    """主函数：用于命令行调用"""
    run_standalone_test()


if __name__ == "__main__":
    main()