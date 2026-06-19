"""CN stock symbol normalization utilities.

CN stock symbols may be stored bare (600519) or prefixed (sh600519, sz000001).
This module provides a single shared function to normalize between forms.

Usage::

    from src.core.symbols import normalize_cn_symbol, CN_EXCHANGE_PREFIXES

    for form in normalize_cn_symbol("600519"):
        ...  # 600519, sh600519, ...

    for form in normalize_cn_symbol("sh600519"):
        ...  # sh600519, 600519, sz600519
"""

from __future__ import annotations

import re

# Exchange prefix → leading digit prefixes for CN A-shares
CN_EXCHANGE_PREFIXES: dict[str, frozenset[str]] = {
    "sh": frozenset({"600", "601", "603", "605", "688"}),
    "sz": frozenset({"000", "001", "002", "003", "300"}),
    "bj": frozenset({"4", "8"}),  # Beijing Stock Exchange
}


def _infer_exchange_prefix(code: str) -> str:
    """Infer exchange prefix (sh / sz / bj) from bare 6-digit CN stock code."""
    if code.startswith(("600", "601", "603", "605", "688")):
        return "sh"
    if code.startswith(("000", "001", "002", "003", "300")):
        return "sz"
    if code.startswith(("4", "8")):  # Beijing exchange
        return "bj"
    return "sh"


def normalize_cn_symbol(symbol: str) -> list[str]:
    """Return candidate forms for a CN stock symbol (bare + prefixed variants).

    CN stock symbols may be stored bare (``600519``) or prefixed
    (``sh600519``, ``sz000001``).  Returns all plausible forms so
    lookups don't fail on format mismatches.

    Args:
        symbol: A CN stock symbol, either bare 6-digit code or
                prefixed (e.g. ``'600519'``, ``'sh600519'``).

    Returns:
        List of candidate forms.  The input form is always first.
    """
    symbol = symbol.strip()
    result: list[str] = [symbol]

    # Prefixed form → extract bare code + add other prefix
    m = re.match(r'^(?:sh|sz|bj)(\d{6})$', symbol, re.IGNORECASE)
    if m:
        bare = m.group(1)
        if bare not in result:
            result.append(bare)
        prefix = _infer_exchange_prefix(bare)
        other = f"sz{bare}" if prefix == "sh" else f"sh{bare}"
        if other not in result:
            result.append(other)
        return result

    # Bare 6-digit code → add prefixed forms
    if re.match(r'^\d{6}$', symbol):
        prefix = _infer_exchange_prefix(symbol)
        result.append(f"{prefix}{symbol}")
        other = "sz" if prefix == "sh" else "sh"
        result.append(f"{other}{symbol}")

    return result
