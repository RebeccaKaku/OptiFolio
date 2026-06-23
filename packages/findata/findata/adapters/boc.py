"""BOC adapter — re-exports from boc_wm and boc_structured for backward compat."""
from .boc_wm import BocFetcher  # wealth management
from .boc_structured import BocStructuredDepositFetcher

__all__ = ["BocFetcher", "BocStructuredDepositFetcher"]
