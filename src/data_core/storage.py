# src/data_core/storage.py
import os
import pandas as pd

class DataStorage:
    def __init__(self, root_dir="data"):
        self.raw_dir = os.path.join(root_dir, "raw")
        self.processed_dir = os.path.join(root_dir, "processed")
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)
        
        # 检测是否支持Parquet
        self.supports_parquet = False
        try:
            import pyarrow
            self.supports_parquet = True
        except ImportError:
            print("    [Warning] pyarrow未安装，将使用CSV格式存储")

    def save_raw(self, symbol, data, frequency='daily'):
        """
        保存单只资产原始数据
        
        Args:
            symbol: 资产代码
            data: 可以是Series或DataFrame
            frequency: 数据频率 ('daily', 'minute', 'weekly', 'monthly')
        """
        if data is None or (hasattr(data, 'empty') and data.empty):
            return
        
        # 创建频率子目录
        freq_dir = os.path.join(self.raw_dir, frequency)
        os.makedirs(freq_dir, exist_ok=True)
        
        if self.supports_parquet:
            file_path = os.path.join(freq_dir, f"{symbol}.parquet")
            # 确保保存为DataFrame
            if isinstance(data, pd.Series):
                df = data.to_frame(name='Close')
            else:
                df = data.copy()
            
            # 保存元数据（频率信息）
            if 'frequency' not in df.attrs:
                df.attrs['frequency'] = frequency
                df.attrs['symbol'] = symbol
            
            df.to_parquet(file_path, compression='snappy')
            print(f"    [仓储] 保存 {symbol} {frequency} 数据到 {file_path}")
        else:
            file_path = os.path.join(freq_dir, f"{symbol}.csv")
            data.to_csv(file_path)
            print(f"    [仓储] 保存 {symbol} {frequency} 数据到 {file_path}")

    def save_processed(self, df):
        """保存清洗后的总表"""
        if df.empty:
            return
            
        if self.supports_parquet:
            file_path = os.path.join(self.processed_dir, "market_matrix.parquet")
            df.to_parquet(file_path, compression='snappy')
            print(f"    [仓储] 数据已归档至 {file_path} (Parquet格式)")
        else:
            file_path = os.path.join(self.processed_dir, "market_matrix.csv")
            df.to_csv(file_path)
            print(f"    [仓储] 数据已归档至 {file_path} (CSV格式)")
    
    def load_processed(self):
        """加载处理后的数据矩阵"""
        if self.supports_parquet:
            file_path = os.path.join(self.processed_dir, "market_matrix.parquet")
            if os.path.exists(file_path):
                return pd.read_parquet(file_path)
        else:
            file_path = os.path.join(self.processed_dir, "market_matrix.csv")
            if os.path.exists(file_path):
                return pd.read_csv(file_path, index_col=0, parse_dates=True)
        return pd.DataFrame()
    
    def load_raw(self, symbol, frequency='daily'):
        """
        加载单只资产原始数据
        
        Args:
            symbol: 资产代码
            frequency: 数据频率 ('daily', 'minute', 'weekly', 'monthly')
            
        Returns:
            pandas.DataFrame: 原始数据DataFrame
        """
        freq_dir = os.path.join(self.raw_dir, frequency)
        
        if self.supports_parquet:
            file_path = os.path.join(freq_dir, f"{symbol}.parquet")
            if os.path.exists(file_path):
                try:
                    df = pd.read_parquet(file_path)
                    return df
                except Exception as e:
                    print(f"    [Warning] 加载 {symbol} {frequency} 数据失败: {e}")
                    return pd.DataFrame()
        else:
            file_path = os.path.join(freq_dir, f"{symbol}.csv")
            if os.path.exists(file_path):
                try:
                    return pd.read_csv(file_path, index_col=0, parse_dates=True)
                except Exception as e:
                    print(f"    [Warning] 加载 {symbol} {frequency} 数据失败: {e}")
                    return pd.DataFrame()
        
        # 如果找不到指定频率的数据，尝试查找任何频率的数据
        if frequency != 'daily':
            return self.load_raw(symbol, 'daily')
        
        return pd.DataFrame()
    
    def get_available_frequencies(self, symbol):
        """
        获取某资产的可用数据频率
        
        Args:
            symbol: 资产代码
            
        Returns:
            list: 可用的频率列表
        """
        available = []
        frequencies = ['daily', 'minute', 'weekly', 'monthly']
        
        for freq in frequencies:
            freq_dir = os.path.join(self.raw_dir, freq)
            if self.supports_parquet:
                file_path = os.path.join(freq_dir, f"{symbol}.parquet")
            else:
                file_path = os.path.join(freq_dir, f"{symbol}.csv")
            
            if os.path.exists(file_path):
                available.append(freq)
        
        return available
    
    def save_raw_with_metadata(self, symbol, df, metadata=None):
        """
        保存原始数据并附带元数据
        
        Args:
            symbol: 资产代码
            df: 数据DataFrame
            metadata: 元数据字典
        """
        if df is None or df.empty:
            return
        
        # 默认使用daily频率
        frequency = 'daily'
        if metadata and 'frequency' in metadata:
            frequency = metadata['frequency']
        
        # 保存元数据到DataFrame属性
        if metadata:
            for key, value in metadata.items():
                df.attrs[key] = value
        
        self.save_raw(symbol, df, frequency)
