"""FinData — unified financial data department.

Usage:
    from FinData import fd
    prices = fd.prices("AAPL", start="2024-01-01")  # fast, from local
    prices = fd.prices("AAPL", mode="live")           # trigger refresh first

The ``fd`` singleton is lazily created on first access.  Importing the
FinData package no longer triggers the full dependency chain
(DataProvider → CanonicalStore → MarketDataRepository).
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
    """Unified data facade. Delegates all requests to DataProvider.

    ``DataProvider`` is created lazily on first method call so that
    importing ``FinData`` (or accessing ``fd``) does not trigger
    the Cascade of imports through ``CanonicalStore`` →
    ``MarketDataRepository`` → ``PROJECT_ROOT`` → ``src.core``.
    """

    def __init__(self) -> None:
        self._provider: "DataProvider | None" = None

    # ── provider accessor (lazy init) ──

    @property
    def _provider_ref(self) -> "DataProvider":
        """Return the DataProvider, creating it on first access."""
        if self.__dict__.get("_provider") is None:
            self._provider = DataProvider()
        return self._provider

    # ── store injection (backward-compatible, for tests) ──

    @property
    def _store(self):
        return self._provider_ref._store

    @_store.setter
    def _store(self, value):
        self._provider_ref._store = value

    # ── delegated methods ──

    def prices(self, symbol, start=None, end=None, mode="fast"):
        return self._provider_ref.prices(symbol, start=start, end=end, mode=mode)

    def ohlcv(self, symbol, start=None, end=None, mode="fast"):
        return self._provider_ref.ohlcv(symbol, start=start, end=end, mode=mode)

    def panel(self, symbols, start=None, end=None, mode="fast"):
        return self._provider_ref.panel(symbols, start=start, end=end, mode=mode)

    def returns(self, symbol, start=None, end=None, frequency="D"):
        return self._provider_ref.returns(symbol, start=start, end=end, frequency=frequency)

    def metrics(self, symbol, metric="all", start=None, end=None, risk_free_rate=0.0):
        return self._provider_ref.metrics(symbol, metric=metric, start=start, end=end, risk_free_rate=risk_free_rate)

    def rate(self, rate_id="1y_cn"):
        return self._provider_ref.rate(rate_id)

    def fx_rate(self, from_cur, to_cur, date_str=None, mode="fast"):
        return self._provider_ref.fx_rate(from_cur, to_cur, date_str=date_str, mode=mode)

    def export(self, symbol, start=None, end=None, format="csv"):
        return self._provider_ref.export(symbol, start=start, end=end, format=format)

    def observations(self, series_ids, start=None, end=None, known_at=None):
        return self._provider_ref.observations(series_ids, start=start, end=end, known_at=known_at)

    def latest_observation(self, series_id, as_of=None, known_at=None):
        return self._provider_ref.latest_observation(series_id, as_of=as_of, known_at=known_at)

    def observation_series(self):
        return self._provider_ref.observation_series()

    def observation_coverage(self, series_ids=None, expected_stale_days=None, as_of=None):
        return self._provider_ref.observation_coverage(
            series_ids=series_ids,
            expected_stale_days=expected_stale_days,
            as_of=as_of,
        )

    def list_assets(self):
        return self._provider_ref._store.list_assets()

    def missing_report(self, assets, start=None, end=None):
        return self._provider_ref._store.missing_report(assets, start=start, end=end)


# Lazy singleton: ``fd`` is created on first access.
# Module-level ``fd = FinData()`` is NOT used here — that would eagerly
# import DataProvider → CanonicalStore → MarketDataRepository,
# creating a circular dependency chain with ``src.core``.
_fd: "FinData | None" = None


def __getattr__(name: str) -> "FinData":
    if name == "fd":
        global _fd
        if _fd is None:
            _fd = FinData()
        return _fd
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
