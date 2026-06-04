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


# ── Merged from test_fx_data.py ──

"""Tests for FX rate resolution via MarketDataRepository and FxRateProvider."""

from datetime import date

import pandas as pd

from src.core.valuation import FxRateProvider, FxRateError
from src.data_foundation.repository import MarketDataRepository


# ── Helpers ───────────────────────────────────────────────────────────────

def _seed_fx_data(repo: MarketDataRepository) -> None:
    """Seed the repository with a few days of USD/CNY and EUR/CNY rates."""
    # USD/CNY: 7.18 .. 7.20
    usd = pd.DataFrame({
        "date": ["2025-06-02", "2025-06-03", "2025-06-04"],
        "close": [7.1848, 7.1763, 7.1886],
    })
    repo.save_raw(usd, asset_id="FX_USDCNY", source="test", currency="CNY")

    # EUR/CNY: 8.18 .. 8.20
    eur = pd.DataFrame({
        "date": ["2025-06-02", "2025-06-03", "2025-06-04"],
        "close": [8.1830, 8.1853, 8.1920],
    })
    repo.save_raw(eur, asset_id="FX_EURCNY", source="test", currency="CNY")


# ── Tests ─────────────────────────────────────────────────────────────────


class TestFxRateFromRepository:
    """Tests for get_rate_from_repository."""

    def test_retrieves_dated_rate_exact_date(self, tmp_path):
        """Rate on the exact date stored in the repository."""
        repo = MarketDataRepository(tmp_path)
        _seed_fx_data(repo)

        provider = FxRateProvider(market_data=repo)
        rate = provider.get_rate_from_repository("USD", "CNY", date(2025, 6, 3))

        assert rate == 7.1763

    def test_retrieves_rate_with_lookback(self, tmp_path):
        """Rate on a weekend — should walk back to Friday."""
        repo = MarketDataRepository(tmp_path)
        _seed_fx_data(repo)

        # 2025-06-07 is a Saturday; last available is 2025-06-04 (Thursday)
        provider = FxRateProvider(market_data=repo)
        rate = provider.get_rate_from_repository("USD", "CNY", date(2025, 6, 7))

        assert rate == 7.1886

    def test_retrieves_euro_rate(self, tmp_path):
        """EUR/CNY retrieval works independently."""
        repo = MarketDataRepository(tmp_path)
        _seed_fx_data(repo)

        provider = FxRateProvider(market_data=repo)
        rate = provider.get_rate_from_repository("EUR", "CNY", date(2025, 6, 3))

        assert rate == 8.1853

    def test_same_currency_returns_one(self, tmp_path):
        """Same currency always returns 1.0 without querying the repo."""
        repo = MarketDataRepository(tmp_path)
        provider = FxRateProvider(market_data=repo)

        rate = provider.get_rate_from_repository("CNY", "CNY", date(2025, 6, 3))
        assert rate == 1.0

        rate = provider.get_rate_from_repository("USD", "USD", date(2025, 6, 3))
        assert rate == 1.0


class TestFxRateFallback:
    """Tests for fallback behaviour when repository has no matching data."""

    def test_falls_back_when_pair_not_in_repo(self, tmp_path):
        """When the FX pair is not in the repo, fall back to hardcoded."""
        repo = MarketDataRepository(tmp_path)
        _seed_fx_data(repo)  # only USDCNY and EURCNY

        provider = FxRateProvider(market_data=repo)
        # JPY/CNY is not in the seeded data, should fall back
        rate = provider.get_rate_from_repository("USD", "JPY", date(2025, 6, 3))

        # Fallback: USD→JPY hardcoded is 150
        assert rate == 150

    def test_falls_back_when_date_too_old(self, tmp_path):
        """When the requested date is before any stored data, fall back."""
        repo = MarketDataRepository(tmp_path)
        _seed_fx_data(repo)  # data starts 2025-06-02

        provider = FxRateProvider(market_data=repo)
        # Date far before any data, lookback of 5 days won't reach it
        rate = provider.get_rate_from_repository("USD", "CNY", date(2020, 1, 1))

        # Falls back to hardcoded USD→CNY = 7.2
        assert rate == 7.2

    def test_falls_back_when_repo_is_none(self, tmp_path):
        """When market_data is None, falls back to existing get_rate logic."""
        provider = FxRateProvider(market_data=None)

        rate = provider.get_rate_from_repository("USD", "CNY", date(2025, 6, 3))
        assert rate == 7.2  # hardcoded fallback

        rate = provider.get_rate_from_repository("EUR", "USD", date(2025, 6, 3))
        assert rate == 1.1  # hardcoded fallback

    def test_falls_back_when_repo_has_empty_parquet(self, tmp_path):
        """Repository exists but has no data at all."""
        repo = MarketDataRepository(tmp_path)
        # Don't seed anything

        provider = FxRateProvider(market_data=repo)
        rate = provider.get_rate_from_repository("USD", "CNY", date(2025, 6, 3))

        assert rate == 7.2  # hardcoded fallback


class TestFxRateProviderBackwardCompat:
    """The existing get_rate() API still works as before."""

    def test_get_rate_still_works_without_repo(self):
        """get_rate() is unchanged and works without a repo."""
        provider = FxRateProvider()

        assert provider.get_rate("USD", "CNY") == 7.2
        assert provider.get_rate("CNY", "USD") == 0.139
        assert provider.get_rate("USD", "EUR") == 0.91
        assert provider.get_rate("USD", "JPY") == 150

    def test_get_rate_same_currency(self):
        provider = FxRateProvider()
        assert provider.get_rate("CNY", "CNY") == 1.0

    def test_get_rate_transitive_via_usd(self):
        """EUR→CNY via USD: EUR→USD (1.1) * USD→CNY (7.2) = 7.92."""
        provider = FxRateProvider()
        rate = provider.get_rate("EUR", "CNY")
        assert rate == 1.1 * 7.2  # 7.92

    def test_get_rate_raises_for_unknown(self):
        provider = FxRateProvider()
        # Remove fallbacks to force error
        provider._fallback = {}
        from src.core.valuation import FxRateError
        import pytest
        with pytest.raises(FxRateError):
            provider.get_rate("XXX", "YYY")

    def test_constructor_accepts_market_data(self):
        """FxRateProvider(market_data=repo) works without errors."""
        repo = MarketDataRepository()
        provider = FxRateProvider(market_data=repo)
        assert provider.market_data is repo

    def test_constructor_without_market_data(self):
        """FxRateProvider() remains backward-compatible."""
        provider = FxRateProvider()
        assert provider.market_data is None
