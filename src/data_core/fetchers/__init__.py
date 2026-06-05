# src/data_core/fetchers/__init__.py
"""
Fetcher package exports.

Concrete fetchers are imported lazily so optional data-source dependencies
(akshare, yfinance, etc.) do not prevent the package from initializing.
"""

_LAZY_EXPORTS = {
    "CnStockFetcher": (".cn_stock", "CnStockFetcher"),
    "CurrencyFetcher": (".currency", "CurrencyFetcher"),
}

_ALIASES = {
    "FXFetcher": "CurrencyFetcher",
}


def __getattr__(name):
    import importlib

    target = _ALIASES.get(name, name)
    if target in _LAZY_EXPORTS:
        module_path, class_name = _LAZY_EXPORTS[target]
        module = importlib.import_module(module_path, package=__name__)
        value = getattr(module, class_name)
        globals()[target] = value
        globals()[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CnStockFetcher",
    "CurrencyFetcher",
    "FXFetcher",
]
