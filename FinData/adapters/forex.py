"""Forex fetcher — thin adapter over akshare.currency_boc_sina (BOC Sina source)."""

from . import FetcherProtocol, FetchResult
import time
import pandas as pd


class ForexFetcher(FetcherProtocol):
    PROVIDER = "akshare-boc-sina"

    def fetch(self, symbol: str, start_date: str, end_date: str, **kwargs) -> FetchResult:
        t0 = time.time()
        try:
            import akshare as ak
            df = ak.currency_boc_sina(symbol=symbol)
            # Filter date range
            df["date"] = pd.to_datetime(df["date"])
            mask = (df["date"] >= pd.Timestamp(start_date)) & (df["date"] <= pd.Timestamp(end_date))
            df = df[mask]
            return FetchResult(symbol=symbol, provider=self.PROVIDER, data=df,
                               success=True, latency_ms=(time.time() - t0) * 1000)
        except Exception as e:
            return FetchResult(symbol=symbol, provider=self.PROVIDER, data=None,
                               success=False, latency_ms=(time.time() - t0) * 1000,
                               errors=[str(e)])
