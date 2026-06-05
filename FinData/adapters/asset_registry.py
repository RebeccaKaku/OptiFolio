import re
from typing import Dict, Optional

# Mapping from internal asset_type to namespaced prefix
TYPE_TO_PREFIX = {
    'us_equity': 'US_EQ',
    'us_stock': 'US_EQ',
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
    'currency': 'FX',
}

def get_namespace_prefix(asset_type: str) -> str:
    """Return the namespace prefix for a given asset type."""
    return TYPE_TO_PREFIX.get(asset_type.lower(), 'UNKNOWN')

def generate_asset_id(symbol: str, asset_type: str) -> str:
    """
    Generate a namespaced asset_id from a symbol and asset_type.

    Formats:
    - US_EQ:{symbol}
    - CN_STOCK:{code} (removes sh/sz prefix)
    - CN_FUND:{code}
    - ICBC_WM:{code}
    - CRYPTO:{pair}
    - FX:{pair}
    """
    prefix = get_namespace_prefix(asset_type)
    symbol = symbol.strip()

    # Clean symbol if necessary
    clean_symbol = symbol
    if prefix == 'CN_STOCK':
        # Remove sh/sz prefix if present
        clean_symbol = re.sub(r'^(sh|sz)', '', symbol.lower())
    elif prefix in ['US_EQ', 'CRYPTO', 'FX']:
        clean_symbol = symbol.upper()

    return f"{prefix}:{clean_symbol}"

# Alias for backward compatibility if needed during migration
def get_namespaced_id(symbol: str, asset_type: str) -> str:
    return generate_asset_id(symbol, asset_type)
