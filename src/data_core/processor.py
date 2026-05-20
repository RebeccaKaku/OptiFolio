# src/data_core/processor.py
"""
增强版数据处理器 - 合并 processor.py 和 processors.py 的功能
负责数据的清洗、对齐、重采样和标准化。
解决多资产频率不一致和数据缺失问题。
支持多种对齐策略。
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Union, Tuple


class DataProcessor:
    """
    增强版数据处理器
    
    功能：
    1. 支持多种对齐策略：common_start, pairwise, raw
    2. 处理整个投资组合的数据字典
    3. 生成统一时间索引
    4. 基础数据清洗和标准化
    5. 协方差矩阵计算（支持成对剔除）
    """
    
    def __init__(self, strategy: str = "common_start", base_freq: str = '1D'):
        """
        初始化数据处理器
        
        Args:
            strategy: 数据对齐策略，可选:
                - "common_start": 方案B - 找到所有资产都有数据的共同开始日期
                - "pairwise": 方案A - 成对剔除（在计算时处理）
                - "raw": 保留原始数据，不进行对齐
            base_freq: 基准频率，默认为日线('1D')
                       支持 pandas offset aliases: '1H', '1min', 'B' (工作日) 等。
        """
        self.strategy = strategy
        self.base_freq = base_freq
    
    def align_and_clean(self, data_dict: Dict[str, pd.DataFrame], 
                       start_date: str, end_date: str) -> pd.DataFrame:
        """
        时空对齐与清洗（兼容旧接口）
        
        根据策略处理数据对齐：
        1. common_start: 找到共同开始日期，确保所有资产都有数据
        2. pairwise: 返回原始数据，在后续计算中成对剔除
        3. raw: 保留原始数据
        
        Args:
            data_dict: 资产数据字典 {symbol: series}
            start_date: 用户指定的开始日期
            end_date: 用户指定的结束日期
            
        Returns:
            pandas.DataFrame: 对齐后的数据框
        """
        print(f"    [加工] 正在执行时空对齐 (策略: {self.strategy})...")
        if not data_dict:
            return pd.DataFrame()
        
        # [双重保险] 再次清洗字典，确保全是 1D Series
        clean_dict = {}
        for k, v in data_dict.items():
            if isinstance(v, pd.DataFrame):
                # 再次强制压扁
                v = v.squeeze()
            clean_dict[k] = v
            
        # 1. 拼接
        try:
            df = pd.DataFrame(clean_dict)
        except ValueError as e:
            print(f"    [Error] 拼接失败，正在尝试暴力修复: {e}")
            # 如果还报错，说明有严重的维度问题，打印出来看是谁捣乱
            for k, v in clean_dict.items():
                print(f"        {k}: type={type(v)}, shape={v.shape}")
            raise e
        
        # 2. 排序与截取到用户指定日期范围
        df = df.sort_index()
        df = df[start_date : end_date]
        
        # 3. 根据策略处理数据对齐
        if self.strategy == "common_start":
            return self._common_start_strategy(df)
        elif self.strategy == "pairwise":
            return self._pairwise_strategy(df)
        elif self.strategy == "raw":
            return self._raw_strategy(df)
        else:
            print(f"    [Warning] 未知策略 {self.strategy}，使用 common_start")
            return self._common_start_strategy(df)
    
    def process_portfolio_data(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """
        处理整个投资组合的数据字典。
        流程：标准化列 -> 处理异常值 -> 时间轴对齐 -> 填充缺失值
        
        Args:
            data_map: 原始数据字典 {symbol: DataFrame}
            
        Returns:
            处理后的数据字典 {symbol: DataFrame}
        """
        processed_map = {}
        
        # 1. 收集所有数据的时间戳，生成全局统一的时间索引
        full_time_index = self._generate_unified_index(data_map)
        
        for symbol, df in data_map.items():
            if df.empty:
                print(f"[Processor Warning] {symbol} 数据为空，跳过处理")
                continue
                
            # 2. 基础清洗
            df_clean = self._clean_basic(df)
            
            # 3. 重采样与对齐 (核心步骤)
            # reindex 会引入 NaN，ffill 负责用最近已知值填充
            df_aligned = df_clean.reindex(full_time_index, method='ffill')
            
            processed_map[symbol] = df_aligned
            
        return processed_map
    
    def _generate_unified_index(self, data_map: Dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
        """
        生成统一的时间索引（并集）。
        策略：取最早开始时间和最晚结束时间，按 base_freq 生成完整序列。
        """
        start_dates = []
        end_dates = []
        
        for df in data_map.values():
            if not df.empty and isinstance(df.index, pd.DatetimeIndex):
                start_dates.append(df.index.min())
                end_dates.append(df.index.max())
        
        if not start_dates:
            return pd.DatetimeIndex([])
            
        min_start = min(start_dates)
        max_end = max(end_dates)
        
        # 生成连续的时间序列，覆盖中间的所有空缺
        # 例如：A股放假了，美股没放，这里会生成包含A股假期的时间点
        unified_index = pd.date_range(start=min_start, end=max_end, freq=self.base_freq)
        return unified_index
    
    def _clean_basic(self, df: pd.DataFrame) -> pd.DataFrame:
        """基础清洗：去重、排序、标准列名检查"""
        df = df.copy()
        
        # 去除重复索引
        if df.index.has_duplicates:
            df = df[~df.index.duplicated(keep='last')]
            
        # 确保按时间排序
        df = df.sort_index()
        
        # 处理 0 成交量 (有时数据源用0表示缺失)
        # 注意：价格不应为0或负数，可以替换为NaN待后续处理
        cols_to_check = ['Open', 'High', 'Low', 'Close']
        for col in cols_to_check:
            if col in df.columns:
                df[col] = df[col].replace(0, np.nan)
        
        return df
    
    def _common_start_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        方案B：找到所有资产都有数据的共同开始日期
        
        返回从第一个所有资产都有数据的日期开始的数据
        不进行全局dropna，而是向前填充然后找到共同开始点
        """
        # 向前填充缺失值（仅限同一资产的历史数据）
        df_filled = df.ffill()
        
        # 找到第一个所有资产都有非NaN值的日期
        valid_start_idx = df_filled.notna().all(axis=1)
        if valid_start_idx.any():
            common_start_date = df_filled.index[valid_start_idx.argmax()]
            result = df_filled.loc[common_start_date:]
            
            # 统计信息
            n_assets = len(df.columns)
            original_days = len(df)
            result_days = len(result)
            lost_days = original_days - result_days
            
            print(f"    [Info] 共同开始日期: {common_start_date.date()}")
            print(f"    [Info] 资产数: {n_assets}, 原始天数: {original_days}, 对齐后天数: {result_days}")
            if lost_days > 0:
                print(f"    [Info] 截断历史天数: {lost_days}")
            
            return result
        else:
            print("    [Warning] 无法找到共同开始日期，返回原始数据")
            return df
    
    def _pairwise_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        方案A：成对剔除策略
        
        返回原始数据，标记缺失值。
        在后续计算协方差等统计量时，仅使用共同时间段的数据。
        """
        print("    [Info] 使用成对剔除策略 - 返回原始数据（含NaN）")
        print(f"    [Info] 数据形状: {df.shape}, 缺失值比例: {df.isna().sum().sum() / (df.shape[0] * df.shape[1]):.2%}")
        return df
    
    def _raw_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        原始策略：仅向前填充，不删除任何数据
        """
        df_filled = df.ffill()
        print(f"    [Info] 使用原始策略 - 向前填充后返回")
        return df_filled
    
    def get_aligned_close_matrix(self, processed_map: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        获取对齐后的收盘价矩阵 (常用于计算协方差等)。
        行：时间，列：资产代码
        """
        close_data = {sym: df['Close'] for sym, df in processed_map.items()}
        return pd.DataFrame(close_data)
    
    def find_common_time_range(self, df: pd.DataFrame) -> Tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
        """
        辅助方法：找到所有资产的共同时间范围
        
        Args:
            df: pandas.DataFrame
            
        Returns:
            (start_date, end_date): 共同时间范围的开始和结束日期
        """
        if df.empty:
            return None, None
        
        # 找到每个资产有数据的日期范围
        asset_ranges = {}
        for col in df.columns:
            valid_data = df[col].dropna()
            if not valid_data.empty:
                asset_ranges[col] = (valid_data.index.min(), valid_data.index.max())
        
        if not asset_ranges:
            return None, None
        
        # 计算所有资产的交集
        common_start = max([start for start, _ in asset_ranges.values()])
        common_end = min([end for _, end in asset_ranges.values()])
        
        if common_start > common_end:
            return None, None
        
        return common_start, common_end
    
    def calculate_pairwise_covariance(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算成对协方差矩阵
        
        仅使用两个资产都有的共同时间段计算协方差
        对于缺失数据对，返回NaN
        
        Args:
            df: pandas.DataFrame 可能包含NaN
            
        Returns:
            pandas.DataFrame: 协方差矩阵
        """
        n_assets = len(df.columns)
        cov_matrix = pd.DataFrame(np.nan, index=df.columns, columns=df.columns)
        
        for i in range(n_assets):
            for j in range(i, n_assets):
                asset_i = df.columns[i]
                asset_j = df.columns[j]
                
                # 仅使用两个资产都有的数据点
                pair_data = df[[asset_i, asset_j]].dropna()
                if len(pair_data) >= 2:  # 至少需要2个点计算协方差
                    cov = pair_data.cov().iloc[0, 1]
                    cov_matrix.loc[asset_i, asset_j] = cov
                    cov_matrix.loc[asset_j, asset_i] = cov
                else:
                    cov_matrix.loc[asset_i, asset_j] = np.nan
                    cov_matrix.loc[asset_j, asset_i] = np.nan
        
        return cov_matrix
    
    def set_strategy(self, strategy: str) -> None:
        """设置对齐策略"""
        valid_strategies = ["common_start", "pairwise", "raw"]
        if strategy in valid_strategies:
            self.strategy = strategy
            print(f"    [Processor] 策略已切换为: {strategy}")
        else:
            print(f"    [Warning] 无效策略: {strategy}, 保持原策略: {self.strategy}")
    
    def set_base_freq(self, base_freq: str) -> None:
        """设置基准频率"""
        self.base_freq = base_freq
        print(f"    [Processor] 基准频率已设置为: {base_freq}")


# 便捷函数
def calc_moving_average(series: pd.Series, window: int) -> pd.Series:
    """简单移动平均"""
    return series.rolling(window=window, min_periods=1).mean()

def calc_rsi(series: pd.Series, periods: int = 14) -> pd.Series:
    """相对强弱指标 (RSI)"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calc_portfolio_return(weights: np.array, returns: pd.DataFrame) -> pd.Series:
    """计算组合加权收益率序列"""
    # 简单的矩阵乘法
    return returns.dot(weights)

def calc_max_drawdown(series: pd.Series) -> float:
    """计算最大回撤"""
    cum_max = series.cummax()
    drawdown = (series - cum_max) / cum_max
    return drawdown.min()