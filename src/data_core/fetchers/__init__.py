"""DEPRECATED — all fetcher code has been migrated to FinData/adapters/.

Use: from FinData.adapters.cn_stock import CnStockFetcher
     from FinData.adapters.forex import CurrencyFetcher
     from FinData.adapters import get_fetcher
"""

# Legacy re-exports for backward compat
from FinData.adapters.cn_stock import CnStockFetcher  # noqa: F401
from FinData.adapters.forex import CurrencyFetcher   # noqa: F401

__all__ = ["CnStockFetcher", "CurrencyFetcher"]
