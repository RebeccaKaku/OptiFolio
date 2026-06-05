"""Product definition contract — financial products offered to clients."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ProductDefinition:
    """A financial product that can appear in client portfolios.

    product_type is one of:
      deposit, money_fund, bond_fund, mixed_fund, bank_wmp,
      fx, structured_deposit
    """

    product_id: str  # canonical id
    name: str
    product_type: str  # deposit, money_fund, bond_fund, mixed_fund, bank_wmp, fx, structured_deposit
    issuer: Optional[str] = None
    manager: Optional[str] = None
    currency: str = "CNY"
    risk_level: Optional[str] = None
    liquidity_type: Optional[str] = None
    fee_policy_id: Optional[str] = None
    benchmark_id: Optional[str] = None
    primary_instrument_id: Optional[str] = None
    data_source: str = "manual"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
