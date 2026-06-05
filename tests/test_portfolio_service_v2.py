"""Integration tests for PortfolioServiceV2."""

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.core.corporate_actions import CorporateActionProcessor
from src.core.fees import FeeProcessor
from src.core.portfolio_history import PortfolioHistoryTracker
from src.core.valuation import FxRateProvider, ValuationEngine
from src.data_foundation.repository import MarketDataRepository
from src.services.portfolio_service_v2 import PortfolioServiceV2


def _seed_repo(repo: MarketDataRepository):
    """Seed test price data for known test symbols."""
    dates = pd.date_range("2025-01-01", "2025-06-15", freq="B")
    prices = 100.0 + pd.Series(range(len(dates)), index=dates) * 0.5

    for symbol in ["AAPL", "QQQ", "510300"]:
        offset = 0
        if symbol == "QQQ":
            offset = 200
        elif symbol == "510300":
            offset = 1
        frame = pd.DataFrame({
            "close": [p + offset for p in prices],
            "open": [p + offset for p in prices],
            "high": [p + offset + 1 for p in prices],
            "low": [p + offset - 1 for p in prices],
            "volume": [10000] * len(prices),
        }, index=dates)
        frame.index.name = "timestamp"
        repo.save_canonical(frame, asset_id=symbol, source="test", currency="USD" if symbol != "510300" else "CNY")


def _make_temp_portfolio(tmp_path: Path) -> Path:
    """Write a minimal portfolio YAML to a temp directory."""
    portfolio = {
        "cash": {"USD": 5000.0, "CNY": 10000.0},
        "positions": {"AAPL": 100, "QQQ": 50},
    }
    portfolio_path = tmp_path / "portfolio.yaml"
    with open(portfolio_path, "w") as f:
        yaml.dump(portfolio, f)
    return portfolio_path


def _make_service(tmp_path: Path) -> PortfolioServiceV2:
    repo = MarketDataRepository(tmp_path / "foundation")
    _seed_repo(repo)

    fx = FxRateProvider(fallback_rates={
        ("USD", "CNY"): 7.2, ("CNY", "USD"): 0.139,
        ("USD", "EUR"): 0.91, ("EUR", "USD"): 1.1,
    })
    engine = ValuationEngine(market_data=repo, fx_provider=fx)

    local_dir = tmp_path / "local"
    local_dir.mkdir()
    portfolio_path = _make_temp_portfolio(local_dir)

    cap = CorporateActionProcessor(local_dir / "corporate_actions.yaml")
    fee = FeeProcessor()
    hist = PortfolioHistoryTracker(local_dir / "portfolio_history.parquet")

    return PortfolioServiceV2(
        valuation_engine=engine,
        corp_action_processor=cap,
        fee_processor=fee,
        history_tracker=hist,
        config_path=portfolio_path,
        base_currency="CNY",
    )


class TestPortfolioServiceV2:
    """Integration tests for the full portfolio service."""

    def test_get_value_returns_nav(self, tmp_path):
        svc = _make_service(tmp_path)
        result = svc.get_value(as_of=date(2025, 6, 15), base_currency="USD")

        assert result["success"], f"Valuation failed: {result.get('message')}"
        data = result["data"]
        assert data["base_currency"] == "USD"
        assert data["total_value"] > 5000  # AAPL + QQQ + cash
        assert len(data["positions"]) == 2
        assert "AAPL" in data["positions"]
        assert "QQQ" in data["positions"]
        assert "USD" in data["cash_breakdown"]
        assert "CNY" in data["cash_breakdown"]

    def test_get_value_specific_date(self, tmp_path):
        svc = _make_service(tmp_path)
        # Early date — should use prices from that date
        result = svc.get_value(as_of=date(2025, 1, 10), base_currency="USD")
        assert result["success"]
        data = result["data"]
        assert data["price_date"] is not None
        # price_date should be <= as_of
        assert data["price_date"] <= "2025-01-10"

    def test_get_value_history(self, tmp_path):
        svc = _make_service(tmp_path)
        result = svc.get_value_history(
            start=date(2025, 1, 5), end=date(2025, 1, 15), base_currency="USD",
        )
        assert result["success"]
        assert len(result["data"]["records"]) > 0

    def test_current_holdings(self, tmp_path):
        svc = _make_service(tmp_path)
        result = svc.get_current_holdings()
        assert result["success"]
        assert result["data"]["holdings"]["AAPL"] == 100
        assert result["data"]["holdings"]["QQQ"] == 50
        assert result["data"]["cash"]["USD"] == 5000

    def test_cash_balances(self, tmp_path):
        svc = _make_service(tmp_path)
        result = svc.get_cash_balances()
        assert result["success"]
        assert result["data"]["cash"]["CNY"] == 10000

    def test_record_and_apply_dividend(self, tmp_path):
        svc = _make_service(tmp_path)
        div_result = svc.record_dividend(
            "AAPL", date(2025, 6, 10), amount_per_share=1.0, currency="USD",
        )
        assert div_result["success"]

        # Value after dividend ex-date — holdings unchanged in PortfolioServiceV2
        # because corporate actions are only applied in get_value_history()
        holdings = svc.get_current_holdings()
        assert holdings["data"]["holdings"]["AAPL"] == 100  # holdings unchanged

    def test_metrics_computed(self, tmp_path):
        svc = _make_service(tmp_path)
        # Record a few valuations to build history
        for d in [date(2025, 1, 5), date(2025, 1, 10), date(2025, 1, 15)]:
            svc.get_value(as_of=d, base_currency="USD")

        metrics = svc.compute_metrics()
        assert metrics["success"]
        assert metrics["data"]["num_observations"] >= 3
        # With positive price trend, expect positive return
        assert metrics["data"]["total_return"] > 0

    def test_get_history(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.get_value(as_of=date(2025, 1, 10), base_currency="USD")
        svc.get_value(as_of=date(2025, 1, 15), base_currency="USD")

        result = svc.get_history()
        assert result["success"]
        assert result["data"]["count"] >= 2

    def test_empty_portfolio_no_config(self, tmp_path):
        """When no config file exists, should start with empty holdings."""
        repo = MarketDataRepository(tmp_path / "foundation")
        engine = ValuationEngine(market_data=repo)
        svc = PortfolioServiceV2(
            valuation_engine=engine,
            config_path=tmp_path / "nonexistent.yaml",
        )
        holdings = svc.get_current_holdings()
        assert holdings["data"]["holdings"] == {}
        assert holdings["data"]["cash"] == {}

    # ── history tracker & enhanced metrics ────────────────────────────────

    def test_enhanced_metrics_all_fields_present(self, tmp_path):
        """After recording valuations, compute_metrics returns all fields."""
        svc = _make_service(tmp_path)
        # Build a richer history: valuations every few days
        for d in [
            date(2025, 1, 5),
            date(2025, 1, 10),
            date(2025, 1, 20),
            date(2025, 1, 30),
            date(2025, 2, 5),
            date(2025, 2, 15),
            date(2025, 3, 1),
            date(2025, 3, 15),
        ]:
            svc.get_value(as_of=d, base_currency="USD")

        result = svc.compute_metrics()
        assert result["success"]
        data = result["data"]

        # All expected keys present
        expected_keys = {
            "total_return", "annualized_return", "volatility",
            "sharpe_ratio", "max_drawdown", "sortino_ratio",
            "calmar_ratio", "win_rate", "best_day", "worst_day",
            "avg_daily_return", "std_daily_return", "num_observations",
        }
        assert set(data.keys()) == expected_keys

        assert data["num_observations"] >= 8
        assert isinstance(data["total_return"], (int, float))
        assert isinstance(data["sortino_ratio"], (int, float))
        assert isinstance(data["calmar_ratio"], (int, float))
        assert isinstance(data["win_rate"], (int, float))
        assert isinstance(data["best_day"], (int, float))
        assert isinstance(data["worst_day"], (int, float))
        assert isinstance(data["avg_daily_return"], (int, float))
        assert isinstance(data["std_daily_return"], (int, float))

        # With strictly increasing prices, win_rate should be high
        assert data["win_rate"] > 0.5

    def test_rolling_metrics_with_sufficient_data(self, tmp_path):
        """Rolling metrics return a DataFrame with expected columns and values."""
        from src.domain import (
            PortfolioHistoryEntry,
            ValuationResult,
        )

        # Build a tracker with synthetic daily data over ~120 days
        tracker = PortfolioHistoryTracker(
            storage_path=tmp_path / "rolling_test.parquet",
        )

        dates = pd.date_range("2025-01-01", periods=120, freq="B")
        import numpy as np
        rng = np.random.default_rng(42)
        # Random walk: starts at 100000, drifts up with noise
        noise = rng.normal(0.0002, 0.01, len(dates))
        values = 100000.0 * np.cumprod(1 + noise)

        for i, d in enumerate(dates):
            entry = PortfolioHistoryEntry(
                date=d.date(),
                total_value=float(values[i]),
                holdings_value=float(values[i] * 0.8),
                cash_value=float(values[i] * 0.2),
                base_currency="USD",
                num_positions=2,
            )
            row = pd.DataFrame([entry.to_dict()])
            row["date"] = pd.to_datetime(row["date"])
            if tracker._df.empty:
                tracker._df = row
            else:
                tracker._df = pd.concat([tracker._df, row], ignore_index=True)

        tracker._df = tracker._df.sort_values("date").reset_index(drop=True)

        # Compute rolling metrics with 60-day window
        result = tracker.compute_rolling_metrics(window_days=60)

        assert isinstance(result, pd.DataFrame)
        assert not result.empty
        expected_cols = {
            "date", "rolling_sharpe", "rolling_volatility", "rolling_max_drawdown",
        }
        assert set(result.columns) == expected_cols
        assert len(result) == 120

        # Early windows (fewer than 3 data points) should have zeros
        # Later windows should have meaningful (non-zero) volatility
        later = result.iloc[-30:]
        non_zero_vol = (later["rolling_volatility"] != 0).sum()
        assert non_zero_vol > 0, "Expected non-zero rolling volatility in later windows"

        # Max drawdown should be <= 0 (or 0)
        assert (result["rolling_max_drawdown"] <= 0).all()

    def test_empty_history_returns_zeros(self, tmp_path):
        """compute_metrics on an empty tracker returns zeros for all fields."""
        tracker = PortfolioHistoryTracker(
            storage_path=tmp_path / "empty_test.parquet",
        )
        metrics = tracker.compute_metrics()

        assert metrics["num_observations"] == 0
        for key in [
            "total_return", "annualized_return", "volatility",
            "sharpe_ratio", "max_drawdown", "sortino_ratio",
            "calmar_ratio", "win_rate", "best_day", "worst_day",
            "avg_daily_return", "std_daily_return",
        ]:
            assert metrics[key] == 0.0, f"Expected {key}=0.0, got {metrics[key]}"

    def test_rolling_metrics_empty_tracker(self, tmp_path):
        """compute_rolling_metrics on an empty tracker returns empty DataFrame."""
        tracker = PortfolioHistoryTracker(
            storage_path=tmp_path / "empty_rolling.parquet",
        )
        result = tracker.compute_rolling_metrics(window_days=60)

        assert isinstance(result, pd.DataFrame)
        assert result.empty
        expected_cols = {
            "date", "rolling_sharpe", "rolling_volatility", "rolling_max_drawdown",
        }
        assert set(result.columns) == expected_cols

    def test_get_exposure_report(self, tmp_path):
        """End-to-end exposure report through PortfolioServiceV2."""
        svc = _make_service(tmp_path)
        result = svc.get_exposure_report(as_of=date(2025, 6, 15), base_currency="CNY")

        assert result["success"], f"Exposure report failed: {result.get('message')}"
        data = result["data"]
        assert "by_asset_class" in data
        assert "by_currency" in data
        assert data["total_value"] > 0

        # Asset class breakdown
        ac_buckets = {item["bucket"]: item for item in data["by_asset_class"]}
        assert "equity" in ac_buckets
        # Cash should appear as its own bucket, not as a pseudo-symbol
        assert "cash" in ac_buckets

        # Currency breakdown
        cur_buckets = {item["bucket"]: item for item in data["by_currency"]}
        assert "USD" in cur_buckets
        assert "CNY" in cur_buckets

        # Verify cash does NOT leak into asset_ids as pseudo-symbols
        for item in data["by_asset_class"]:
            for asset_id in item.get("asset_ids", []):
                assert not asset_id.startswith("CASH:")
