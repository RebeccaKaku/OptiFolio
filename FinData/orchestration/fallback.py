"""Provider fallback chains.

When a primary data source fails, the orchestrator tries alternates in
order.  ``"cached"`` means "use whatever is already in storage" — no
fetch is attempted for that step.
"""

from __future__ import annotations

FALLBACK_CHAINS: dict[str, list[str]] = {
    "us_equity":      ["akshare-sina"],                      # Only Sina works behind GFW
    "cn_stock":       ["akshare-eastmoney", "akshare-sina", "akshare-tencent"],
    "cn_stock_sh":    ["akshare-eastmoney", "akshare-sina"],
    "cn_stock_sz":    ["akshare-eastmoney", "akshare-sina"],
    "cn_fund":        ["akshare-eastmoney"],
    "cn_fund_open":   ["akshare-eastmoney"],
    "cn_fund_etf":    ["akshare-eastmoney"],
    "cn_fund_money":  ["akshare-eastmoney"],
    "forex":          ["akshare-boc-sina"],
    "currency":       ["akshare-boc-sina"],
    "bank_wm_boc":    ["boc-wmp", "cached"],
    "bank_wm_bosc":   ["bosc-wmp", "cached"],
    "bank_wm_icbc":   ["icbc-wmp", "cached"],
    "crypto":         ["ccxt"],
}
"""Per-asset-type fallback chains.

Each list is tried in order.  The special entry ``"cached"`` means
"skip the fetch and accept whatever is already stored".
"""


def get_fallback_chain(asset_type: str) -> list[str]:
    """Return the ordered fallback chain for *asset_type*.

    Unknown asset types get ``["cached"]`` — no fetch, storage-only.
    """
    return FALLBACK_CHAINS.get(asset_type, ["cached"])
