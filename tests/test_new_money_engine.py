import pytest
from decimal import Decimal
from src.analytics.new_money_engine import (
    NewMoneyEngine, NewMoneyRequest, CandidateProduct,
    NewMoneyConstraints, AllocationGapReport
)
from src.analytics.trade_friction import AllocationFrictionInput
from src.analytics.allocation_targets import AllocationGapItem, AllocationGapReport

def test_new_money_basic_allocation():
    engine = NewMoneyEngine()

    # 1. Setup Request
    request = NewMoneyRequest(
        new_cash_amount=Decimal("100000"),
        currency="CNY",
        reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1")},
        current_total_value=Decimal("900000"),
        current_exposures={
            "product": {"EXISTING": Decimal("1.0")}
        },
        gaps=[],
        candidates=[
            CandidateProduct(
                asset_id="PROD_B",
                name="Product B",
                currency="CNY",
                asset_class="bond",
                issuer="BANK_B",
                purpose_bucket="core",
                liquidity_level="low"
            )
        ],
        constraints=NewMoneyConstraints()
    )

    # 2. Run
    proposals = engine.run(request)

    assert len(proposals) == 3
    for p in proposals:
        assert p.status == "success"
        assert len(p.allocations) == 1
        assert p.allocations[0].asset_id == "PROD_B"
        assert p.allocations[0].amount_original == Decimal("100000")
        assert p.residual_cash == Decimal("0")
        # Post trade total: 900k + 100k = 1M.
        # EXISTING scaled: 1.0 * (900k/1M) = 0.9
        # PROD_B: 100k/1M = 0.1
        assert p.post_trade_weights["product"]["EXISTING"] == pytest.approx(Decimal("0.9"))
        assert p.post_trade_weights["product"]["PROD_B"] == pytest.approx(Decimal("0.1"))

def test_new_money_constraints_hit():
    engine = NewMoneyEngine()

    # Product cap 5%. Total value 1M (900k + 100k). Max alloc 50k.
    request = NewMoneyRequest(
        new_cash_amount=Decimal("100000"),
        currency="CNY",
        reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1")},
        current_total_value=Decimal("900000"),
        current_exposures={},
        gaps=[],
        candidates=[
            CandidateProduct(
                asset_id="PROD_B",
                name="Product B",
                currency="CNY",
                asset_class="bond",
                issuer="BANK_B",
                purpose_bucket="core",
                liquidity_level="low"
            )
        ],
        constraints=NewMoneyConstraints(
            single_product_max_pct=Decimal("0.05")
        )
    )

    proposals = engine.run(request)
    for p in proposals:
        assert p.status == "partial"
        assert p.allocations[0].amount_original == Decimal("50000")
        assert p.residual_cash == Decimal("50000")

def test_new_money_strategy_difference():
    engine = NewMoneyEngine()

    # PROD_LIQ: Low liquidity restriction, but no gap
    # PROD_GAP: Filling a gap, but medium liquidity

    gap_item = AllocationGapItem(
        bucket="PROD_GAP",
        current_weight=Decimal("0"),
        min=Decimal("0.1"),
        max=Decimal("0.2"),
        status="below",
        gap_to_min=Decimal("0.1"),
        gap_to_max=Decimal("0.2"),
        amount_range=(Decimal("100000"), Decimal("200000")),
        quality="exact"
    )

    request = NewMoneyRequest(
        new_cash_amount=Decimal("100000"),
        currency="CNY",
        reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1")},
        current_total_value=Decimal("900000"),
        current_exposures={},
        gaps=[AllocationGapReport(scope="total", dimension="product", items=[gap_item], unknown_pct=Decimal("0"))],
        candidates=[
            CandidateProduct(
                asset_id="PROD_LIQ", name="Liq", currency="CNY",
                asset_class="cash", issuer="I1", purpose_bucket="P1", liquidity_level="low"
            ),
            CandidateProduct(
                asset_id="PROD_GAP", name="Gap", currency="CNY",
                asset_class="bond", issuer="I2", purpose_bucket="P1", liquidity_level="medium"
            )
        ],
        constraints=NewMoneyConstraints()
    )

    proposals = {p.strategy: p for p in engine.run(request)}

    # gap_first should pick PROD_GAP first
    assert proposals["gap_first"].allocations[0].asset_id == "PROD_GAP"

    # liquidity_first should pick PROD_LIQ first
    assert proposals["liquidity_first"].allocations[0].asset_id == "PROD_LIQ"

def test_new_money_insufficient_funds_for_min_trade():
    engine = NewMoneyEngine()
    request = NewMoneyRequest(
        new_cash_amount=Decimal("500"),
        currency="CNY",
        reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1")},
        current_total_value=Decimal("10000"),
        current_exposures={},
        gaps=[],
        candidates=[
            CandidateProduct(
                asset_id="P1", name="P1", currency="CNY", asset_class="C",
                issuer="I", purpose_bucket="B", liquidity_level="low", min_trade_amount=Decimal("1000")
            )
        ],
        constraints=NewMoneyConstraints()
    )

    proposals = engine.run(request)
    for p in proposals:
        assert p.status == "failed"
        assert len(p.allocations) == 0
        assert p.residual_cash == Decimal("500")

def test_new_money_fx_conversion():
    engine = NewMoneyEngine()
    # 10,000 USD new money. 1 USD = 7.2 CNY.
    # Product in CNY.
    request = NewMoneyRequest(
        new_cash_amount=Decimal("10000"),
        currency="USD",
        reporting_currency="CNY",
        fx_rates={"USD": Decimal("7.2"), "CNY": Decimal("1")},
        current_total_value=Decimal("0"),
        current_exposures={},
        gaps=[],
        candidates=[
            CandidateProduct(
                asset_id="PROD_CNY", name="CNY Prod", currency="CNY",
                asset_class="C", issuer="I", purpose_bucket="B", liquidity_level="low"
            )
        ],
        constraints=NewMoneyConstraints()
    )

    proposals = engine.run(request)
    for p in proposals:
        assert p.status == "success"
        # 10,000 USD should all be allocated
        assert p.allocations[0].amount_reporting == Decimal("72000")
        assert p.residual_cash == Decimal("0")

def test_new_money_budget_identity():
    engine = NewMoneyEngine()
    request = NewMoneyRequest(
        new_cash_amount=Decimal("1000.00"),
        currency="USD",
        reporting_currency="CNY",
        fx_rates={"USD": Decimal("7.20"), "CNY": Decimal("1.00")},
        current_total_value=Decimal("10000"),
        current_exposures={},
        gaps=[],
        candidates=[
            CandidateProduct(
                asset_id="P1", name="P1", currency="CNY", asset_class="C",
                issuer="I", purpose_bucket="B", liquidity_level="low", max_trade_amount=Decimal("3600") # 500 USD
            )
        ],
        constraints=NewMoneyConstraints()
    )

    proposals = engine.run(request)
    for p in proposals:
        total_allocated_orig = sum(engine._convert(a.amount_reporting, a.currency, request.currency, request.fx_rates) for a in p.allocations)
        assert (total_allocated_orig + p.residual_cash) == pytest.approx(request.new_cash_amount)

def test_new_money_input_order_independence():
    engine = NewMoneyEngine()

    c1 = CandidateProduct(asset_id="P1", name="P1", currency="CNY", asset_class="C", issuer="I1", purpose_bucket="B", liquidity_level="low")
    c2 = CandidateProduct(asset_id="P2", name="P2", currency="CNY", asset_class="C", issuer="I2", purpose_bucket="B", liquidity_level="low")

    req1 = NewMoneyRequest(
        new_cash_amount=Decimal("1000"), currency="CNY", reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1")}, current_total_value=Decimal("0"),
        current_exposures={}, gaps=[], candidates=[c1, c2], constraints=NewMoneyConstraints()
    )
    req2 = NewMoneyRequest(
        new_cash_amount=Decimal("1000"), currency="CNY", reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1")}, current_total_value=Decimal("0"),
        current_exposures={}, gaps=[], candidates=[c2, c1], constraints=NewMoneyConstraints()
    )

    prop1 = engine.run(req1)
    prop2 = engine.run(req2)

    for p1, p2 in zip(prop1, prop2):
        assert p1.strategy == p2.strategy
        assert [a.asset_id for a in p1.allocations] == [a.asset_id for a in p2.allocations]
        assert [a.amount_original for a in p1.allocations] == [a.amount_original for a in p2.allocations]

def test_new_money_liquidity_floor():
    engine = NewMoneyEngine()
    # 100k new money, 900k existing. 1M total.
    # Constraint: 20% must be 'low' liquidity.
    # Existing: 10% 'low'.
    # New money must provide at least 10% more 'low' (100k).

    request = NewMoneyRequest(
        new_cash_amount=Decimal("100000"),
        currency="CNY",
        reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1")},
        current_total_value=Decimal("900000"),
        current_exposures={
            "liquidity": {"low": Decimal("0.1"), "medium": Decimal("0.9")}
        },
        gaps=[],
        candidates=[
            CandidateProduct(
                asset_id="P_HIGH", name="High", currency="CNY",
                asset_class="equity", issuer="I", purpose_bucket="B", liquidity_level="high"
            )
        ],
        constraints=NewMoneyConstraints(
            liquidity_low_min_pct=Decimal("0.2")
        )
    )

    proposals = engine.run(request)
    for p in proposals:
        assert "liquidity_low_min_pct" in p.binding_constraints

def test_new_money_no_feasible_products():
    engine = NewMoneyEngine()
    request = NewMoneyRequest(
        new_cash_amount=Decimal("100000"),
        currency="USD", # No FX rate for USD provided
        reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1")},
        current_total_value=Decimal("900000"),
        current_exposures={},
        gaps=[],
        candidates=[
             CandidateProduct(asset_id="P1", name="P1", currency="CNY", asset_class="C", issuer="I", purpose_bucket="B", liquidity_level="low")
        ],
        constraints=NewMoneyConstraints()
    )

    proposals = engine.run(request)
    for p in proposals:
        assert p.status == "failed"
        assert p.residual_cash == Decimal("100000")

def test_new_money_max_cash_retention():
    engine = NewMoneyEngine()
    # 100k new money. Can only retain 10% (10k).
    # If partial allocation leaves 20k residual, it should show as binding constraint.
    request = NewMoneyRequest(
        new_cash_amount=Decimal("100000"),
        currency="CNY",
        reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1")},
        current_total_value=Decimal("0"),
        current_exposures={},
        gaps=[],
        candidates=[
            CandidateProduct(
                asset_id="P1", name="P1", currency="CNY", asset_class="C",
                issuer="I", purpose_bucket="B", liquidity_level="low", max_trade_amount=Decimal("80000")
            )
        ],
        constraints=NewMoneyConstraints(
            max_cash_retention_pct=Decimal("0.1")
        )
    )

    proposals = engine.run(request)
    for p in proposals:
        assert p.status == "partial"
        assert p.residual_cash == Decimal("20000")
        assert "max_cash_retention_pct" in p.binding_constraints

def test_new_money_friction_rejection():
    engine = NewMoneyEngine()
    # 10k new money, 1M total value. Allocation weight = 1%.
    # Global no-trade band = 2%.

    request = NewMoneyRequest(
        new_cash_amount=Decimal("10000"),
        currency="CNY",
        reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1")},
        current_total_value=Decimal("990000"),
        current_exposures={},
        gaps=[],
        candidates=[
            CandidateProduct(
                asset_id="P1", name="P1", currency="CNY", asset_class="C",
                issuer="I", purpose_bucket="B", liquidity_level="low",
                friction_input=AllocationFrictionInput(
                    buy_fee_rate=Decimal("0"),
                    sell_fee_rate=Decimal("0"),
                    mgmt_fee_diff_rate=Decimal("0"),
                    fixed_fees=Decimal("0"),
                    fx_spread_rate=Decimal("0")
                )
            )
        ],
        constraints=NewMoneyConstraints(
            no_trade_band_pct=Decimal("0.02") # 2%
        )
    )

    proposals = engine.run(request)
    for p in proposals:
        assert p.status == "failed"
        assert len(p.allocations) == 0
        assert any("within no-trade band" in r["reason"] for r in p.rejected_candidates)

def test_new_money_friction_cost_vs_benefit():
    engine = NewMoneyEngine()

    request = NewMoneyRequest(
        new_cash_amount=Decimal("10000"),
        currency="CNY",
        reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1")},
        current_total_value=Decimal("0"),
        current_exposures={},
        gaps=[],
        candidates=[
            CandidateProduct(
                asset_id="P1", name="P1", currency="CNY", asset_class="C",
                issuer="I", purpose_bucket="B", liquidity_level="low",
                monetized_benefit_annual_rate=Decimal("0.01"), # 1% benefit
                friction_input=AllocationFrictionInput(
                    buy_fee_rate=Decimal("0.02"), # 2% cost > 1% benefit
                    sell_fee_rate=Decimal("0"),
                    mgmt_fee_diff_rate=Decimal("0"),
                    fixed_fees=Decimal("0"),
                    fx_spread_rate=Decimal("0")
                )
            )
        ],
        constraints=NewMoneyConstraints(
            expected_holding_period_years=Decimal("1.0")
        )
    )

    proposals = engine.run(request)
    for p in proposals:
        assert p.status == "failed"
        assert len(p.allocations) == 0
        assert any("does not exceed costs" in r["reason"] for r in p.rejected_candidates)

def test_new_money_currency_purpose_constraint():
    engine = NewMoneyEngine()
    
    # Candidate P_CNY belongs to "core" bucket (constrained to CNY)
    # Candidate P_USD belongs to "core" bucket (constrained to CNY) - should be rejected!
    c_cny = CandidateProduct(
        asset_id="P_CNY", name="CNY Product", currency="CNY",
        asset_class="deposit", issuer="BANK_A", purpose_bucket="core", liquidity_level="low"
    )
    c_usd = CandidateProduct(
        asset_id="P_USD", name="USD Product", currency="USD",
        asset_class="deposit", issuer="BANK_A", purpose_bucket="core", liquidity_level="low"
    )
    
    request = NewMoneyRequest(
        new_cash_amount=Decimal("10000"),
        currency="CNY",
        reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1"), "USD": Decimal("7.2")},
        current_total_value=Decimal("0"),
        current_exposures={},
        gaps=[],
        candidates=[c_cny, c_usd],
        constraints=NewMoneyConstraints(
            purpose_bucket_currencies={"core": "CNY"}
        )
    )
    
    proposals = engine.run(request)
    for p in proposals:
        # P_USD should be rejected because its currency (USD) doesn't match the "core" bucket base currency (CNY)
        rejected_ids = [item["asset_id"] for item in p.rejected_candidates]
        assert "P_USD" in rejected_ids
        assert any("base currency CNY" in item["reason"] for item in p.rejected_candidates if item["asset_id"] == "P_USD")
        
        # P_CNY should be allocated successfully
        assert any(a.asset_id == "P_CNY" for a in p.allocations)
        assert not any(a.asset_id == "P_USD" for a in p.allocations)

def test_new_money_multiple_gaps():
    engine = NewMoneyEngine()
    
    # Gap in asset class "bond" and gap in product "P_GAP_1"
    gap_product = AllocationGapItem(
        bucket="P_GAP_1", current_weight=Decimal("0"), min=Decimal("0.1"), max=Decimal("0.2"),
        status="below", gap_to_min=Decimal("0.1"), gap_to_max=Decimal("0.2"),
        amount_range=(Decimal("10000"), Decimal("20000")), quality="exact"
    )
    gap_asset_class = AllocationGapItem(
        bucket="bond", current_weight=Decimal("0"), min=Decimal("0.3"), max=Decimal("0.5"),
        status="below", gap_to_min=Decimal("0.3"), gap_to_max=Decimal("0.5"),
        amount_range=(Decimal("30000"), Decimal("50000")), quality="exact"
    )
    
    gaps = [
        AllocationGapReport(scope="total", dimension="product", items=[gap_product], unknown_pct=Decimal("0")),
        AllocationGapReport(scope="total", dimension="asset_class", items=[gap_asset_class], unknown_pct=Decimal("0"))
    ]
    
    # P1 is bond (fills bond gap, gap=0.3)
    # P2 is cash (no gap)
    # P3 is bond and asset_id P_GAP_1 (fills both bond gap and product gap, total gap = 0.3 + 0.1 = 0.4)
    # Under gap_first, P3 should be sorted first (score 0.4), then P1 (score 0.3), then P2 (score 0)
    c1 = CandidateProduct(asset_id="P1", name="P1", currency="CNY", asset_class="bond", issuer="I", purpose_bucket="B", liquidity_level="low")
    c2 = CandidateProduct(asset_id="P2", name="P2", currency="CNY", asset_class="cash", issuer="I", purpose_bucket="B", liquidity_level="low")
    c3 = CandidateProduct(asset_id="P_GAP_1", name="P3", currency="CNY", asset_class="bond", issuer="I", purpose_bucket="B", liquidity_level="low")
    
    request = NewMoneyRequest(
        new_cash_amount=Decimal("100000"),
        currency="CNY",
        reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1")},
        current_total_value=Decimal("100000"),
        current_exposures={},
        gaps=gaps,
        candidates=[c1, c2, c3],
        constraints=NewMoneyConstraints(
            single_product_max_pct=Decimal("0.4")
        )
    )
    
    proposals = {p.strategy: p for p in engine.run(request)}
    gap_first_allocs = proposals["gap_first"].allocations
    
    # Check that gap_first strategy sorts and allocates to P_GAP_1 first, then P1.
    # Total value = 200,000. Cap per product = 40% * 200k = 80,000.
    # P_GAP_1 gets 80,000 (first candidate, fills product gap & asset class gap).
    # P1 gets 20,000 (remaining cash).
    assert len(gap_first_allocs) == 2
    assert gap_first_allocs[0].asset_id == "P_GAP_1"
    assert gap_first_allocs[0].amount_original == Decimal("80000")
    assert gap_first_allocs[1].asset_id == "P1"
    assert gap_first_allocs[1].amount_original == Decimal("20000")

def test_new_money_residual_cash_exposures():
    engine = NewMoneyEngine()
    
    # Setup request where some cash is not allocated (max product cap restricts it)
    request = NewMoneyRequest(
        new_cash_amount=Decimal("100000"),
        currency="CNY",
        reporting_currency="CNY",
        fx_rates={"CNY": Decimal("1")},
        current_total_value=Decimal("0"),
        current_exposures={},
        gaps=[],
        candidates=[
            CandidateProduct(
                asset_id="P1", name="P1", currency="CNY", asset_class="bond", issuer="I1", purpose_bucket="B", liquidity_level="low"
            )
        ],
        constraints=NewMoneyConstraints(
            single_product_max_pct=Decimal("0.4") # Can allocate at most 40% (40,000 CNY)
        )
    )
    
    proposals = engine.run(request)
    for p in proposals:
        assert p.status == "partial"
        assert p.residual_cash == Decimal("60000")
        
        # Verify that post_trade_weights contains the residual cash (60%)
        # across different dimensions, ensuring weights sum to 100%
        w = p.post_trade_weights
        assert w["product"]["P1"] == pytest.approx(Decimal("0.4"))
        assert w["product"]["cash"] == pytest.approx(Decimal("0.6"))
        
        assert w["asset_class"]["bond"] == pytest.approx(Decimal("0.4"))
        assert w["asset_class"]["cash"] == pytest.approx(Decimal("0.6"))
        
        assert w["currency"]["CNY"] == pytest.approx(Decimal("1.0"))
        
        assert w["liquidity"]["low"] == pytest.approx(Decimal("0.4"))
        assert w["liquidity"]["high"] == pytest.approx(Decimal("0.6"))
        
        assert w["issuer"]["I1"] == pytest.approx(Decimal("0.4"))
        assert w["issuer"]["cash"] == pytest.approx(Decimal("0.6"))
