"""findata — local-first financial data layer.

This package MUST NOT import from src/. It MAY import from optifolio_contracts.

Public API:
    from findata import fd, FinDataConfig

    prices = fd.prices("AAPL", start="2024-01-01")
    ohlcv = fd.ohlcv("AAPL")
    panel = fd.panel(["AAPL", "QQQ"])
    returns = fd.returns("AAPL")
    metrics = fd.metrics("AAPL", "all")
    rate = fd.rate("1y_cn")
    fx = fd.fx_rate("USD", "CNY", mode="live")
    observations = fd.observations([...])

Internal modules (``findata.store.*``, ``findata.orchestration.*``,
``findata.adapters.*``) are available for advanced users but are not part of
 the stable public facade.
"""

from __future__ import annotations

from findata.config import FinDataConfig, get_default_config


#: Methods exposed through the ``fd`` singleton facade.
_PUBLIC_FACADE_METHODS = frozenset({
    "prices",
    "ohlcv",
    "panel",
    "returns",
    "metrics",
    "rate",
    "fx_rate",
    "observations",
    "latest_observation",
    "observation_series",
    "observation_coverage",
    "export",
})


class FinData:
    """Unified public data facade.

    Delegates data requests to ``findata.serving.DataProvider``.  The
    provider is created lazily on first access so that ``import findata``
    remains lightweight.

    Only the methods listed in ``_PUBLIC_FACADE_METHODS`` are delegated
    through ``__getattr__``.  Names starting with an underscore are never
    delegated, which keeps the facade surface small and prevents accidental
    reliance on implementation details.
    """

    def __init__(self) -> None:
        self._provider = None

    @property
    def _provider_ref(self):
        if self._provider is None:
            from findata.serving.provider import DataProvider

            self._provider = DataProvider()
        return self._provider

    @property
    def _store(self):
        """Internal injection point for tests and advanced callers."""
        return self._provider_ref._store

    @_store.setter
    def _store(self, value):
        self._provider_ref._store = value

    def list_assets(self):
        """List assets currently stored in the canonical store."""
        return self._provider_ref._store.list_assets()

    def missing_report(self, asset_ids):
        """Return a missing-data report for the requested assets."""
        return self._provider_ref._store.missing_report(asset_ids)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(f"'FinData' object has no attribute {name!r}")
        if name not in _PUBLIC_FACADE_METHODS:
            raise AttributeError(
                f"'{name}' is not part of the findata public facade. "
                f"Use the underlying DataProvider directly if you need it."
            )
        return getattr(self._provider_ref, name)

    def __dir__(self):
        return sorted(
            {"list_assets", "missing_report"} | set(_PUBLIC_FACADE_METHODS)
        )


#: Lazy singleton used by the rest of the application.
fd: FinData = FinData()

__all__ = ["FinData", "fd", "FinDataConfig", "get_default_config"]
