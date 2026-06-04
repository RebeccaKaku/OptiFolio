"""
Registry Adapter - Mapping between legacy asset types and namespaced prefixes.
"""

from typing import Dict, Optional

# Mapping from internal asset_type to namespaced prefix
TYPE_TO_PREFIX = {
    'us_equity': 'US_EQ',
    'cn_stock': 'CN_STOCK',
    'cn_stock_sh': 'CN_STOCK',
    'cn_stock_sz': 'CN_STOCK',
    'cn_fund': 'CN_FUND',
    'cn_fund_open': 'CN_FUND',
    'cn_fund_etf': 'CN_FUND',
    'cn_fund_qdii': 'CN_FUND',
    'cn_fund_lof': 'CN_FUND',
    'cn_fund_index': 'CN_FUND',
    'icbc_wm': 'ICBC_WM',
    'boc_wm': 'BOC_WM',
    'bosc_wm': 'BOSC_WM',
    'crypto': 'CRYPTO',
    'currency': 'CRYPTO',  # Or maybe just 'FX'? But issue says CRYPTO:{pair}
}

def get_namespace_prefix(asset_type: str) -> str:
    """Return the namespace prefix for a given asset type."""
    return TYPE_TO_PREFIX.get(asset_type.lower(), 'UNKNOWN')

def generate_asset_id(symbol: str, asset_type: str) -> str:
    """Generate a namespaced asset_id from a symbol and asset_type."""
    prefix = get_namespace_prefix(asset_type)

    # Clean symbol if necessary (e.g. remove sh/sz for CN_STOCK if present)
    clean_symbol = symbol
    if prefix == 'CN_STOCK':
        if symbol.lower().startswith(('sh', 'sz')):
            clean_symbol = symbol[2:]

    return f"{prefix}:{clean_symbol}"
