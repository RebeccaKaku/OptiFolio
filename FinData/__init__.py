"""FinData — unified financial data department.

Usage:
    from FinData import fd
    prices = fd.prices("AAPL", start="2024-01-01")  # fast, from local
    prices = fd.prices("AAPL", mode="live")           # trigger refresh first
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path so that top-level packages like
# ``fetchers`` are importable regardless of the entry-point directory.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from .serving.provider import DataProvider


class FinData:
    """Unified data facade. Delegates all requests to DataProvider."""

    def __init__(self) -> None:
        self._provider = DataProvider()

    @property
    def _store(self):
        """Backward-compatible store accessor — delegates to provider."""
        return self._provider._store

    @_store.setter
    def _store(self, value):
        self._provider._store = value

    def prices(self, symbol, start=None, end=None, mode="fast"):
        return self._provider.prices(symbol, start=start, end=end, mode=mode)

    def ohlcv(self, symbol, start=None, end=None, mode="fast"):
        return self._provider.ohlcv(symbol, start=start, end=end, mode=mode)

    def panel(self, symbols, start=None, end=None, mode="fast"):
        return self._provider.panel(symbols, start=start, end=end, mode=mode)

    def returns(self, symbol, start=None, end=None, frequency="D"):
        return self._provider.returns(symbol, start=start, end=end, frequency=frequency)

    def metrics(self, symbol, metric="all", start=None, end=None, risk_free_rate=0.0):
        return self._provider.metrics(symbol, metric=metric, start=start, end=end, risk_free_rate=risk_free_rate)

    def rate(self, rate_id="1y_cn"):
        return self._provider.rate(rate_id)

    def fx_rate(self, from_cur, to_cur, date_str=None):
        return self._provider.fx_rate(from_cur, to_cur, date_str=date_str)

    def export(self, symbol, start=None, end=None, format="csv"):
        return self._provider.export(symbol, start=start, end=end, format=format)

    def list_assets(self):
        return self._provider._store.list_assets()

    def missing_report(self, assets, start=None, end=None):
        return self._provider._store.missing_report(assets, start=start, end=end)


fd = FinData()
