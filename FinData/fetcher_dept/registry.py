"""Fetcher registry — maps asset types to fetcher instances.

Fetch for supported types only. None = not yet implemented.
"""

from .us_equity import UsEquityFetcher
from .cn_stock import CnStockFetcherAdapter
from .cn_fund import CnFundFetcherAdapter
from .forex import ForexFetcher
from .bank_wmp import BankWmpFetcher

FETCHER_REGISTRY = {
    "us_equity": UsEquityFetcher(),
    "us_etf": UsEquityFetcher(),                   # US ETFs use same fetcher as US equities
    "cn_stock": CnStockFetcherAdapter(),
    "cn_stock_sh": CnStockFetcherAdapter(),
    "cn_stock_sz": CnStockFetcherAdapter(),
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
