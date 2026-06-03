"""Tests for ValuationEngine — date-aware portfolio valuation."""

from datetime import date

import pandas as pd
import pytest

from src.core.valuation import (
    FxRateProvider,
    NoPriceDataError,
    ValuationEngine,
)
from src.data_foundation.repository import MarketDataRepository
from src.domain import ValuationRequest


# ── Helpers ────────────────────────────────────────────────────────────


def _seed_prices(repo: MarketDataRepository, assets: list[str], dates: list[str]) -> None:
    """Seed test price data into a repository."""
    for asset in assets:
        frame = pd.DataFrame(
            {
                "close": [100.0 + i + (10 * assets.index(asset)) for i in range(len(dates))],
                "open": [100.0] * len(dates),
                "high": [101.0] * len(dates),
                "low": [99.0] * len(dates),
                "volume": [1000] * len(dates),
            },
            index=pd.to_datetime(dates),
        )
        frame.index.name = "timestamp"
        repo.save_raw(frame, asset_id=asset, source="test", currency="USD")


def _make_engine(tmp_path):
    """Create a ValuationEngine with a tmp_path-backed repository."""
    repo = MarketDataRepository(tmp_path)
    fx = FxRateProvider(fallback_rates={
        ("USD", "CNY"): 7.2,
        ("CNY", "USD"): 0.139,
        ("EUR", "CNY"): 7.9,
    })
    return ValuationEngine(market_data=repo, fx_provider=fx)


# ── Tests ──────────────────────────────────────────────────────────────


class TestValuationEngine:
    """Core valuation logic."""

    def test_single_asset_single_date(self, tmp_path):
        engine = _make_engine(tmp_path)
        _seed_prices(engine.market_data, ["AAPL"], ["2025-01-13", "2025-01-14", "2025-01-15"])

        result = engine.value(
            {"AAPL": 10},
            {"USD": 500},
            ValuationRequest(as_of=date(2025, 1, 15), base_currency="USD"),
        )

        assert result.total_value == pytest.approx(10 * 102.0 + 500)
        assert result.holdings_value == pytest.approx(1020.0)
        assert result.cash_value == pytest.approx(500.0)
        assert result.base_currency == "USD"
        assert result.positions["AAPL"].price == 102.0
        assert result.positions["AAPL"].quantity == 10
        assert result.price_date == date(2025, 1, 15)

    def test_next_day_nav_convention(self, tmp_path):
        """value_on(T+1) uses T's close price."""
        engine = _make_engine(tmp_path)
        _seed_prices(engine.market_data, ["QQQ"], ["2025-06-02", "2025-06-03"])

        # Ask for value on 2025-06-04 → uses 06-03 close
        result = engine.value(
            {"QQQ": 5}, {"USD": 0},
            ValuationRequest(as_of=date(2025, 6, 4), base_currency="USD"),
        )

        assert result.price_date == date(2025, 6, 3)
        assert result.positions["QQQ"].price == 101.0

    def test_multi_asset_multi_currency(self, tmp_path):
        engine = _make_engine(tmp_path)
        _seed_prices(engine.market_data, ["AAPL"], ["2025-01-15"])
        _seed_prices(engine.market_data, ["510300"], ["2025-01-15"])

        result = engine.value(
            {"AAPL": 10, "510300": 100},
            {"USD": 500, "CNY": 10000},
            ValuationRequest(as_of=date(2025, 1, 15), base_currency="CNY"),
        )

        # AAPL: 10 * 100 * 7.2 = 7200 CNY
        # 510300: 100 * 110 * 1.0 = 11000 CNY (assuming same currency)
        # USD cash: 500 * 7.2 = 3600 CNY
        # CNY cash: 10000 * 1.0 = 10000 CNY
        assert result.base_currency == "CNY"
        assert "AAPL" in result.positions
        assert "510300" in result.positions

    def test_empty_holdings_returns_cash_only(self, tmp_path):
        engine = _make_engine(tmp_path)
        result = engine.value(
            {}, {"USD": 1000},
            ValuationRequest(as_of=date(2025, 6, 3), base_currency="USD"),
        )

        assert result.holdings_value == 0.0
        assert result.total_value == 1000.0
        assert len(result.positions) == 0

    def test_raises_when_no_price_data(self, tmp_path):
        engine = _make_engine(tmp_path)
        with pytest.raises(NoPriceDataError):
            engine.value(
                {"UNKNOWN": 100}, {"USD": 0},
                ValuationRequest(as_of=date(2025, 6, 3), base_currency="USD"),
            )

    def test_lookback_walks_to_prior_date(self, tmp_path):
        """If T has no price but T-1 does, use T-1."""
        engine = _make_engine(tmp_path)
        _seed_prices(engine.market_data, ["AAPL"], ["2025-01-10"])

        # Ask for value on 2025-01-15 → should find 01-10 (within 5 days)
        result = engine.value(
            {"AAPL": 10}, {"USD": 0},
            ValuationRequest(as_of=date(2025, 1, 15), base_currency="USD"),
        )
        assert result.price_date == date(2025, 1, 10)

    def test_raises_when_price_too_old(self, tmp_path):
        """If most recent price is > max_lookback_days, raise error."""
        engine = _make_engine(tmp_path)
        _seed_prices(engine.market_data, ["AAPL"], ["2025-01-01"])

        with pytest.raises(NoPriceDataError):
            engine.value(
                {"AAPL": 10}, {"USD": 0},
                ValuationRequest(as_of=date(2025, 1, 15), base_currency="USD"),
            )

    def test_value_history(self, tmp_path):
        engine = _make_engine(tmp_path)
        _seed_prices(
            engine.market_data, ["AAPL"],
            [f"2025-01-{d:02d}" for d in range(10, 16)]
        )

        dates = [date(2025, 1, d) for d in range(12, 16)]
        results = engine.value_history(
            {"AAPL": 10}, {"USD": 0}, dates, base_currency="USD",
        )
        assert len(results) == 4
        assert results[0].as_of == date(2025, 1, 12)

    def test_to_dict_roundtrip(self, tmp_path):
        engine = _make_engine(tmp_path)
        _seed_prices(engine.market_data, ["AAPL"], ["2025-01-15"])

        result = engine.value(
            {"AAPL": 10}, {"USD": 500},
            ValuationRequest(as_of=date(2025, 1, 15), base_currency="USD"),
        )

        d = result.to_dict()
        assert d["as_of"] == "2025-01-15"
        assert "AAPL" in d["positions"]
        assert d["positions"]["AAPL"]["quantity"] == 10
        assert d["positions"]["AAPL"]["price"] == 100.0
        assert "USD" in d["cash_breakdown"]


class TestFxRateProvider:
    """Currency conversion logic."""

    def test_same_currency_returns_one(self):
        fx = FxRateProvider()
        assert fx.get_rate("USD", "USD") == 1.0
        assert fx.get_rate("CNY", "CNY") == 1.0

    def test_fallback_rate_direct(self):
        fx = FxRateProvider()
        assert fx.get_rate("USD", "CNY") == 7.2

    def test_cache_reuse(self):
        fx = FxRateProvider()
        r1 = fx.get_rate("EUR", "USD")
        r2 = fx.get_rate("EUR", "USD")
        assert r1 == r2  # same cached value
