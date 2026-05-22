import time

import pandas as pd

from src.data_core.interface import BaseFetcher
from src.data_core.fetchers.factory import get_factory
from src.data_core.storage import DataStorage
from src.data_loader import DataLoader


class _RecordingFetcher(BaseFetcher):
    calls = []
    base_price = 100.0

    def fetch(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.__class__.calls.append((symbol, time.perf_counter()))
        dates = pd.date_range(start=start_date, end=end_date, freq="D")
        prices = [self.base_price + idx for idx in range(len(dates))]
        return pd.DataFrame({"Close": prices}, index=dates)


class _FakeUSFetcher(_RecordingFetcher):
    calls = []
    base_price = 100.0


class _FakeCNFetcher(_RecordingFetcher):
    calls = []
    base_price = 50.0


def test_data_loader_fetches_different_provider_groups_concurrently(tmp_path):
    factory = get_factory()
    factory.register("test_us_concurrent", _FakeUSFetcher)
    factory.register("test_cn_concurrent", _FakeCNFetcher)
    factory.clear_cache()
    _FakeUSFetcher.calls = []
    _FakeCNFetcher.calls = []

    config = {
        "universe": {
            "assets": [
                {"symbol": "US1", "type": "test_us_concurrent"},
                {"symbol": "US2", "type": "test_us_concurrent"},
                {"symbol": "CN1", "type": "test_cn_concurrent"},
            ]
        },
        "parameters": {
            "start_date": "2024-01-01",
            "end_date": "2024-01-12",
        },
    }
    loader = DataLoader(config)
    loader.storage = DataStorage(tmp_path)

    start = time.perf_counter()
    result = loader.fetch_all_data()
    elapsed = time.perf_counter() - start

    assert list(result.columns) == ["US1", "US2", "CN1"]
    assert result.shape == (12, 3)
    assert elapsed < 1.2
    assert len(_FakeUSFetcher.calls) == 2
    assert len(_FakeCNFetcher.calls) == 1
    assert _FakeUSFetcher.calls[1][1] - _FakeUSFetcher.calls[0][1] >= 0.45
    assert _FakeCNFetcher.calls[0][1] - _FakeUSFetcher.calls[0][1] < 0.45
