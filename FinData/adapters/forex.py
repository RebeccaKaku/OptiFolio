"""Forex / currency fetchers.

Two paths:
- ForexFetcher: FinData pipeline fetcher (FetcherProtocol → FetchResult, akshare source)
- CurrencyFetcher: direct-use fetcher for valuation (returns pd.DataFrame, yfinance source)
"""

import time

import pandas as pd

from . import FetcherProtocol, FetchResult


# ── FinData pipeline fetcher ──────────────────────────────────────────────

class ForexFetcher(FetcherProtocol):
    PROVIDER = "akshare-boc-sina"

    def fetch(self, symbol: str, start_date: str, end_date: str, **kwargs) -> FetchResult:
        t0 = time.time()
        try:
            import akshare as ak

            df = ak.currency_boc_sina(symbol=symbol)
            df["date"] = pd.to_datetime(df["date"])
            mask = (df["date"] >= pd.Timestamp(start_date)) & (df["date"] <= pd.Timestamp(end_date))
            df = df[mask]
            return FetchResult(
                symbol=symbol, provider=self.PROVIDER, data=df,
                success=True, latency_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            return FetchResult(
                symbol=symbol, provider=self.PROVIDER, data=None,
                success=False, latency_ms=(time.time() - t0) * 1000,
                errors=[str(e)],
            )


# ── Direct-use currency fetcher (for valuation.py) ────────────────────────

class CurrencyFetcher:
    """FX rate fetcher using yfinance.

    Symbol format: "FROMTO" where FROM and TO are 3-letter codes.
    Example: "USDCNY" for USD → CNY rate.

    Returns DataFrame with OHLC columns; 'Close' = exchange rate.
    """

    _SYMBOL_MAP = {
        "USDCNY": "CNY=X", "CNYUSD": "CNYUSD=X",
        "USDEUR": "EUR=X", "EURUSD": "EURUSD=X",
        "USDJPY": "JPY=X", "JPYUSD": "JPYUSD=X",
        "USDGBP": "GBP=X", "GBPUSD": "GBPUSD=X",
        "USDCAD": "CAD=X", "CADUSD": "CADUSD=X",
        "USDAUD": "AUD=X", "AUDUSD": "AUDUSD=X",
        "USDCHF": "CHF=X", "CHFUSD": "CHFUSD=X",
        "EURGBP": "EURGBP=X", "GBPEUR": "GBPEUR=X",
        "EURJPY": "EURJPY=X", "JPYEUR": "JPYEUR=X",
        "GBPJPY": "GBPJPY=X", "JPYGBP": "JPYGBP=X",
    }

    def fetch(self, symbol: str, start_date: str, end_date: str,
              interval: str = "1d") -> pd.DataFrame:
        import yfinance as yf

        yf_symbol = self._get_yfinance_symbol(symbol)
        if yf_symbol is None:
            return pd.DataFrame()

        try:
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(
                start=start_date, end=end_date,
                interval=interval, auto_adjust=True,
            )
            if len(df) == 0:
                return pd.DataFrame()
            expected = ["Open", "High", "Low", "Close", "Volume"]
            for col in expected:
                if col not in df.columns:
                    df[col] = pd.NA
            return df[expected]
        except Exception:
            return pd.DataFrame()

    def get_realtime_rate(self, from_currency: str, to_currency: str) -> float:
        if from_currency == to_currency:
            return 1.0
        symbol = f"{from_currency}{to_currency}"
        try:
            df = self.fetch(symbol, start_date="2024-01-01", end_date="2024-12-31")
            if len(df) > 0:
                return float(df["Close"].iloc[-1])
        except Exception:
            pass
        inverse = f"{to_currency}{from_currency}"
        try:
            df = self.fetch(inverse, start_date="2024-01-01", end_date="2024-12-31")
            if len(df) > 0:
                return 1.0 / float(df["Close"].iloc[-1])
        except Exception:
            pass
        return 1.0

    def _get_yfinance_symbol(self, pair_symbol: str) -> str | None:
        if pair_symbol in self._SYMBOL_MAP:
            return self._SYMBOL_MAP[pair_symbol]
        if len(pair_symbol) == 6:
            return f"{pair_symbol}=X"
        return None

    @classmethod
    def get_supported_pairs(cls):
        return list(cls._SYMBOL_MAP.keys())
