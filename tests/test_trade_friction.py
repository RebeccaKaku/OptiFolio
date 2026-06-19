from decimal import Decimal
from src.analytics.trade_friction import (
    AllocationFrictionInput,
    TradeFrictionRequest,
    calculate_trade_friction
)

def test_friction_zero_fees():
    fi = AllocationFrictionInput(
        buy_fee_rate=Decimal("0"),
        sell_fee_rate=Decimal("0"),
        mgmt_fee_diff_rate=Decimal("0"),
        fixed_fees=Decimal("0"),
        fx_spread_rate=Decimal("0")
    )
    req = TradeFrictionRequest(
        amount_reporting=Decimal("10000"),
        total_portfolio_value_reporting=Decimal("1000000"),
        expected_holding_period_years=Decimal("1.0"),
        reporting_currency="CNY",
        friction_input=fi
    )
    res = calculate_trade_friction(req)
    assert res.total_known_cost_amount == 0
    assert not res.no_trade
    assert res.eligible_allocations == Decimal("10000")

def test_friction_proportional_and_fixed():
    fi = AllocationFrictionInput(
        buy_fee_rate=Decimal("0.001"),  # 0.1%
        fixed_fees=Decimal("5"),
        fx_spread_rate=Decimal("0.002"), # 0.2%
        sell_fee_rate=Decimal("0"),
        mgmt_fee_diff_rate=Decimal("0")
    )
    req = TradeFrictionRequest(
        amount_reporting=Decimal("10000"),
        total_portfolio_value_reporting=Decimal("1000000"),
        expected_holding_period_years=Decimal("1.0"),
        reporting_currency="CNY",
        friction_input=fi
    )
    res = calculate_trade_friction(req)
    # 10000 * (0.001 + 0.002) + 5 = 10000 * 0.003 + 5 = 30 + 5 = 35
    assert res.total_known_cost_amount == Decimal("35")
    assert not res.no_trade

def test_no_trade_band():
    fi = AllocationFrictionInput(
        no_trade_band_pct=Decimal("0.01"), # 1%
        buy_fee_rate=Decimal("0"),
        sell_fee_rate=Decimal("0"),
        mgmt_fee_diff_rate=Decimal("0"),
        fixed_fees=Decimal("0"),
        fx_spread_rate=Decimal("0")
    )
    # Deviation 0.5% < 1%
    req = TradeFrictionRequest(
        amount_reporting=Decimal("5000"),
        total_portfolio_value_reporting=Decimal("1000000"),
        expected_holding_period_years=Decimal("1.0"),
        reporting_currency="CNY",
        friction_input=fi
    )
    res = calculate_trade_friction(req)
    assert res.no_trade
    assert "within no-trade band" in res.reasons[0]
    assert res.eligible_allocations == 0

def test_min_trade_amount():
    fi = AllocationFrictionInput(
        min_trade_amount=Decimal("1000"),
        buy_fee_rate=Decimal("0"),
        sell_fee_rate=Decimal("0"),
        mgmt_fee_diff_rate=Decimal("0"),
        fixed_fees=Decimal("0"),
        fx_spread_rate=Decimal("0")
    )
    req = TradeFrictionRequest(
        amount_reporting=Decimal("500"),
        total_portfolio_value_reporting=Decimal("1000000"),
        expected_holding_period_years=Decimal("1.0"),
        reporting_currency="CNY",
        friction_input=fi
    )
    res = calculate_trade_friction(req)
    assert res.no_trade
    assert "below minimum" in res.reasons[0]

def test_cost_vs_benefit():
    fi = AllocationFrictionInput(
        buy_fee_rate=Decimal("0.01"), # 1% cost
        sell_fee_rate=Decimal("0"),
        mgmt_fee_diff_rate=Decimal("0"),
        fixed_fees=Decimal("0"),
        fx_spread_rate=Decimal("0")
    )
    # Benefit 0.5% < 1% cost
    req = TradeFrictionRequest(
        amount_reporting=Decimal("10000"),
        total_portfolio_value_reporting=Decimal("1000000"),
        expected_holding_period_years=Decimal("1.0"),
        reporting_currency="CNY",
        monetized_benefit_annual_rate=Decimal("0.005"),
        friction_input=fi
    )
    res = calculate_trade_friction(req)
    assert res.no_trade
    assert "does not exceed costs" in res.reasons[0]
    assert res.monetized_benefit == Decimal("50")
    assert res.total_known_cost_amount == Decimal("100")
    assert res.net_monetized_benefit == Decimal("-50")

def test_break_even_horizon():
    fi = AllocationFrictionInput(
        buy_fee_rate=Decimal("0.02"), # 2% one-time
        mgmt_fee_diff_rate=Decimal("0.01"), # 1% extra annual cost
        sell_fee_rate=Decimal("0"),
        fixed_fees=Decimal("0"),
        fx_spread_rate=Decimal("0")
    )
    # Benefit 5% annual
    # Net annual benefit = 5% - 1% = 4%
    # Break-even = 2% / 4% = 0.5 years
    req = TradeFrictionRequest(
        amount_reporting=Decimal("10000"),
        total_portfolio_value_reporting=Decimal("1000000"),
        expected_holding_period_years=Decimal("1.0"),
        reporting_currency="CNY",
        monetized_benefit_annual_rate=Decimal("0.05"),
        friction_input=fi
    )
    res = calculate_trade_friction(req)
    assert res.break_even_horizon == Decimal("0.5")

def test_unknown_critical_costs():
    fi = AllocationFrictionInput(
        buy_fee_rate=None, # UNKNOWN
        sell_fee_rate=Decimal("0"),
        mgmt_fee_diff_rate=Decimal("0"),
        fixed_fees=Decimal("0"),
        fx_spread_rate=Decimal("0")
    )
    req = TradeFrictionRequest(
        amount_reporting=Decimal("10000"),
        total_portfolio_value_reporting=Decimal("1000000"),
        expected_holding_period_years=Decimal("1.0"),
        reporting_currency="CNY",
        friction_input=fi
    )
    res = calculate_trade_friction(req)
    assert res.no_trade
    assert "Critical costs unknown" in res.reasons[0]
    assert "buy_fee_rate" in res.unknown_costs

def test_lock_up_period():
    fi = AllocationFrictionInput(
        lock_up_days=366,
        buy_fee_rate=Decimal("0"),
        sell_fee_rate=Decimal("0"),
        mgmt_fee_diff_rate=Decimal("0"),
        fixed_fees=Decimal("0"),
        fx_spread_rate=Decimal("0")
    )
    # Holding period 1 year (365 days) < 366 days lockup
    req = TradeFrictionRequest(
        amount_reporting=Decimal("10000"),
        total_portfolio_value_reporting=Decimal("1000000"),
        expected_holding_period_years=Decimal("1.0"),
        reporting_currency="CNY",
        friction_input=fi
    )
    res = calculate_trade_friction(req)
    assert res.no_trade
    assert "Lock-up period" in res.reasons[0]
