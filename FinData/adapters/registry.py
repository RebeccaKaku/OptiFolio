import re

def get_namespaced_id(symbol: str, asset_type: str) -> str:
    """
    Generate a namespaced asset_id from a symbol and asset_type.

    Formats:
    - US_EQ:{symbol}
    - CN_STOCK:{code} (removes sh/sz prefix)
    - CN_FUND:{code}
    - ICBC_WM:{code}
    """
    asset_type = asset_type.lower()
    symbol = symbol.strip()

    if asset_type == "us_equity" or asset_type == "us_stock":
        return f"US_EQ:{symbol.upper()}"

    if asset_type in ["cn_stock", "cn_stock_sh", "cn_stock_sz"]:
        # Remove sh/sz prefix if present
        code = re.sub(r'^(sh|sz)', '', symbol.lower())
        return f"CN_STOCK:{code}"

    if asset_type.startswith("cn_fund"):
        return f"CN_FUND:{symbol}"

    if asset_type == "icbc_wm":
        return f"ICBC_WM:{symbol}"

    if asset_type == "boc_wm":
        return f"BOC_WM:{symbol}"

    if asset_type == "bosc_wm":
        return f"BOSC_WM:{symbol}"

    if asset_type == "crypto":
        return f"CRYPTO:{symbol.upper()}"

    if asset_type == "currency":
        return f"FX:{symbol.upper()}"

    # Default fallback
    return f"{asset_type.upper()}:{symbol}"
