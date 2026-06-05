"""Domain models for OptiFolio's framework-independent core."""

from .cashflows import CashflowEvent
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
from .instruments import InstrumentDefinition
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
from .observations import Observation
from .positions import PositionSnapshot
from .products import ProductDefinition
from .relationships import (
    ExposureDefinition,
    PayoffDefinition,
    PortfolioComponent,
    PortfolioDefinition,
    UnderlyingLink,
)
from .series import SeriesDefinition

__all__ = [
    # models (existing)
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
    # products
    "ProductDefinition",
    # positions
    "PositionSnapshot",
    # cashflows
    "CashflowEvent",
    # instruments
    "InstrumentDefinition",
    # series
    "SeriesDefinition",
    # observations
    "Observation",
    # relationships
    "ExposureDefinition",
    "PayoffDefinition",
    "PortfolioComponent",
    "PortfolioDefinition",
    "UnderlyingLink",
]
