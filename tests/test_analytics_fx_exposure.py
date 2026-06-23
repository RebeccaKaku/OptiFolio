"""Tests for the FX exposure analytics module."""

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from src.analytics.fx_exposure import FxExposureAnalyzer, FxExposureItem, FxExposureReport
from src.core.valuation import FxRateProvider, ValuationEngine
from findata.store import MarketDataRepository
from src.domain import CashHolding, PositionValue, ValuationRequest
from src.services.portfolio_service_v2 import PortfolioServiceV2


# ── helpers ──────────────────────────────────────────────────────────

def _seed_repo(repo: MarketDataRepository):
    """Seed test price data for known test symbols."""
    dates = pd.date_range("2025-01-01", "2025-06-15", freq="B")
    base = pd.Series(range(len(dates)), index=dates) * 0.5

    datasets = {
        "equity.us.aapl": ("USD", 100.0),
        "equity.us.qqq":  ("USD", 200.0),
        "fund.cn.510300": ("CNY", 1.0),
    }
    for symbol, (currency, offset) in datasets.items():
        prices = offset + base
        frame = pd.DataFrame({
            "close": prices,
            "open": prices,
            "high": prices + 1,
            "low": prices - 1,
            "volume": [10000] * len(prices),
        }, index=dates)
        frame.index.name = "timestamp"
        repo.save_canonical(frame, asset_id=symbol, source="test", currency=currency)


def _make_fx_provider() -> FxRateProvider:
    return FxRateProvider(fallback_rates={
        ("USD", "CNY"): 7.2,
        ("CNY", "USD"): 0.139,
        ("EUR", "USD"): 1.1,
        ("USD", "EUR"): 0.91,
        ("EUR", "CNY"): 7.92,
        ("CNY", "EUR"): 0.1263,
    })


def _make_service(tmp_path: Path) -> PortfolioServiceV2:
    repo = MarketDataRepository(tmp_path / "foundation")
    _seed_repo(repo)
    fx = _make_fx_provider()
    engine = ValuationEngine(market_data=repo, fx_provider=fx)

    local_dir = tmp_path / "local"
    local_dir.mkdir()
    portfolio = {
        "cash": {"USD": 5000.0, "CNY": 10000.0},
        "positions": {"equity.us.aapl": 100, "equity.us.qqq": 50, "fund.cn.510300": 1000},
    }
    portfolio_path = local_dir / "portfolio.yaml"
    with open(portfolio_path, "w") as f:
        yaml.dump(portfolio, f)

    return PortfolioServiceV2(
        valuation_engine=engine,
        config_path=portfolio_path,
        base_currency="CNY",
    )


# ── unit tests: FxExposureAnalyzer ───────────────────────────────────

class TestFxExposureAnalyzer:
    """Unit tests for the FX exposure analyzer in isolation."""

    def test_docstring_contains_level0_warning(self):
        """The class docstring must clearly state the Level 0 limitation."""
        doc = FxExposureAnalyzer.__doc__
        assert doc is not None
        assert "Level 0" in doc
        assert "LABEL-LEVEL" in doc
        assert "does NOT look through" in doc
        assert "NEVER be presented as complete FX risk analysis" in doc

    def test_empty_portfolio(self):
        analyzer = FxExposureAnalyzer()
        report = analyzer.analyze(
            positions={},
            cash_breakdown={},
            base_currency="CNY",
            total_value=0.0,
            as_of=date(2025, 6, 15),
        )
        assert isinstance(report, FxExposureReport)
        assert report.total_value == 0.0
        assert report.exposures == []
        assert report.net_non_base_pct == 0.0

    def test_single_currency_all_base(self):
        analyzer = FxExposureAnalyzer()
        positions = {
            "fund.cn.510300": PositionValue(
                asset_id="fund.cn.510300", quantity=1000, price=4.0,
                currency="CNY", fx_rate=1.0, value_base=4000.0,
            ),
        }
        cash = {
            "CNY": CashHolding(currency="CNY", amount=1000.0, fx_rate=1.0, value_base=1000.0),
        }
        report = analyzer.analyze(
            positions=positions, cash_breakdown=cash,
            base_currency="CNY", total_value=5000.0,
            as_of=date(2025, 6, 15),
        )
        assert report.base_currency == "CNY"
        assert report.net_non_base_pct == 0.0
        assert len(report.exposures) == 1
        assert report.exposures[0].currency == "CNY"
        assert report.exposures[0].pct == 100.0
        assert "本币" in report.exposures[0].sensitivity_note

    def test_mixed_currencies(self):
        analyzer = FxExposureAnalyzer()
        positions = {
            "equity.us.aapl": PositionValue(
                asset_id="equity.us.aapl", quantity=100, price=150.0,
                currency="USD", fx_rate=7.2, value_base=108000.0,
            ),
            "fund.cn.510300": PositionValue(
                asset_id="fund.cn.510300", quantity=1000, price=4.0,
                currency="CNY", fx_rate=1.0, value_base=4000.0,
            ),
        }
        cash = {
            "USD": CashHolding(currency="USD", amount=5000.0, fx_rate=7.2, value_base=36000.0),
            "CNY": CashHolding(currency="CNY", amount=10000.0, fx_rate=1.0, value_base=10000.0),
        }
        total = 108000.0 + 4000.0 + 36000.0 + 10000.0  # 158000
        report = analyzer.analyze(
            positions=positions, cash_breakdown=cash,
            base_currency="CNY", total_value=total,
            as_of=date(2025, 6, 15),
        )

        # USD exposure: (108000 + 36000) / 158000 = 0.91139...  => 91.14%
        # CNY exposure: (4000 + 10000) / 158000 = 0.08860... => 8.86%
        assert len(report.exposures) == 2
        usd_item = next(e for e in report.exposures if e.currency == "USD")
        cny_item = next(e for e in report.exposures if e.currency == "CNY")

        assert usd_item.value_base == 144000.0
        assert usd_item.asset_ids == ["equity.us.aapl"]
        assert round(usd_item.pct, 1) == 91.1
        assert "USD/CNY" in usd_item.sensitivity_note

        assert cny_item.value_base == 14000.0
        assert cny_item.pct == pytest.approx(8.86, rel=0.01)

        assert report.net_non_base_pct == pytest.approx(91.14, rel=0.01)
        assert len(report.warnings) >= 1
        assert any("91.1%" in w for w in report.warnings)

    def test_multiple_assets_same_currency(self):
        analyzer = FxExposureAnalyzer()
        positions = {
            "equity.us.aapl": PositionValue(
                asset_id="equity.us.aapl", quantity=100, price=150.0,
                currency="USD", fx_rate=7.2, value_base=108000.0,
            ),
            "equity.us.qqq": PositionValue(
                asset_id="equity.us.qqq", quantity=50, price=300.0,
                currency="USD", fx_rate=7.2, value_base=108000.0,
            ),
        }
        report = analyzer.analyze(
            positions=positions, cash_breakdown={},
            base_currency="CNY", total_value=216000.0,
            as_of=date(2025, 6, 15),
        )
        assert len(report.exposures) == 1
        usd_item = report.exposures[0]
        assert usd_item.currency == "USD"
        assert set(usd_item.asset_ids) == {"equity.us.aapl", "equity.us.qqq"}
        assert usd_item.pct == 100.0

    def test_warnings_when_non_base_exceeds_threshold(self):
        analyzer = FxExposureAnalyzer()
        positions = {
            "equity.us.aapl": PositionValue(
                asset_id="equity.us.aapl", quantity=100, price=150.0,
                currency="USD", fx_rate=7.2, value_base=54000.0,
            ),
            "fund.cn.510300": PositionValue(
                asset_id="fund.cn.510300", quantity=1000, price=4.0,
                currency="CNY", fx_rate=1.0, value_base=40000.0,
            ),
        }
        total = 94000.0
        report = analyzer.analyze(
            positions=positions, cash_breakdown={},
            base_currency="CNY", total_value=total,
            as_of=date(2025, 6, 15),
        )
        # USD is ~57.4% > 20% threshold
        assert len(report.warnings) >= 1
        assert any("57.4" in w for w in report.warnings)

    def test_cash_only_portfolio(self):
        analyzer = FxExposureAnalyzer()
        cash = {
            "EUR": CashHolding(currency="EUR", amount=1000.0, fx_rate=7.92, value_base=7920.0),
        }
        report = analyzer.analyze(
            positions={}, cash_breakdown=cash,
            base_currency="CNY", total_value=7920.0,
            as_of=date(2025, 6, 15),
        )
        assert len(report.exposures) == 1
        assert report.exposures[0].currency == "EUR"
        assert report.exposures[0].pct == 100.0
        assert "EUR/CNY" in report.exposures[0].sensitivity_note

    def test_sensitivity_note_contains_value(self):
        analyzer = FxExposureAnalyzer()
        positions = {
            "equity.us.aapl": PositionValue(
                asset_id="equity.us.aapl", quantity=100, price=150.0,
                currency="USD", fx_rate=7.2, value_base=50000.0,
            ),
        }
        report = analyzer.analyze(
            positions=positions, cash_breakdown={},
            base_currency="CNY", total_value=50000.0,
            as_of=date(2025, 6, 15),
        )
        usd_item = report.exposures[0]
        assert "¥500.00" in usd_item.sensitivity_note  # 50000 * 0.01 = 500

    def test_to_dict_serializable(self):
        analyzer = FxExposureAnalyzer()
        positions = {
            "equity.us.aapl": PositionValue(
                asset_id="equity.us.aapl", quantity=100, price=150.0,
                currency="USD", fx_rate=7.2, value_base=108000.0,
            ),
        }
        cash = {
            "CNY": CashHolding(currency="CNY", amount=10000.0, fx_rate=1.0, value_base=10000.0),
        }
        report = analyzer.analyze(
            positions=positions, cash_breakdown=cash,
            base_currency="CNY", total_value=118000.0,
            as_of=date(2025, 6, 15),
        )
        d = report.to_dict()
        assert d["base_currency"] == "CNY"
        assert isinstance(d["as_of"], str)
        assert len(d["exposures"]) == 2
        for e in d["exposures"]:
            assert "currency" in e
            assert "pct" in e
            assert isinstance(e["asset_ids"], list)


# ── integration tests: PortfolioServiceV2 ────────────────────────────

class TestFxExposureIntegration:
    """Integration tests for FX exposure through PortfolioServiceV2."""

    def test_get_fx_exposure_report_via_service(self, tmp_path):
        svc = _make_service(tmp_path)
        result = svc.get_fx_exposure_report(
            as_of=date(2025, 6, 15), base_currency="CNY",
        )
        assert result["success"], f"FX report failed: {result.get('message')}"
        data = result["data"]
        assert data["base_currency"] == "CNY"
        assert data["total_value"] > 0
        assert len(data["exposures"]) >= 1

        currencies = {e["currency"] for e in data["exposures"]}
        assert "CNY" in currencies  # 510300 + CNY cash
        assert "USD" in currencies  # AAPL + QQQ + USD cash

        # Net non-base should be USD portion > 0
        assert data["net_non_base_pct"] > 0

    def test_get_fx_exposure_defaults_to_today(self, tmp_path):
        """When no as_of is given, defaults to date.today() — works with seeded data."""
        svc = _make_service(tmp_path)
        # Seed data covers up to 2025-06-15, so explicitly provide a date within range
        result = svc.get_fx_exposure_report(as_of=date(2025, 6, 15))
        assert result["success"], f"FX report failed: {result.get('message')}"
        assert result["data"]["total_value"] > 0

    def test_get_fx_exposure_handles_no_price_data(self, tmp_path):
        """When valuation fails due to no prices, FX exposure should fail gracefully."""
        repo = MarketDataRepository(tmp_path / "foundation")
        # No seed — empty repo
        engine = ValuationEngine(market_data=repo)
        svc = PortfolioServiceV2(valuation_engine=engine, base_currency="CNY")
        svc._holdings = {"UNKNOWN": 100}
        result = svc.get_fx_exposure_report(as_of=date(2020, 1, 1), base_currency="CNY")
        assert not result["success"]
        assert result["error_code"] == "NO_PRICE_DATA"

    def test_get_fx_exposure_all_cny(self, tmp_path):
        """Portfolio with only CNY assets should show 0% non-base."""
        repo = MarketDataRepository(tmp_path / "foundation")
        dates = pd.date_range("2025-01-01", "2025-06-15", freq="B")
        frame = pd.DataFrame({
            "close": 4.0 + pd.Series(range(len(dates)), index=dates) * 0.01,
            "open": 4.0, "high": 4.1, "low": 3.9,
            "volume": [10000] * len(dates),
        }, index=dates)
        frame.index.name = "timestamp"
        repo.save_canonical(frame, asset_id="fund.cn.510300", source="test", currency="CNY")

        fx = _make_fx_provider()
        engine = ValuationEngine(market_data=repo, fx_provider=fx)

        local_dir = tmp_path / "local"
        local_dir.mkdir()
        portfolio = {"cash": {"CNY": 50000.0}, "positions": {"fund.cn.510300": 1000}}
        portfolio_path = local_dir / "portfolio.yaml"
        with open(portfolio_path, "w") as f:
            yaml.dump(portfolio, f)

        svc = PortfolioServiceV2(
            valuation_engine=engine, config_path=portfolio_path, base_currency="CNY",
        )
        result = svc.get_fx_exposure_report(as_of=date(2025, 6, 15), base_currency="CNY")
        assert result["success"]
        data = result["data"]
        assert data["net_non_base_pct"] == 0.0
        assert len(data["warnings"]) == 0
