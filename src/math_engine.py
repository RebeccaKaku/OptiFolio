import pandas as pd
import numpy as np

class MathEngine:
    @staticmethod
    def get_stats(returns):
        """
        计算基础统计量
        """
        mu = returns.mean() * 252  # 年化收益
        sigma = returns.cov() * 252 # 年化协方差
        
        return {
            'mu': mu,
            'sigma': sigma
        }

"""
数学引擎 - 只负责纯粹的数学和金融指标计算。
输入数据应当是已经经过 Processor 对齐和清洗过的。
"""

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