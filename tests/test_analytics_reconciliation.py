import pytest
from datetime import date
from decimal import Decimal
from src.analytics.reconciliation import (
    reconcile_snapshots, SnapshotInput, PositionInput, CashflowInput, CoverageLevel, ReconciliationRequest
)

def test_pure_market_move():
    prev = SnapshotInput(
        batch_id="b1",
        as_of=date(2026, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "p1", "CNY", market_value=Decimal("100"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    curr = SnapshotInput(
        batch_id="b2",
        as_of=date(2026, 1, 31),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "p1", "CNY", market_value=Decimal("110"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )

    req = ReconciliationRequest(previous=prev, current=curr, cashflows=[])
    res = reconcile_snapshots(req)
    assert res.opening_value == Decimal("100")
    assert res.closing_value == Decimal("110")
    assert res.market_change == Decimal("10")
    assert res.external_net_flow == Decimal("0")
    assert res.unclassified_change == Decimal("0")
    assert res.is_return_eligible is True

def test_external_contribution():
    prev = SnapshotInput(
        batch_id="b1",
        as_of=date(2026, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "cash", "CNY", market_value=Decimal("100"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    curr = SnapshotInput(
        batch_id="b2",
        as_of=date(2026, 1, 31),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "cash", "CNY", market_value=Decimal("150"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    cf = [
        CashflowInput("cf1", "external_contribution", "acc1", Decimal("50"), "CNY", date(2026, 1, 15))
    ]

    req = ReconciliationRequest(previous=prev, current=curr, cashflows=cf)
    res = reconcile_snapshots(req)
    assert res.opening_value == Decimal("100")
    assert res.closing_value == Decimal("150")
    assert res.external_net_flow == Decimal("50")
    assert res.market_change == Decimal("0")
    assert res.unclassified_change == Decimal("0")

def test_investment_income():
    prev = SnapshotInput(
        batch_id="b1",
        as_of=date(2026, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "stock", "CNY", market_value=Decimal("1000"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    curr = SnapshotInput(
        batch_id="b2",
        as_of=date(2026, 1, 31),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "stock", "CNY", market_value=Decimal("1050"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    cf = [
        CashflowInput("cf1", "dividend", "acc1", Decimal("20"), "CNY", date(2026, 1, 15))
    ]

    req = ReconciliationRequest(previous=prev, current=curr, cashflows=cf)
    res = reconcile_snapshots(req)
    # 1050 - 1000 = 50 delta
    # 50 delta = 20 income + 30 market change
    assert res.investment_income == Decimal("20")
    assert res.market_change == Decimal("30")

def test_imbalanced_internal_flow():
    # Transfer out without corresponding transfer in (missing account in scope)
    prev = SnapshotInput(
        batch_id="b1",
        as_of=date(2026, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "cash", "CNY", market_value=Decimal("100"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    curr = SnapshotInput(
        batch_id="b2",
        as_of=date(2026, 1, 31),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "cash", "CNY", market_value=Decimal("60"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    cf = [
        CashflowInput("cf1", "transfer_out", "acc1", Decimal("-40"), "CNY", date(2026, 1, 15))
    ]

    req = ReconciliationRequest(previous=prev, current=curr, cashflows=cf)
    res = reconcile_snapshots(req)
    # 60 - 100 = -40 delta
    # -40 delta = -40 internal flow + 0 market change
    # unclassified_change should capture the imbalanced internal flow
    assert res.internal_flow_net == Decimal("-40")
    assert res.unclassified_change == Decimal("-40")
    assert res.market_change == Decimal("0")

def test_partial_coverage_disables_return():
    prev = SnapshotInput(
        batch_id="b1",
        as_of=date(2026, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.PARTIAL},
        positions=[PositionInput("acc1", "p1", "CNY", market_value=Decimal("100"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    curr = SnapshotInput(
        batch_id="b2",
        as_of=date(2026, 1, 31),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "p1", "CNY", market_value=Decimal("110"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )

    req = ReconciliationRequest(previous=prev, current=curr, cashflows=[])
    res = reconcile_snapshots(req)
    assert res.is_return_eligible is False
    assert res.coverage_status == "partial"
    # When partial, market_change is 0, residual goes to unclassified_change
    assert res.market_change == Decimal("0")
    assert res.unclassified_change == Decimal("10")

def test_mixed_currencies_raises_error():
    prev = SnapshotInput(
        batch_id="b1",
        as_of=date(2026, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[
            PositionInput("acc1", "p1", "CNY", market_value=Decimal("100")),
            PositionInput("acc1", "p2", "USD", market_value=Decimal("10"))
        ],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    curr = SnapshotInput(
        batch_id="b2",
        as_of=date(2026, 1, 31),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "p1", "CNY", market_value=Decimal("110"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )

    req = ReconciliationRequest(previous=prev, current=curr, cashflows=[])
    with pytest.raises(ValueError, match="Mixed currencies found"):
        reconcile_snapshots(req)

def test_invalid_date_order_raises_error():
    prev = SnapshotInput(
        batch_id="b1",
        as_of=date(2026, 1, 31),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    curr = SnapshotInput(
        batch_id="b2",
        as_of=date(2026, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[],
        cashflow_coverage=CoverageLevel.COMPLETE
    )

    req = ReconciliationRequest(previous=prev, current=curr, cashflows=[])
    with pytest.raises(ValueError, match="must be after previous"):
        reconcile_snapshots(req)

def test_fx_conversion_side():
    # Base currency is CNY. FX conversion: sell 100 USD for 700 CNY.
    # We only care about the 700 CNY side.
    prev = SnapshotInput(
        batch_id="b1",
        as_of=date(2026, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "cash", "CNY", market_value=Decimal("1000"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    curr = SnapshotInput(
        batch_id="b2",
        as_of=date(2026, 1, 31),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "cash", "CNY", market_value=Decimal("1700"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    cf = [
        CashflowInput(
            "cf1", "fx_conversion", "acc1",
            amount=Decimal("-100"), currency="USD",
            counter_amount=Decimal("700"), counter_currency="CNY",
            effective_date=date(2026, 1, 15)
        )
    ]

    req = ReconciliationRequest(previous=prev, current=curr, cashflows=cf)
    res = reconcile_snapshots(req)
    assert res.internal_flow_net == Decimal("700")
    assert res.market_change == Decimal("0")
    assert res.unclassified_change == Decimal("700") # Imbalanced because USD side is out of scope

def test_maturity_interest():
    # 1000 CNY matures, returns 1050 CNY.
    prev = SnapshotInput(
        batch_id="b1",
        as_of=date(2026, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "bond", "CNY", market_value=Decimal("1000"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    curr = SnapshotInput(
        batch_id="b2",
        as_of=date(2026, 1, 31),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "cash", "CNY", market_value=Decimal("1050"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    cf = [
        CashflowInput("cf1", "maturity", "acc1", Decimal("1050"), "CNY", date(2026, 1, 15))
    ]

    req = ReconciliationRequest(previous=prev, current=curr, cashflows=cf)
    res = reconcile_snapshots(req)
    assert res.internal_flow_net == Decimal("1050")
    assert res.market_change == Decimal("-1000")
    assert res.unclassified_change == Decimal("1050")

def test_identity_with_all_types():
    prev = SnapshotInput(
        batch_id="b1",
        as_of=date(2026, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "p1", "CNY", market_value=Decimal("1000"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    curr = SnapshotInput(
        batch_id="b2",
        as_of=date(2026, 1, 31),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "p1", "CNY", market_value=Decimal("1200"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    # delta = 200
    cf = [
        CashflowInput("c1", "external_contribution", "acc1", Decimal("100"), "CNY", date(2026, 1, 5)),
        CashflowInput("c2", "dividend", "acc1", Decimal("20"), "CNY", date(2026, 1, 10)),
        CashflowInput("c3", "fee", "acc1", Decimal("-5"), "CNY", date(2026, 1, 15)),
        CashflowInput("c4", "purchase", "acc1", Decimal("-50"), "CNY", date(2026, 1, 20)), # internal
    ]

    req = ReconciliationRequest(previous=prev, current=curr, cashflows=cf)
    res = reconcile_snapshots(req)
    assert res.opening_value == Decimal("1000")
    assert res.closing_value == Decimal("1200")
    assert res.external_net_flow == Decimal("100")
    assert res.investment_income == Decimal("20")
    assert res.fees_taxes == Decimal("-5")
    assert res.internal_flow_net == Decimal("-50")
    assert res.market_change == Decimal("135")
    assert res.fx_effect == Decimal("0")
    assert res.unclassified_change == Decimal("-50")

    # Identity: closing - opening = ext + inc + fee + market + fx + unclassified
    assert res.closing_value - res.opening_value == \
           res.external_net_flow + res.investment_income + res.fees_taxes + \
           res.market_change + res.fx_effect + res.unclassified_change

def test_partial_identity():
    prev = SnapshotInput(
        batch_id="b1",
        as_of=date(2026, 1, 1),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.PARTIAL},
        positions=[PositionInput("acc1", "p1", "CNY", market_value=Decimal("1000"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    curr = SnapshotInput(
        batch_id="b2",
        as_of=date(2026, 1, 31),
        status="confirmed",
        account_coverage={"acc1": CoverageLevel.COMPLETE},
        positions=[PositionInput("acc1", "p1", "CNY", market_value=Decimal("1200"))],
        cashflow_coverage=CoverageLevel.COMPLETE
    )
    cf = [
        CashflowInput("c1", "external_contribution", "acc1", Decimal("100"), "CNY", date(2026, 1, 5)),
    ]

    req = ReconciliationRequest(previous=prev, current=curr, cashflows=cf)
    res = reconcile_snapshots(req)
    assert res.coverage_status == "partial"
    assert res.market_change == Decimal("0")
    assert res.unclassified_change == Decimal("100")

    # Identity
    assert res.closing_value - res.opening_value == \
           res.external_net_flow + res.investment_income + res.fees_taxes + \
           res.market_change + res.fx_effect + res.unclassified_change
