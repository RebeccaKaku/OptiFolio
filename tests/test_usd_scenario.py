import pytest
from decimal import Decimal
from src.analytics.usd_scenario import run_usd_scenarios, UsdExposure, ExposureRole, ScenarioResult

def test_benchmark_0_0_0():
    """Verify that 0 product return, 0 FX change, and 0 fees results in no change."""
    exposures = [
        UsdExposure(Decimal("100"), ExposureRole.PAYOFF_CURRENCY),
        UsdExposure(Decimal("50"), ExposureRole.LOOKTHROUGH_ECONOMIC),
        UsdExposure(Decimal("50"), ExposureRole.HEDGED, hedged_ratio=Decimal("1.0")),
        UsdExposure(Decimal("10"), ExposureRole.UNKNOWN),
    ]
    r_prod = [Decimal("0")]
    r_fx = [Decimal("0")]
    opening_fx = Decimal("7.0")

    grid = run_usd_scenarios(exposures, r_prod, r_fx, opening_fx)
    res = grid[0][0]

    total_opening_usd = Decimal("210")
    total_opening_cny = total_opening_usd * opening_fx

    assert res.ending_value_usd == total_opening_usd
    assert res.ending_value_cny == total_opening_cny
    assert res.cny_return == Decimal("0")
    assert res.local_component == Decimal("0")
    assert res.fx_component == Decimal("0")
    assert res.interaction == Decimal("0")
    assert res.fees == Decimal("0")
    assert res.relative_to_cny_benchmark == Decimal("0")

def test_basic_positive_scenario():
    """Test 10% product return and 5% USD appreciation."""
    exposures = [UsdExposure(Decimal("100"), ExposureRole.PAYOFF_CURRENCY)]
    r_prod = [Decimal("0.1")]
    r_fx = [Decimal("0.05")]
    opening_fx = Decimal("7.0")

    grid = run_usd_scenarios(exposures, r_prod, r_fx, opening_fx)
    res = grid[0][0]

    # ending_usd = 100 * (1 + 0.1) = 110
    # ending_cny = 110 * 7 * (1 + 0.05) = 110 * 7.35 = 808.5
    assert res.ending_value_usd == Decimal("110")
    assert res.ending_value_cny == Decimal("808.5")

    # components:
    # local = 100 * 0.1 * 7 = 70
    # fx = 100 * 7 * 0.05 = 35
    # interaction = 100 * 0.1 * 7 * 0.05 = 3.5
    # total_change = 808.5 - 700 = 108.5
    # 70 + 35 + 3.5 = 108.5 (Exact)
    assert res.local_component == Decimal("70")
    assert res.fx_component == Decimal("35")
    assert res.interaction == Decimal("3.5")
    assert res.local_component + res.fx_component + res.interaction + res.fees == res.ending_value_cny - (Decimal("100") * opening_fx)

def test_hedge_and_lookthrough():
    """Verify that LOOKTHROUGH has no FX impact and HEDGED has partial impact."""
    exposures = [
        UsdExposure(Decimal("100"), ExposureRole.LOOKTHROUGH_ECONOMIC),
        UsdExposure(Decimal("100"), ExposureRole.HEDGED, hedged_ratio=Decimal("0.6")),
    ]
    r_prod = [Decimal("0")]
    r_fx = [Decimal("0.1")]
    opening_fx = Decimal("7.0")

    grid = run_usd_scenarios(exposures, r_prod, r_fx, opening_fx)
    res = grid[0][0]

    # LOOKTHROUGH: end_cny = 100 * 7 * (1 + 0) = 700
    # HEDGED (0.6): eff_fx = 0.1 * (1 - 0.6) = 0.04; end_cny = 100 * 7 * (1 + 0.04) = 728
    # total_ending_cny = 1428
    assert res.ending_value_cny == Decimal("1428")
    assert res.fx_component == Decimal("28") # Only from hedged one

def test_fee_handling():
    """Test fee deduction and already_in_return flag."""
    exposures = [UsdExposure(Decimal("100"), ExposureRole.PAYOFF_CURRENCY)]
    r_prod = [Decimal("0.1")]
    r_fx = [Decimal("0")]
    opening_fx = Decimal("7.0")
    fee_usd = Decimal("1")

    # Case 1: Deduct fee
    grid = run_usd_scenarios(exposures, r_prod, r_fx, opening_fx, fee_usd=fee_usd, fees_already_in_return=False)
    res = grid[0][0]
    # end_usd = 100 * 1.1 - 1 = 109
    # end_cny = 109 * 7 = 763
    # fees_impact = -1 * 7 * 1 = -7
    assert res.ending_value_usd == Decimal("109")
    assert res.fees == Decimal("-7")

    # Case 2: Fee already in return
    grid2 = run_usd_scenarios(exposures, r_prod, r_fx, opening_fx, fee_usd=fee_usd, fees_already_in_return=True)
    res2 = grid2[0][0]
    # end_usd = 100 * 1.1 = 110
    # end_cny = 770
    # fees_impact = 0
    assert res2.ending_value_usd == Decimal("110")
    assert res2.fees == Decimal("0")

def test_deduplication():
    """Test that exposures with same asset_id are prioritized."""
    exposures = [
        UsdExposure(Decimal("100"), ExposureRole.LOOKTHROUGH_ECONOMIC, asset_id="A1"),
        UsdExposure(Decimal("100"), ExposureRole.PAYOFF_CURRENCY, asset_id="A1"), # Higher priority
    ]
    r_prod = [Decimal("0")]
    r_fx = [Decimal("0.1")]
    opening_fx = Decimal("7.0")

    grid = run_usd_scenarios(exposures, r_prod, r_fx, opening_fx)
    res = grid[0][0]

    # Only the PAYOFF_CURRENCY one should be kept
    # ending_cny = 100 * 7 * 1.1 = 770
    assert res.ending_value_cny == Decimal("770")

def test_unknown_residual():
    """Verify UNKNOWN exposures are not shocked."""
    exposures = [UsdExposure(Decimal("100"), ExposureRole.UNKNOWN)]
    r_prod = [Decimal("0.5")]
    r_fx = [Decimal("0.5")]
    opening_fx = Decimal("7.0")

    grid = run_usd_scenarios(exposures, r_prod, r_fx, opening_fx)
    res = grid[0][0]

    assert res.ending_value_usd == Decimal("100")
    assert res.ending_value_cny == Decimal("700")
    assert res.cny_return == Decimal("0")

def test_relative_benchmark():
    exposures = [UsdExposure(Decimal("100"), ExposureRole.PAYOFF_CURRENCY)]
    r_prod = [Decimal("0.05")]
    r_fx = [Decimal("0")]
    opening_fx = Decimal("7.0")
    # opening_cny = 700. ending_cny = 100 * 1.05 * 7 = 735.
    # benchmark_return = 0.02. benchmark_ending_cny = 700 * 1.02 = 714
    # relative = 735 - 714 = 21

    grid = run_usd_scenarios(exposures, r_prod, r_fx, opening_fx, cny_benchmark_return=Decimal("0.02"))
    assert grid[0][0].relative_to_cny_benchmark == Decimal("21")

def test_invalid_inputs():
    with pytest.raises(ValueError, match="positive"):
        run_usd_scenarios([], [Decimal("0")], [Decimal("0")], Decimal("-1"))
    with pytest.raises(ValueError, match="empty"):
        run_usd_scenarios([], [], [Decimal("0")], Decimal("7"))
