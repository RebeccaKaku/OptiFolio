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
        repo.save_raw(frame, asset_id=symbol, source="test", currency="USD" if symbol != "510300" else "CNY")


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
