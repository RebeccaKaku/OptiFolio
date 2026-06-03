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
