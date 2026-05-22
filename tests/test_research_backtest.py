import pandas as pd

from src.research import BacktestEngine, BacktestRequest


def test_backtest_engine_runs_static_asset_allocation():
    prices = pd.DataFrame(
        {
            "AAA": [100, 101, 102, 104],
            "BBB": [50, 50, 51, 51],
        },
        index=pd.date_range("2024-01-01", periods=4, freq="D"),
    )

    result = BacktestEngine().run(
        BacktestRequest(prices=prices, target_weights={"AAA": 0.6, "BBB": 0.4})
    )

    payload = result.to_dict()
    assert payload["engine"] in ["vectorbt", "pandas-fallback"]
    assert result.metrics["total_return"] > 0
    assert set(result.asset_contribution) == {"AAA", "BBB"}


def test_backtest_engine_reports_engine_type():
    prices = pd.DataFrame(
        {
            "AAA": [100, 101, 102, 104],
        },
        index=pd.date_range("2024-01-01", periods=4, freq="D"),
    )

    # Test with vectorbt (assuming it is available since we installed it)
    engine = BacktestEngine()
    result = engine.run(BacktestRequest(prices=prices, target_weights={"AAA": 1.0}))
    assert result.engine in ["vectorbt", "pandas-fallback"]

    # If we want to specifically test fallback, we can mock VECTORBT_AVAILABLE
    import src.research.backtest as backtest
    original_available = backtest.VECTORBT_AVAILABLE
    try:
        backtest.VECTORBT_AVAILABLE = False
        result_fallback = engine.run(
            BacktestRequest(prices=prices, target_weights={"AAA": 1.0})
        )
        assert result_fallback.engine == "pandas-fallback"
    finally:
        backtest.VECTORBT_AVAILABLE = original_available


def test_backtest_engine_weight_alignment():
    # AAA is going up, BBB is flat.
    # If weights are swapped (AAA 0, BBB 1), return will be 0.
    # If weights are correct (AAA 1, BBB 0), return will be positive.
    prices = pd.DataFrame(
        {
            "AAA": [100, 101, 102, 104],
            "BBB": [50, 50, 50, 50],
        },
        index=pd.date_range("2024-01-01", periods=4, freq="D"),
    )

    # Intentionally use a weight dict with different order/subset
    # to ensure label-based alignment
    weights = {"BBB": 0.0, "AAA": 1.0}

    engine = BacktestEngine()
    result = engine.run(BacktestRequest(prices=prices, target_weights=weights))

    assert result.metrics["total_return"] > 0.03  # AAA return is 4%
    assert result.asset_contribution["AAA"] > 0
    assert result.asset_contribution["BBB"] == 0
