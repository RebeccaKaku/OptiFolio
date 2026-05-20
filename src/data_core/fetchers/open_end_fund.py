# src/data_core/fetchers/cn_fund.py
import akshare as ak
import pandas as pd
from src.data_core.interface import BaseFetcher

class CnFundFetcher(BaseFetcher):
    """
    中国公募基金抓取器 (支持 ETF、场外基金和货币基金)
    自动识别基金类型：
    1. 优先尝试 ETF 接口 (具备 OHLC)
    2. 失败则尝试 场外基金接口 (仅 Net Value)
    3. 失败则尝试 货币基金接口 (每万份收益和7日年化)
    """
    
    def fetch(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        print(f"    [采购-CN] 尝试下载中国基金 {symbol}...")
        
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

        # --- 策略 C: 尝试当作货币基金获取 (每万份收益和7日年化) ---
        try:
            # 货币基金使用专用接口
            df = ak.fund_money_fund_info_em(symbol=symbol)
            
            if not df.empty:
                # 货币基金数据重命名
                df = df.rename(columns={
                    '净值日期': 'Date',
                    '每万份收益': 'Per10kYield',
                    '7日年化收益率': 'Annualized7d',
                    '申购状态': 'PurchaseStatus',
                    '赎回状态': 'RedemptionStatus'
                })
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                df['Per10kYield'] = pd.to_numeric(df['Per10kYield'], errors='coerce')
                df['Annualized7d'] = pd.to_numeric(df['Annualized7d'], errors='coerce')
                
                # 按日期排序并设置索引
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
                    
                    print(f"    [成功] 识别为 Money Fund (货币基金) - 使用累计收益作为净值")
                    print(f"    [信息] 货币基金 {symbol}: 平均每万份收益 {df['Per10kYield'].mean():.4f}, 平均7日年化 {df['Annualized7d'].mean():.3f}%")
                    return df[['Open', 'High', 'Low', 'Close', 'Volume']]
                
        except Exception as e:
            print(f"    [Error] {symbol} 货币基金接口失败: {e}")

        print(f"    [Warning] 无法获取 {symbol} (非 ETF、公募基金或货币基金，或代码错误)")
        return pd.DataFrame()
