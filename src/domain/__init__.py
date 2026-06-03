"""Domain models for OptiFolio's framework-independent core."""

from .corporate_actions import (
    CorporateAction,
    DividendAction,
    MergerAction,
    StockSplitAction,
    corporate_action_from_dict,
)
from .fees import (
    FeeRule,
    FeeSchedule,
    ManagementFee,
    TaxRule,
    TransactionFee,
)
from .models import (
    AllocationResult,
    CashHolding,
    Holding,
    OptimizationRequest,
    PortfolioHistoryEntry,
    PortfolioSnapshot,
    PositionValue,
    RebalancePlan,
    RiskReport,
    Universe,
    ValuationRequest,
    ValuationResult,
)

__all__ = [
    # models
    "AllocationResult",
    "CashHolding",
    "Holding",
    "OptimizationRequest",
    "PortfolioHistoryEntry",
    "PortfolioSnapshot",
    "PositionValue",
    "RebalancePlan",
    "RiskReport",
    "Universe",
    "ValuationRequest",
    "ValuationResult",
    # corporate actions
    "CorporateAction",
    "DividendAction",
    "MergerAction",
    "StockSplitAction",
    "corporate_action_from_dict",
    # fees
    "FeeRule",
    "FeeSchedule",
    "ManagementFee",
    "TaxRule",
    "TransactionFee",
]
