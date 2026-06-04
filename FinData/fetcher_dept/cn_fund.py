"""CN Fund fetcher — thin adapter delegating to fetchers.cn_fund.CnFundFetcher (async)."""

from . import FetcherProtocol, FetchResult
import time
import asyncio


class CnFundFetcherAdapter(FetcherProtocol):
    PROVIDER = "akshare-cn-fund"

    def __init__(self):
        from fetchers.cn_fund import CnFundFetcher
        self._fetcher = CnFundFetcher()

    def fetch(self, symbol: str, start_date: str, end_date: str, **kwargs) -> FetchResult:
        t0 = time.time()
        try:
            df = asyncio.run(self._fetcher.fetch(symbol, start_date, end_date, **kwargs))
            return FetchResult(symbol=symbol, provider=self.PROVIDER, data=df,
                               success=True, latency_ms=(time.time() - t0) * 1000)
        except Exception as e:
            return FetchResult(symbol=symbol, provider=self.PROVIDER, data=None,
                               success=False, latency_ms=(time.time() - t0) * 1000,
                               errors=[str(e)])
