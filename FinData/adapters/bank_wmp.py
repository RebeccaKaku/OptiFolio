"""Bank WMP fetcher — unified adapter dispatching BOC / ICBC / BOSC by symbol pattern."""

import re
import time
import asyncio
from . import FetcherProtocol, FetchResult


class BankWmpFetcher(FetcherProtocol):
    """Unified adapter for BOC / BOSC / ICBC wealth management products.

    Classification rules (checked in order):
    - ICBC: 8‑char alphanumeric starting with digits (e.g. 23GS8125)
    - BOSC: short letter prefix + digits + letter + digits (e.g. WPXK24M1203A)
    - BOC:  uppercase alpha+numeric, 10+ chars (e.g. AMHQLXTTUSD01B)
    """

    PROVIDER = "bank-wmp"

    # ── classification ──────────────────────────────────────────────
    _RE_ICBC = re.compile(r"^\d{2}[A-Z0-9]{6}$")                      # 2 digits + 6 alnum = 8 chars
    _RE_BOSC = re.compile(r"^[A-Z]{1,6}\d+[A-Z0-9]*$")                # letter prefix + digits (covers GKF/J/W/MPJF/...)
    _RE_BOC  = re.compile(r"^[A-Z][A-Z0-9]{9,}$")                     # uppercase, 10+ chars

    @staticmethod
    def _classify(symbol: str) -> str:
        if BankWmpFetcher._RE_ICBC.match(symbol):
            return "icbc"
        if BankWmpFetcher._RE_BOSC.match(symbol):
            return "bosc"
        if BankWmpFetcher._RE_BOC.match(symbol):
            return "boc"
        return ""

    # ── lazy sub-fetchers ───────────────────────────────────────────
    def __init__(self):
        self._boc = None
        self._icbc = None
        self._bosc = None

    def _get_boc(self):
        if self._boc is None:
            from .boc_wm import BocFetcher
            self._boc = BocFetcher()
        return self._boc

    def _get_icbc(self):
        if self._icbc is None:
            from .icbc import IcbcFetcher
            self._icbc = IcbcFetcher()
        return self._icbc

    def _get_bosc(self):
        if self._bosc is None:
            from .bosc import BoscFetcher
            self._bosc = BoscFetcher()
        return self._bosc

    # ── fetch ───────────────────────────────────────────────────────
    def fetch(self, symbol: str, start_date: str, end_date: str, **kwargs) -> FetchResult:
        t0 = time.time()
        kind = kwargs.pop("kind", None) or self._classify(symbol)

        try:
            if kind == "boc":
                df = asyncio.run(self._get_boc().fetch(symbol, start_date, end_date, **kwargs))
            elif kind == "icbc":
                df = asyncio.run(self._get_icbc().fetch(symbol, start_date, end_date, **kwargs))
            elif kind == "bosc":
                df = asyncio.run(self._get_bosc().fetch(symbol, start_date, end_date, **kwargs))
            else:
                return FetchResult(
                    symbol=symbol, provider=self.PROVIDER, data=None,
                    success=False, latency_ms=(time.time() - t0) * 1000,
                    errors=[f"Unknown bank WMP symbol pattern: {symbol}"],
                )
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
