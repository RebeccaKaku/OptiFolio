"""CN stock symbol normalization — re-export shim.

Canonical definitions now live in optifolio_contracts.symbols.
This module exists for backward compatibility with existing imports.
Prefer ``from optifolio_contracts import normalize_cn_symbol`` in new code.
"""

from optifolio_contracts.symbols import (  # noqa: F401
    CN_EXCHANGE_PREFIXES,
    _infer_exchange_prefix,
    normalize_cn_symbol,
)
