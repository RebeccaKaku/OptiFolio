from decimal import Decimal
from datetime import date
import pytest
from src.analytics.return_attribution import (
    attribute_returns, AttributionRequest, AttributionQuality
)
from src.analytics.reconciliation import (
    SnapshotInput, PositionInput, CashflowInput, CoverageLevel
)
from src.analytics.currency_aggregation import FxQuote, ValuationQuality

def test_usd_product_fixture():
    """
    USD 产品两年本币 +8%，USD/CNY 变化 -10%，验证人民币回报为 -2.8%
    Formula: (1 + 0.08) * (1 - 0.10) - 1 = 1.08 * 0.9 - 1 = 0.972 - 1 = -0.028
    """
    # Opening: 100 USD @ 7.0 CNY/USD = 700 CNY
    # Closing: 108 USD @ 6.3 CNY/USD = 680.4 CNY
    # Change in CNY: 680.4 - 700 = -19.6

    prev = SnapshotInput(
        batch_id="b1",
        as_of=date(2024, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[
            PositionInput(account_id="acc1", product_id="usd_prod", currency="USD", market_value=Decimal("100"))
        ],
        cashflow_coverage=CoverageLevel.COMPLETE
    )

    curr = SnapshotInput(
        batch_id="b2",
        as_of=date(2026, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[
            PositionInput(account_id="acc1", product_id="usd_prod", currency="USD", market_value=Decimal("108"))
        ],
        cashflow_coverage=CoverageLevel.COMPLETE
    )

    fx_quotes = [
        FxQuote(base="USD", quote="CNY", rate=Decimal("7.0"), as_of=date(2024, 1, 1), source="test", quality=ValuationQuality.CONFIRMED),
        FxQuote(base="USD", quote="CNY", rate=Decimal("6.3"), as_of=date(2026, 1, 1), source="test", quality=ValuationQuality.CONFIRMED)
    ]

    request = AttributionRequest(
        previous=prev,
        current=curr,
        cashflows=[],
        fx_quotes=fx_quotes,
        reporting_currency="CNY"
    )

    result = attribute_returns(request)
    attr = result.by_asset[0]

    assert attr.local_return == Decimal("0.08")
    assert attr.fx_return == Decimal("-0.1")
    # interaction = 0.08 * -0.1 = -0.008
    assert attr.interaction_return == Decimal("-0.008")
    # total return = 0.08 - 0.1 - 0.008 = -0.028
    assert attr.total_return_reporting == Decimal("-0.028")
    assert attr.relative_loss_flag is True

    # Amount verification
    # local_pnl_rep = 8 USD * 7.0 = 56.0 CNY
    # fx_pnl_rep = 100 USD * (6.3 - 7.0) = -70.0 CNY
    # interaction_pnl_rep = 8 USD * (6.3 - 7.0) = -5.6 CNY
    # total_change = 56.0 - 70.0 - 5.6 = -19.6
    assert attr.local_pnl_reporting == Decimal("56.0")
    assert attr.fx_pnl_reporting == Decimal("-70.0")
    assert attr.interaction_pnl_reporting == Decimal("-5.6")
    assert attr.total_change_reporting == Decimal("-19.6")
    assert attr.total_change_reporting == attr.local_pnl_reporting + attr.fx_pnl_reporting + attr.interaction_pnl_reporting

def test_attribution_with_flows_and_fees():
    """Test identity with cashflows and fees."""
    # Opening: 1000 CNY
    # Contribution: 500 CNY
    # Fee: -10 CNY
    # Closing: 1600 CNY
    # Local PNL = 1600 - 1000 - 500 = 100 (gross of fees)

    prev = SnapshotInput(
        batch_id="b1",
        as_of=date(2024, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[
            PositionInput(account_id="acc1", product_id="p1", currency="CNY", market_value=Decimal("1000"))
        ],
        cashflow_coverage=CoverageLevel.COMPLETE
    )

    curr = SnapshotInput(
        batch_id="b2",
        as_of=date(2024, 2, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[
            PositionInput(account_id="acc1", product_id="p1", currency="CNY", market_value=Decimal("1600"))
        ],
        cashflow_coverage=CoverageLevel.COMPLETE
    )

    cashflows = [
        CashflowInput(event_id="f1", event_type="external_contribution", account_id="acc1", product_id="p1", amount=Decimal("500"), currency="CNY", effective_date=date(2024, 1, 15)),
        CashflowInput(event_id="f2", event_type="fee", account_id="acc1", product_id="p1", amount=Decimal("-10"), currency="CNY", effective_date=date(2024, 1, 31))
    ]

    request = AttributionRequest(
        previous=prev,
        current=curr,
        cashflows=cashflows,
        fx_quotes=[],
        reporting_currency="CNY"
    )

    result = attribute_returns(request)
    attr = result.by_asset[0]

    assert attr.local_pnl_reporting == Decimal("100")
    assert attr.external_flows_reporting == Decimal("500")
    assert attr.fees_taxes_reporting == Decimal("-10")
    assert attr.total_change_reporting == Decimal("600")

    # Identity: 100 + 0 + 0 + 500 + (-10) + unclassified = 600
    # 590 + unclassified = 600 -> unclassified = 10
    # Wait, why unclassified 10?
    # closing = 1600, opening = 1000, flows = 500, fees = -10.
    # If fees_already_in_closing_value=False:
    # gross_local_pnl = closing - opening - flows = 1600 - 1000 - 500 = 100.
    # explained = 100 (local) + 500 (flow) - 10 (fee) = 590.
    # unclassified = 600 - 590 = 10.
    # This 10 is actually the fee that was NOT in the closing value but we want to show it.
    # If the fee is "outside", it means it didn't reduce the closing_value.
    assert attr.unclassified_reporting == Decimal("10")

    # Now test with fees_already_in_closing_value=True
    request_net = AttributionRequest(
        previous=prev,
        current=curr,
        cashflows=cashflows,
        fx_quotes=[],
        reporting_currency="CNY",
        fees_already_in_closing_value=True
    )
    result_net = attribute_returns(request_net)
    attr_net = result_net.by_asset[0]
    # gross_local_pnl = closing - opening - flows - fees = 1600 - 1000 - 500 - (-10) = 110.
    assert attr_net.local_pnl_reporting == Decimal("110")
    assert attr_net.unclassified_reporting == Decimal("0")

def test_missing_fx_degrades_quality():
    prev = SnapshotInput(
        batch_id="b1", as_of=date(2024, 1, 1), status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput(account_id="acc1", product_id="p1", currency="USD", market_value=Decimal("100"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    curr = SnapshotInput(
        batch_id="b2", as_of=date(2024, 2, 1), status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput(account_id="acc1", product_id="p1", currency="USD", market_value=Decimal("110"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    # Missing FX quotes
    request = AttributionRequest(previous=prev, current=curr, cashflows=[], fx_quotes=[], reporting_currency="CNY")
    result = attribute_returns(request)

    assert result.total.quality == AttributionQuality.ESTIMATED
    assert result.by_asset[0].quality == AttributionQuality.NOT_ATTRIBUTABLE
    assert "Missing opening FX for USD" in result.by_asset[0].warnings

def test_partial_coverage_degrades_quality():
    prev = SnapshotInput(
        batch_id="b1", as_of=date(2024, 1, 1), status="confirmed",
        account_coverage={"acc1": CoverageLevel.PARTIAL},
        positions=[PositionInput(account_id="acc1", product_id="p1", currency="CNY", market_value=Decimal("100"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    curr = SnapshotInput(
        batch_id="b2", as_of=date(2024, 2, 1), status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput(account_id="acc1", product_id="p1", currency="CNY", market_value=Decimal("110"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    request = AttributionRequest(previous=prev, current=curr, cashflows=[], fx_quotes=[], reporting_currency="CNY")
    result = attribute_returns(request)

    assert result.total.quality == AttributionQuality.ESTIMATED
    assert "Previous snapshot has partial account coverage" in result.total.warnings
