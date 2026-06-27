"""Bank WMP fetcher — unified adapter dispatching BOC / ICBC / BOSC by symbol pattern."""

import re
import time
import asyncio
from typing import Optional, Dict, Any

from optifolio_contracts.identifiers import normalize_instrument_id

from . import FetcherProtocol, FetchResult, _run_async


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
    _RE_BOC  = re.compile(r"^[A-Z]{5,}[A-Z0-9]{5,}$")                 # 5+ leading letters + 5+ alnum = 10+ total, digits delayed

    @staticmethod
    def _bare_code(symbol: str) -> str:
        return symbol.split(".")[-1].upper()

    @staticmethod
    def _classify(symbol: str) -> str:
        symbol = BankWmpFetcher._bare_code(symbol)
        if BankWmpFetcher._RE_ICBC.match(symbol):
            return "icbc"
        if BankWmpFetcher._RE_BOC.match(symbol):
            return "boc"
        if BankWmpFetcher._RE_BOSC.match(symbol):
            return "bosc"
        return ""

    # ── lazy sub-fetchers ───────────────────────────────────────────
    def __init__(self):
        self._boc = None
        self._icbc = None
        self._bosc = None
        self._boc_structured = None

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

    def _get_boc_structured(self):
        if self._boc_structured is None:
            from .boc_structured import BocStructuredDepositFetcher
            self._boc_structured = BocStructuredDepositFetcher()
        return self._boc_structured

    def get_metadata(self, symbol: str) -> Optional[Dict[str, Any]]:
        code = self._bare_code(symbol)
        kind = self._classify(code)
        if kind == "boc":
            # Try structured first, then wealth management
            if code.startswith(("GRSDR", "CSDPY")):
                return self._get_boc_structured().get_metadata(code)
            return self._get_boc().get_metadata(code)
        elif kind == "icbc":
            return self._get_icbc().get_metadata(code)
        elif kind == "bosc":
            return self._get_bosc().get_metadata(code)
        return None

    # ── fetch ───────────────────────────────────────────────────────
    def fetch(self, symbol: str, start_date: str, end_date: str, **kwargs) -> FetchResult:
        t0 = time.time()
        code = self._bare_code(symbol)
        try:
            canonical = normalize_instrument_id(code, asset_type="bank_wmp")
        except Exception:
            canonical = symbol
        kind = kwargs.pop("kind", None) or self._classify(code)

        try:
            if kind == "boc":
                df = _run_async(self._get_boc().fetch(code, start_date, end_date, **kwargs))
            elif kind == "icbc":
                df = _run_async(self._get_icbc().fetch(code, start_date, end_date, **kwargs))
            elif kind == "bosc":
                df = _run_async(self._get_bosc().fetch(code, start_date, end_date, **kwargs))
            else:
                return FetchResult(
                    symbol=canonical, provider=self.PROVIDER, data=None,
                    success=False, latency_ms=(time.time() - t0) * 1000,
                    errors=[f"Unknown bank WMP symbol pattern: {symbol}"],
                )
            return FetchResult(
                symbol=canonical, provider=self.PROVIDER, data=df,
                success=True, latency_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            return FetchResult(
                symbol=canonical, provider=self.PROVIDER, data=None,
                success=False, latency_ms=(time.time() - t0) * 1000,
                errors=[str(e)],
            )
