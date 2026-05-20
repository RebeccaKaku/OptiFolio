# 文件路径: src/data_core/interface.py
from abc import ABC, abstractmethod
import pandas as pd

class BaseFetcher(ABC):
    """所有数据抓取器的基类"""
    @abstractmethod
    def fetch(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        pass