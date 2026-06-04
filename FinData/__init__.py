"""FinData — unified financial data department.

Usage:
    from FinData import fd
    prices = fd.prices("AAPL", start="2024-01-01")  # fast, from local
    prices = fd.prices("AAPL", mode="live")           # trigger refresh first
"""

from __future__ import annotations


class _LazyStore:
    """Lazy proxy for CanonicalStore — avoids importing storage_dept at module level."""

    def __init__(self) -> None:
        self._store = None

    def _get(self):
        if self._store is None:
            from .storage_dept.store import CanonicalStore
            self._store = CanonicalStore()
        return self._store

    def __getattr__(self, name: str):
        return getattr(self._get(), name)


class FinData:
    """Unified data facade. Phase 1: storage only. Later phases add orchestrator/fetcher/serving."""

    def __init__(self) -> None:
        self._store = _LazyStore()

    def prices(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        mode: str = "fast",
    ):
        """Get price series for an asset.

        Args:
            symbol: Asset identifier (e.g. 'AAPL').
            start: Start date string (e.g. '2024-01-01').
            end: End date string.
            mode: 'fast' (cached only) or 'live' (refresh then return).

        Returns:
            Price series as a pandas Series, or None if unavailable.
        """
        if mode == "live":
            # Phase 1 stub: live mode just warns
            import warnings

            warnings.warn("Live mode not yet implemented — returning cached data")
        series = self._store.get_prices([symbol], start=start, end=end)
        if series.empty or symbol not in series.columns:
            return None
        return series[symbol]

    def ohlcv(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
    ):
        """Raw OHLCV DataFrame."""
        import pandas as pd

        result = self._store.get_prices([symbol], start=start, end=end)
        if result.empty or symbol not in result.columns:
            return None
        return pd.DataFrame(result[symbol])

    def panel(
        self,
        symbols: list[str],
        start: str | None = None,
        end: str | None = None,
    ):
        """Multi-asset price matrix (date x asset_id)."""
        return self._store.get_prices(symbols, start=start, end=end)

    def list_assets(self) -> list[str]:
        """Return all asset IDs in storage."""
        return self._store.list_assets()

    def missing_report(
        self,
        assets: list[str],
        start: str | None = None,
        end: str | None = None,
    ):
        """Return data completeness report per asset."""
        return self._store.missing_report(assets, start=start, end=end)


fd = FinData()
