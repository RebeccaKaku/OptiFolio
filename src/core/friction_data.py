"""Hardcoded A-share market friction rules.

These are fixed by regulation and do not require API calls.
Imported as FeeSchedule objects compatible with src/domain/fees.py.
"""

from __future__ import annotations

from src.domain.fees import FeeRule, FeeSchedule, TaxRule, TransactionFee


# ── A-share trading costs ─────────────────────────────────────────────

A_SHARE_STAMP_TAX = TaxRule(
    name="A股印花税",
    rate=0.0005,  # 0.05% — 仅卖出时收取
    tax_on="gains",
    applies_to="sell",
)

A_SHARE_TRANSFER_FEE = TransactionFee(
    name="A股过户费",
    rate=0.00001,  # 0.001% — 双向收取
    applies_to="all",
)

A_SHARE_REGULATORY_FEE = TransactionFee(
    name="A股规费(证管+经手)",
    rate=0.0000687,  # ~0.00687% — 双向收取
    applies_to="all",
)

# ── A-share dividend tax (持股时间阶梯) ────────────────────────────────

A_SHARE_DIVIDEND_TAX_SHORT = TaxRule(
    name="A股分红税-持股<1月",
    rate=0.20,  # 20%
    tax_on="dividends",
    applies_to="all",
)

A_SHARE_DIVIDEND_TAX_MID = TaxRule(
    name="A股分红税-持股1月~1年",
    rate=0.10,  # 10%
    tax_on="dividends",
    applies_to="all",
)

A_SHARE_DIVIDEND_TAX_LONG = TaxRule(
    name="A股分红税-持股>1年",
    rate=0.00,  # 0%
    tax_on="dividends",
    applies_to="all",
)

# ── Default schedules ──────────────────────────────────────────────────

A_SHARE_BUY_FEES = FeeSchedule(
    rules=(A_SHARE_TRANSFER_FEE, A_SHARE_REGULATORY_FEE),
    name="A股买入费用",
)

A_SHARE_SELL_FEES = FeeSchedule(
    rules=(A_SHARE_STAMP_TAX, A_SHARE_TRANSFER_FEE, A_SHARE_REGULATORY_FEE),
    name="A股卖出费用",
)

NO_FEES = FeeSchedule(rules=(), name="零费用")


def get_a_share_fee_schedule(action: str = "all") -> FeeSchedule:
    """Get the standard A-share fee schedule for buy/sell."""
    if action == "buy":
        return A_SHARE_BUY_FEES
    elif action == "sell":
        return A_SHARE_SELL_FEES
    return A_SHARE_SELL_FEES  # default conservative


def get_dividend_tax_rate(holding_days: int) -> float:
    """Get A-share dividend tax rate based on holding period.

    Regulation:
        - < 1 month: 20%
        - 1 month ~ 1 year: 10%
        - > 1 year: 0%
    """
    if holding_days > 365:
        return 0.0
    elif holding_days > 30:
        return 0.10
    else:
        return 0.20
