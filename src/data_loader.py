# src/data_loader.py
import pandas as pd
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from src.data_core.fetchers import get_factory, get_fetcher
from src.data_core.validator import DataValidator
from src.data_core.storage import DataStorage
from src.data_core.processor import DataProcessor
from src.utils import update_asset_names_in_config

class DataLoader:
    def __init__(self, config, processor_strategy="common_start"):
        self.assets = config['universe']['assets']
        self.start_date = config['parameters']['start_date']
        self.end_date = config['parameters']['end_date']
        
        # 使用工厂模式获取Fetcher
        self.factory = get_factory()
        
        # 初始化其他组件
        self.validator = DataValidator()
        self.storage = DataStorage()
        self.processor = DataProcessor(strategy=processor_strategy)
        
        # 显示支持的资产类型
        supported_types = self.factory.get_supported_asset_types()
        print(f"    [Loader] 支持的资产类型: {supported_types}")

    def fetch_all_data(self):
        """
        指挥官流程：采购 -> 质检 -> 入库 -> 加工 -> 出库
        """
        print(f">>> [System] 启动分布式数据采集流水线...")
        print(f"    [Loader] 使用工厂模式管理数据源")
        
        raw_data_buffer = {}
        
        # 共享的请求限流器状态
        rate_limit_lock = threading.Lock()
        last_request_time = [0.0]

        def process_asset(asset):
            symbol = asset['symbol']
            asset_type = asset['type']
            name = asset.get('name', symbol)
            currency = asset.get('currency', 'USD')  # 默认为USD
            
            print(f"    [采购] 处理 {name} ({symbol}, {asset_type}, {currency})...")
            
            # --- 1. 采购 (Fetching) ---
            data = None
            fetcher = self.factory.get_fetcher_for_asset(asset)
            
            if fetcher:
                try:
                    # 防封控 - 保证每次请求之间至少有0.5秒间隔
                    with rate_limit_lock:
                        now = time.time()
                        time_since_last = now - last_request_time[0]
                        if time_since_last < 0.5:
                            time.sleep(0.5 - time_since_last)
                        last_request_time[0] = time.time()

                    data = fetcher.fetch(symbol, self.start_date, self.end_date)
                    if data is not None and not data.empty:
                        print(f"        [成功] 获取到 {len(data)} 行数据")
                    else:
                        print(f"        [失败] 未获取到数据")
                except Exception as e:
                    print(f"        [异常] {type(e).__name__}: {e}")
            else:
                print(f"        [错误] 无法获取 {asset_type} 类型的Fetcher")
                
            # --- 2. 质检 (Validation) ---
            # 从DataFrame提取Close价格作为Series
            series = None
            if isinstance(data, pd.DataFrame) and not data.empty:
                # 获取收盘价列，优先使用'Close'，如果没有则使用第一列
                if 'Close' in data.columns:
                    series = data['Close']
                elif 'close' in data.columns:
                    series = data['close']
                elif len(data.columns) > 0:
                    series = data.iloc[:, 0]
                else:
                    series = pd.Series(dtype=float)
                series.name = symbol
            elif isinstance(data, pd.Series) and not data.empty:
                series = data
                series.name = symbol
                
            is_valid, msg = self.validator.check_series(symbol, series)
            if not is_valid:
                print(f"        [提示] 采购失败或数据无效 ({msg})，尝试从本地仓储加载...")
                local_df = self.storage.load_raw(symbol, frequency='daily')
                if local_df is not None and not local_df.empty:
                    if 'Close' in local_df.columns:
                        series = local_df['Close']
                    elif 'close' in local_df.columns:
                        series = local_df['close']
                    elif len(local_df.columns) > 0:
                        series = local_df.iloc[:, 0]
                    else:
                        series = pd.Series(dtype=float)
                    series.name = symbol
                    
                    is_valid, msg = self.validator.check_series(symbol, series)
                    if is_valid:
                        print(f"        [成功-本地] 从本地仓储成功加载历史数据 ({len(series)}行)")

            result = None
            if is_valid:
                print(f"        [√] 数据有效 ({len(series)}行)")
                
                # --- 3. 入库 (Storage) ---
                # 去重
                series = series[~series.index.duplicated(keep='first')]
                
                # 保存原始数据，默认频率为daily
                self.storage.save_raw(symbol, series, frequency='daily')
                result = (symbol, series)
            else:
                print(f"        [×] 废弃 ({msg})")

            return result

        with ThreadPoolExecutor(max_workers=min(10, len(self.assets) if self.assets else 1)) as executor:
            results = list(executor.map(process_asset, self.assets))

        for res in results:
            if res:
                symbol, series = res
                raw_data_buffer[symbol] = series

        # --- 4. 加工 (Processing) ---
        print(f"    [加工] 使用策略: {self.processor.strategy}")
        final_df = self.processor.align_and_clean(raw_data_buffer, self.start_date, self.end_date)
        
        # --- 5. 最终质检 ---
        ok, matrix_msg = self.validator.check_alignment(final_df)
        print(f"    [报告] {matrix_msg}")
        
        # 显示对齐结果统计
        if not final_df.empty:
            n_assets = len(final_df.columns)
            n_days = len(final_df)
            missing_ratio = final_df.isna().sum().sum() / (n_assets * n_days)
            print(f"    [统计] 对齐后: {n_assets} 个资产, {n_days} 天")
            if missing_ratio > 0:
                print(f"    [警告] 缺失值比例: {missing_ratio:.2%}")
        
        # --- 6. 归档成品 ---
        if not final_df.empty:
            self.storage.save_processed(final_df)
            print(f"    [归档] 已保存到 data/processed/market_matrix.parquet")
            
        return final_df
    
    def set_processor_strategy(self, strategy):
        """
        设置数据处理器策略。
        
        Args:
            strategy: "common_start"|"pairwise"|"raw"
        """
        self.processor = DataProcessor(strategy=strategy)
        print(f"    [Loader] 已切换处理器策略为: {strategy}")
        
    def get_supported_asset_types(self):
        """
        获取当前支持的资产类型。
        
        Returns:
            支持的资产类型列表
        """
        return self.factory.get_supported_asset_types()
    
    def register_custom_fetcher(self, asset_type, fetcher_class):
        """
        注册自定义Fetcher类。
        
        Args:
            asset_type: 资产类型
            fetcher_class: Fetcher类
        """
        self.factory.register(asset_type, fetcher_class)
        print(f"    [Loader] 已注册自定义Fetcher: {asset_type} -> {fetcher_class.__name__}")
