# src/data_core/validator.py
import pandas as pd
import numpy as np

class DataValidator:
    @staticmethod
    def check_series(symbol, series):
        """
        检查单只资产数据质量 (鲁棒性增强版)
        """
        # 1. 基础判空
        if series is None:
            return False, "数据为None"
            
        # 2. 类型防御 (防止 DataFrame 混入导致报错)
        if isinstance(series, pd.DataFrame):
            # 如果是 DataFrame，尝试降维成 Series
            if series.shape[1] == 1:
                series = series.iloc[:, 0]
            else:
                return False, f"格式错误: 期望Series，收到DataFrame (shape={series.shape})"

        # 3. 内容判空
        if series.empty:
            return False, "数据为空(Empty)"
        
        # 4. 全NaN检查 (关键修正点)
        # .sum() == 0 或者 .count() == 0 也可以，但 isna().all() 语义最清晰
        if series.isna().all():
            return False, "全是空值(NaN)"
            
        # 5. 长度检查 (太短的数据无法计算统计量)
        if len(series) < 10:
            return False, f"数据太少 (只有{len(series)}行)"
            
        # 6. (可选) 停牌检查
        # 如果最近一年的价格完全没变过，可能是死股
        if series.nunique() <= 1:
             return False, "价格无波动(疑似停牌/死数据)"

        return True, "Pass"

    @staticmethod
    def check_alignment(df):
        """检查最终矩阵质量"""
        if df.empty:
            return False, "最终矩阵为空"
        
        # 检查缺失率
        # 某些资产可能因为假期导致大量空值
        missing_rate = df.isna().mean().max()
        if missing_rate > 0.5:
            return True, f"警告: 存在缺失率 > 50% 的资产，请检查对齐逻辑"
            
        return True, "Pass"