"""Fetcher registry — maps asset types to fetcher instances."""

from .us_equity import UsEquityFetcher
from .cn_stock import CnStockFetcherAdapter
from .cn_fund import CnFundFetcherAdapter
from .forex import ForexFetcher
from .bank_wmp import BankWmpFetcher

FETCHER_REGISTRY = {
    "us_equity": UsEquityFetcher(),
    "cn_stock": CnStockFetcherAdapter(),
    "cn_stock_sh": CnStockFetcherAdapter(),
    "cn_stock_sz": CnStockFetcherAdapter(),
    "cn_fund": CnFundFetcherAdapter(),
    "cn_fund_open": CnFundFetcherAdapter(),
    "cn_fund_etf": CnFundFetcherAdapter(),
    "cn_fund_money": CnFundFetcherAdapter(),
    "currency": ForexFetcher(),
    "forex": ForexFetcher(),
    "bank_wm_bosc": BankWmpFetcher(),
    "bank_wm_boc": BankWmpFetcher(),
    "bank_wm_icbc": BankWmpFetcher(),
    "crypto": None,  # Not yet adapted
}


def get_fetcher(asset_type: str):
    return FETCHER_REGISTRY.get(asset_type)
