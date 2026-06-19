"""Tests for standard product comparator."""

from decimal import Decimal
import pytest
from src.analytics.product_comparison import (
    compare_products,
    ComparisonUseCase,
    ProductComparisonInput,
    YieldType,
)


def test_compare_three_products_simple():
    """Basic comparison of three products in same currency."""
    use_case = ComparisonUseCase(
        target_currency="CNY",
        amount=Decimal("10000"),
        holding_period_days=365,
    )

    products = [
        ProductComparisonInput(
            product_id="P1", name="Money Fund A", currency="CNY",
            yield_value=2.0, yield_type=YieldType.ANNUALIZED_7D,
            mgmt_fee_annual=0.3
        ),
        ProductComparisonInput(
            product_id="P2", name="Bond B", currency="CNY",
            yield_value=3.5, yield_type=YieldType.YTM,
            mgmt_fee_annual=0.1
        ),
        ProductComparisonInput(
            product_id="P3", name="Deposit C", currency="CNY",
            yield_value=2.5, yield_type=YieldType.FIXED
        ),
    ]

    results = compare_products(products, use_case)

    assert len(results) == 3
    # P2 (Bond B) should be first: 3.5 - 0.1 = 3.4%
    assert results[0].product_id == "P2"
    assert results[0].net_yield_scenarios["base"] == 3.4

    # P3 (Deposit C) second: 2.5%
    assert results[1].product_id == "P3"
    assert results[1].net_yield_scenarios["base"] == 2.5

    # P1 (Money Fund A) third: 2.0 - 0.3 = 1.7%
    assert results[2].product_id == "P1"
    assert results[2].net_yield_scenarios["base"] == 1.7


def test_compare_with_fees_and_settlement():
    """Verify that fees and settlement days impact results."""
    use_case = ComparisonUseCase(
        target_currency="CNY",
        amount=Decimal("10000"),
        holding_period_days=90, # Short period makes one-off fees hurt more
    )

    products = [
        ProductComparisonInput(
            product_id="P1", name="No Fee", currency="CNY",
            yield_value=3.0, yield_type=YieldType.FIXED,
            settlement_days=0
        ),
        ProductComparisonInput(
            product_id="P2", name="With Redemp Fee", currency="CNY",
            yield_value=4.0, yield_type=YieldType.FIXED,
            redemption_fee=0.5, # 0.5% one-off
            settlement_days=3
        ),
    ]

    results = compare_products(products, use_case)

    # P2: 4.0 - (0.5 / (90/365)) = 4.0 - 2.027... = 1.97%
    # P1: 3.0%
    assert results[0].product_id == "P1"
    assert results[1].product_id == "P2"
    assert results[0].liquidity_score == 100.0
    assert results[1].liquidity_score == 40.0 # 100 - 3*20


def test_compare_cross_currency_fx_scenarios():
    """Verify FX scenarios for products in different currencies."""
    use_case = ComparisonUseCase(
        target_currency="CNY",
        amount=Decimal("10000"),
        holding_period_days=365,
        allow_fx=True,
        fx_shocks={"base": 0.0, "bull": 0.10, "bear": -0.10}
    )

    products = [
        ProductComparisonInput(
            product_id="USD_BOND", name="USD Bond", currency="USD",
            yield_value=5.0, yield_type=YieldType.YTM,
            fx_fee=0.2
        ),
        ProductComparisonInput(
            product_id="CNY_BOND", name="CNY Bond", currency="CNY",
            yield_value=3.0, yield_type=YieldType.YTM
        ),
    ]

    results = compare_products(products, use_case)
    by_id = {r.product_id: r for r in results}

    # USD Bond Net (base): 5.0 - 0.2 = 4.8%
    # With 10% bull shock: (1 + 0.048) * (1 + 0.10) - 1 = 1.048 * 1.1 - 1 = 1.1528 - 1 = 15.28%
    # With 10% bear shock: (1 + 0.048) * (1 - 0.10) - 1 = 1.048 * 0.9 - 1 = 0.9432 - 1 = -5.68%
    usd_res = by_id["USD_BOND"]
    assert usd_res.net_yield_scenarios["base"] == 4.8
    assert abs(usd_res.net_yield_scenarios["bull"] - 15.28) < 0.01
    assert abs(usd_res.net_yield_scenarios["bear"] - (-5.68)) < 0.01
    assert usd_res.fx_exposure == "USD"

    cny_res = by_id["CNY_BOND"]
    assert cny_res.fx_exposure == "None"


def test_hard_constraints_incomparable():
    """Verify constraints like min_amount and lockup."""
    use_case = ComparisonUseCase(
        target_currency="CNY",
        amount=Decimal("5000"),
        holding_period_days=30,
    )

    products = [
        ProductComparisonInput(
            product_id="P1", name="High Min", currency="CNY",
            yield_value=4.0, yield_type=YieldType.FIXED,
            min_amount=Decimal("10000")
        ),
        ProductComparisonInput(
            product_id="P2", name="Long Lockup", currency="CNY",
            yield_value=4.0, yield_type=YieldType.FIXED,
            lockup_days=90
        ),
    ]

    results = compare_products(products, use_case)
    for r in results:
        assert r.incomparable is True

    reasons = [r.incomparable_reasons[0] for r in results]
    assert any("below minimum" in res for res in reasons)
    assert any("exceeds holding period" in res for res in reasons)


def test_missing_data_coverage():
    """Verify coverage calculation and incomparable status for missing data."""
    use_case = ComparisonUseCase(target_currency="CNY", amount=Decimal("1000"), holding_period_days=365)

    p = ProductComparisonInput(
        product_id="MISSING", name="Incomplete", currency="CNY",
        yield_value=2.0, yield_type=YieldType.FIXED,
        duration=None, credit_rating=None # Missing 2 out of 5 fields
    )

    results = compare_products([p], use_case)
    # 3 fields known: yield, fees (defaulted), settlement (defaulted)
    # 2 missing: duration, credit_rating
    # Coverage = 3/5 = 0.6.
    # Current threshold in code is 0.4 for incomparable, so 0.6 is still comparable.
    assert results[0].coverage == 0.6
    assert results[0].incomparable is False


def test_stable_sorting_tie_break():
    """Tie scores should be broken by product_id."""
    use_case = ComparisonUseCase(target_currency="CNY", amount=Decimal("1000"), holding_period_days=365)
    products = [
        ProductComparisonInput(product_id="P2", name="B", currency="CNY", yield_value=3.0, yield_type=YieldType.FIXED),
        ProductComparisonInput(product_id="P1", name="A", currency="CNY", yield_value=3.0, yield_type=YieldType.FIXED),
    ]
    results = compare_products(products, use_case)
    assert results[0].product_id == "P1"
    assert results[1].product_id == "P2"
