# src/data_core/fetchers/cn_stock.py
"""
中国A股数据抓取器，使用akshare获取股票数据。
支持A股历史行情、复权数据、实时数据等。
已适配带前缀的系统ID格式（如 sh600519, sz000001）。
"""
import akshare as ak
import pandas as pd
import re
from datetime import datetime, timedelta
from src.data_core.interface import BaseFetcher


class CnStockFetcher(BaseFetcher):
    """
    中国A股股票数据抓取器。
    
    支持：
    - A股历史行情（复权/不复权）
    - 分时数据
    - 实时行情
    
    输入符号格式：
    - 推荐：带交易所前缀，如 'sh600519'（贵州茅台），'sz000001'（平安银行）
    - 兼容：纯数字代码（尝试自动推断交易所），如 '600519'
    
    返回DataFrame包含标准OHLCV列（Open, High, Low, Close, Volume）。
    """
    
    def fetch(self, symbol: str, start_date: str, end_date: str, 
              period: str = "daily", adjust: str = "qfq") -> pd.DataFrame:
        """
        获取A股历史数据。
        
        Args:
            symbol: 股票代码，推荐格式 'sh600519' 或 'sz000001'
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'
            period: 数据周期，可选 'daily'（日线）, 'weekly'（周线）, 'monthly'（月线）
            adjust: 复权类型，可选 'qfq'（前复权）, 'hfq'（后复权）, ''（不复权）
            
        Returns:
            DataFrame with columns: ['Open', 'High', 'Low', 'Close', 'Volume']
        """
        # 解析代码：获取纯数字代码(code)和带前缀代码(full_symbol)
        code, full_symbol = self._parse_symbol(symbol)
        
        print(f"    [采购-A股] 下载 {full_symbol} | 周期: {period} | 复权: {adjust}...")
        
        # 转换日期格式：akshare需要 'YYYYMMDD'
        start_str = start_date.replace("-", "")
        end_str = end_date.replace("-", "")
        
        # 尝试多个数据源，按优先级排序
        
        # 1. 东方财富 (使用纯数字代码)
        df = self._try_eastmoney(code, start_str, end_str, period, adjust)
        
        # 2. 新浪 (使用带前缀代码)
        if df.empty:
            df = self._try_sina(full_symbol, start_str, end_str, period)
            
        # 3. 腾讯 (使用纯数字代码)
        if df.empty:
            df = self._try_tencent(code, start_str, end_str, period)
        
        if df.empty:
            print(f"    [Warning] 所有数据源都无法获取 {full_symbol} 数据")
            return pd.DataFrame()
        
        # 确保列名标准化
        df = self._standardize_columns(df)
        
        # 按日期范围过滤
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        # 确保索引是Datetime类型以便切片
        if not isinstance(df.index, pd.DatetimeIndex):
             if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.set_index('Date').sort_index()
        
        df = df.loc[start_dt:end_dt]
        
        print(f"    [成功] 获取 {full_symbol} 数据 {len(df)} 条记录")
        return df
    
    def _parse_symbol(self, symbol: str) -> tuple[str, str]:
        """
        解析输入的 symbol，返回 (纯数字代码, 带前缀代码)。
        如果输入是 '600519'，推断为 ('600519', 'sh600519')。
        如果输入是 'sh600519'，返回 ('600519', 'sh600519')。
        """
        # 移除空白字符
        symbol = symbol.strip().lower()
        
        # 提取数字部分
        code_match = re.search(r'\d{6}', symbol)
        if not code_match:
            # 异常情况，原样返回，让接口去报错或处理
            return symbol, symbol
            
        code = code_match.group(0)
        
        # 判断是否已有前缀
        if symbol.startswith(('sh', 'sz')):
            return code, symbol
        else:
            # 推断前缀（为了兼容旧配置或纯数字输入）
            prefix = self._infer_exchange_prefix(code)
            return code, f"{prefix}{code}"

    def _infer_exchange_prefix(self, code: str) -> str:
        """
        根据股票代码数字推断交易所前缀。
        """
        if code.startswith(('600', '601', '603', '605', '688')):
            return 'sh'
        elif code.startswith(('000', '001', '002', '003', '300')):
            return 'sz'
        elif code.startswith(('4', '8')): # 北交所
            return 'bj'
        else:
            return 'sh' # 默认

    def _try_eastmoney(self, code: str, start_date: str, end_date: str, 
                       period: str, adjust: str) -> pd.DataFrame:
        """
        尝试使用东方财富接口（推荐，数据质量高）。
        接口: stock_zh_a_hist
        参数要求: 纯数字代码 (如 '600519')
        """
        try:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust
            )
            
            if df.empty:
                return pd.DataFrame()
            
            # 东方财富接口返回的列名是中文
            column_map = {
                '日期': 'Date',
                '开盘': 'Open',
                '收盘': 'Close',
                '最高': 'High',
                '最低': 'Low',
                '成交量': 'Volume',
                '成交额': 'Amount',
                '振幅': 'Amplitude',
                '涨跌幅': 'ChangePercent',
                '涨跌额': 'Change',
                '换手率': 'Turnover'
            }
            
            # 重命名列
            df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})
            
            # 设置日期索引
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.set_index('Date').sort_index()
            
            return df
            
        except Exception as e:
            # 忽略特定错误，避免刷屏
            # print(f"    [调试] 东方财富接口失败: {e}")
            return pd.DataFrame()
    
    def _try_sina(self, full_symbol: str, start_date: str, end_date: str, period: str) -> pd.DataFrame:
        """
        尝试使用新浪接口（备选方案）。
        接口: stock_zh_a_daily
        参数要求: 带前缀代码 (如 'sh600519')
        """
        try:
            df = ak.stock_zh_a_daily(
                symbol=full_symbol,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"  # 新浪接口可能不支持adjust参数
            )
            
            if df.empty:
                return pd.DataFrame()
            
            # 新浪接口列名可能不同
            column_map = {
                'date': 'Date',
                'open': 'Open',
                'close': 'Close',
                'high': 'High',
                'low': 'Low',
                'volume': 'Volume'
            }
            
            df = df.rename(columns=column_map)
            
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.set_index('Date').sort_index()
            
            return df
            
        except Exception as e:
            # print(f"    [调试] 新浪接口失败: {e}")
            return pd.DataFrame()
    
    def _try_tencent(self, code: str, start_date: str, end_date: str, period: str) -> pd.DataFrame:
        """
        尝试使用腾讯接口（备选方案）。
        接口: stock_zh_a_hist_min_em (这里实际使用的是分钟接口的日线聚合，或者类似的备用接口)
        参数要求: 纯数字代码 (通常)
        """
        try:
            # 腾讯接口逻辑保持原样，注意这里使用了分钟接口来获取近期数据作为兜底
            # 计算天数差
            start_dt = datetime.strptime(start_date, "%Y%m%d")
            end_dt = datetime.strptime(end_date, "%Y%m%d")
            days_diff = (end_dt - start_dt).days + 1
            
            # 限制最多获取最近60天的数据（腾讯该接口可能有限制）
            if days_diff > 60:
                start_dt = end_dt - timedelta(days=60)
                start_date = start_dt.strftime("%Y%m%d")
            
            # 获取数据
            df = ak.stock_zh_a_hist_min_em(
                symbol=code,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )
            
            if df.empty:
                return pd.DataFrame()
            
            # 重命名列
            column_map = {
                '时间': 'Date',
                '开盘': 'Open',
                '收盘': 'Close',
                '最高': 'High',
                '最低': 'Low',
                '成交量': 'Volume'
            }
            
            df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})
            
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.set_index('Date').sort_index()
            
            return df
            
        except Exception as e:
            # print(f"    [调试] 腾讯接口失败: {e}")
            return pd.DataFrame()
    
    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化DataFrame列，确保包含标准OHLCV列。
        """
        # 确保索引是DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.set_index('Date').sort_index()
        
        # 标准列列表
        standard_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        
        # 检查并创建缺失的列
        for col in standard_cols:
            if col not in df.columns:
                if col == 'Volume':
                    df[col] = 0.0
                elif col in ['Open', 'High', 'Low', 'Close']:
                    # 如果有Close列，用Close填充其他价格列
                    if 'Close' in df.columns:
                        df[col] = df['Close']
                    else:
                        df[col] = pd.NA
        
        # 只返回标准列
        available_cols = [col for col in standard_cols if col in df.columns]
        return df[available_cols]
    
    def get_realtime_quote(self, symbol: str) -> dict:
        """
        获取股票实时行情。
        
        Args:
            symbol: 股票代码 (支持 sh600519 或 600519)
            
        Returns:
            包含实时行情数据的字典
        """
        code, full_symbol = self._parse_symbol(symbol)
        
        try:
            # 使用东方财富实时行情接口 (返回所有A股实时数据)
            df = ak.stock_zh_a_spot_em()
            if df.empty:
                return {}
            
            # 查找指定股票 (列名为 '代码'，内容为纯数字)
            stock_data = df[df['代码'] == code]
            
            if not stock_data.empty:
                row = stock_data.iloc[0]
                return {
                    'symbol': full_symbol, # 返回系统使用的标准ID
                    'name': row.get('名称', ''),
                    'latest': row.get('最新价', 0),
                    'change': row.get('涨跌额', 0),
                    'change_percent': row.get('涨跌幅', 0),
                    'volume': row.get('成交量', 0),
                    'amount': row.get('成交额', 0),
                    'high': row.get('最高', 0),
                    'low': row.get('最低', 0),
                    'open': row.get('今开', 0),
                    'prev_close': row.get('昨收', 0)
                }
            
            return {}
            
        except Exception as e:
            print(f"    [Error] 获取实时行情失败: {e}")
            return {}