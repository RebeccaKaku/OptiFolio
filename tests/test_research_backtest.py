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
    assert payload["engine"] == "vectorbt-compatible"
    assert result.metrics["total_return"] > 0
    assert set(result.asset_contribution) == {"AAA", "BBB"}
