"""FinData Fetcher Department — data retrieval only. No validation, no storage."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time

@dataclass
class FetchResult:
    """Raw result from a data fetch operation."""
    symbol: str
    provider: str
    data: Any              # pd.DataFrame or similar — whatever the provider returned
    success: bool
    latency_ms: float
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

class FetcherProtocol:
    """Every fetcher must implement this. Fetch only — no validation, no storage."""
    def fetch(self, symbol: str, start_date: str, end_date: str, **kwargs) -> FetchResult:
        raise NotImplementedError


"""Fetcher registry — maps asset types to fetcher instances.

Fetch for supported types only. None = not yet implemented.
"""

from .us_equity import UsEquityFetcher
from .cn_stock import CnStockFetcher
from .cn_fund import CnFundFetcherAdapter
from .forex import CurrencyFetcher, ForexFetcher
from .bank_wmp import BankWmpFetcher

FETCHER_REGISTRY = {
    "us_equity": UsEquityFetcher(),
    "us_etf": UsEquityFetcher(),                   # US ETFs use same fetcher as US equities
    "cn_stock": CnStockFetcher(),
    "cn_stock_sh": CnStockFetcher(),
    "cn_stock_sz": CnStockFetcher(),
    "cn_fund": CnFundFetcherAdapter(),
    "cn_fund_open": CnFundFetcherAdapter(),
    "cn_fund_etf": CnFundFetcherAdapter(),
    "cn_fund_money": CnFundFetcherAdapter(),
    "cn_fund_qdii": CnFundFetcherAdapter(),        # QDII → same as cn_fund
    "cn_money_market_fund": CnFundFetcherAdapter(), # Money market → same as cn_fund
    "currency": ForexFetcher(),
    "forex": ForexFetcher(),
    "bank_wmp": BankWmpFetcher(),                  # Generic bank WMP entry
    "bank_wm_bosc": BankWmpFetcher(),
    "bank_wm_boc": BankWmpFetcher(),
    "bank_wm_icbc": BankWmpFetcher(),
    "crypto": None,                                # Not yet adapted
    "hk_equity": None,                             # Not yet adapted
}


def get_fetcher(asset_type: str):
    return FETCHER_REGISTRY.get(asset_type)
