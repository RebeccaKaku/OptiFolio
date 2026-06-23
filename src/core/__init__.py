"""
核心业务逻辑模块。

Import directly from submodules:
    from src.core.valuation import ValuationEngine
    from src.core.calendars import ExchangeCalendar, get_calendar
    from src.core.portfolio_book_db import PortfolioBookDatabase
"""

__all__ = [
    "CorporateActionProcessor",
    "FeeProcessor",
]

_LAZY = {
    "CorporateActionProcessor": ".corporate_actions",
    "FeeProcessor": ".fees",
}


def __getattr__(name: str):
    if name in _LAZY:
        import importlib
        mod = importlib.import_module(_LAZY[name], __package__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
