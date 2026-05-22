import pytest
import pandas as pd
from src.data_loader import DataLoader
from src.data_core.interface import BaseFetcher
from src.data_core.fetchers.factory import get_factory
import time

class FakeSequentialLoader(DataLoader):
    def fetch_all_data(self):
        raw_data_buffer = {}
        for asset in self.assets:
            symbol = asset['symbol']
            asset_type = asset['type']
            data = None
            fetcher = self.factory.get_fetcher_for_asset(asset)
            if fetcher:
                try:
                    data = fetcher.fetch(symbol, self.start_date, self.end_date)
                except Exception:
                    pass

            series = None
            if isinstance(data, pd.DataFrame) and not data.empty:
                series = data['Close'] if 'Close' in data.columns else data.iloc[:, 0]
                series.name = symbol

            is_valid, _ = self.validator.check_series(symbol, series)
            if not is_valid:
                local_df = self.storage.load_raw(symbol, frequency='daily')
                if local_df is not None and not local_df.empty:
                    series = local_df['Close'] if 'Close' in local_df.columns else local_df.iloc[:, 0]
                    series.name = symbol
                is_valid, _ = self.validator.check_series(symbol, series)

            if is_valid:
                series = series[~series.index.duplicated(keep='first')]
                raw_data_buffer[symbol] = series

        final_df = self.processor.align_and_clean(raw_data_buffer, self.start_date, self.end_date)
        return final_df

class FakeUSFetcher(BaseFetcher):
    def fetch(self, symbol, start_date, end_date):
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        return pd.DataFrame({'Close': [100.0] * len(dates)}, index=dates)

class FakeCNFetcher(BaseFetcher):
    def fetch(self, symbol, start_date, end_date):
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        return pd.DataFrame({'Close': [50.0] * len(dates)}, index=dates)

def test_concurrent_matches_sequential():
    factory = get_factory()
    factory.register('fake_us', FakeUSFetcher)
    factory.register('fake_cn', FakeCNFetcher)

    config = {
        'universe': {
            'assets': [
                {'symbol': 'US1', 'type': 'fake_us'},
                {'symbol': 'US2', 'type': 'fake_us'},
                {'symbol': 'CN1', 'type': 'fake_cn'},
            ]
        },
        'parameters': {
            'start_date': '2023-01-01',
            'end_date': '2023-01-05'
        }
    }

    loader_concurrent = DataLoader(config)
    loader_sequential = FakeSequentialLoader(config)

    start1 = time.time()
    df_concurrent = loader_concurrent.fetch_all_data()
    end1 = time.time()

    df_sequential = loader_sequential.fetch_all_data()

    pd.testing.assert_frame_equal(df_concurrent, df_sequential)
    print(f"Concurrent loaded in {end1 - start1:.2f}s")
