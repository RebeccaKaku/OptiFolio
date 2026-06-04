"""CN Stock fetcher — thin adapter delegating to src.data_core.fetchers.cn_stock.CnStockFetcher."""

from . import FetcherProtocol, FetchResult
import time


class CnStockFetcherAdapter(FetcherProtocol):
    PROVIDER = "akshare-cn-stock"

    def __init__(self):
        from src.data_core.fetchers.cn_stock import CnStockFetcher
        self._fetcher = CnStockFetcher()

    def fetch(self, symbol: str, start_date: str, end_date: str, **kwargs) -> FetchResult:
        t0 = time.time()
        try:
            df = self._fetcher.fetch(symbol, start_date, end_date, **kwargs)
            return FetchResult(symbol=symbol, provider=self.PROVIDER, data=df,
                               success=True, latency_ms=(time.time() - t0) * 1000)
        except Exception as e:
            return FetchResult(symbol=symbol, provider=self.PROVIDER, data=None,
                               success=False, latency_ms=(time.time() - t0) * 1000,
                               errors=[str(e)])
