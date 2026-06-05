"""Tests for concentration risk analyzer."""

from __future__ import annotations

from dataclasses import is_dataclass
from datetime import date

import pytest

from src.analytics.concentration import (
    ConcentrationAnalyzer,
    ConcentrationItem,
    ConcentrationReport,
    _map_asset_class,
)
from src.domain import PositionValue


# ── Helpers ───────────────────────────────────────────────────────────────

def _pos(asset_id: str, value_base: float, currency: str = "USD", price_date: date = None) -> PositionValue:
    """Shortcut for creating a test PositionValue."""
    return PositionValue(
        asset_id=asset_id,
        quantity=1.0,
        price=value_base,
        currency=currency,
        fx_rate=1.0,
        value_base=value_base,
        price_date=price_date or date(2026, 6, 1),
        stale_days=0,
    )


def _assert_frozen(obj: object) -> None:
    from dataclasses import FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        obj._test_field = "should_fail"  # type: ignore[attr-defined]


# ── _map_asset_class ──────────────────────────────────────────────────────


class TestMapAssetClass:
    def test_equity_types(self):
        assert _map_asset_class("us_equity") == "equity"
        assert _map_asset_class("cn_stock") == "equity"
        assert _map_asset_class("cn_stock_sh") == "equity"
        assert _map_asset_class("hk_equity") == "equity"
        assert _map_asset_class("equity") == "equity"

    def test_fund_types(self):
        assert _map_asset_class("fund") == "fund"
        assert _map_asset_class("etf") == "fund"
        assert _map_asset_class("mutual_fund") == "fund"
        assert _map_asset_class("bond_fund") == "fund"
        assert _map_asset_class("money_market_fund") == "fund"

    def test_bond_types(self):
        assert _map_asset_class("bond") == "bond"
        assert _map_asset_class("government_bond") == "bond"
        assert _map_asset_class("corporate_bond") == "bond"
        assert _map_asset_class("convertible_bond") == "bond"

    def test_bank_wmp(self):
        assert _map_asset_class("bank_wmp") == "bank_wmp"
        assert _map_asset_class("bank_deposit") == "bank_wmp"

    def test_cash_types(self):
        assert _map_asset_class("cash") == "cash"
        assert _map_asset_class("currency") == "cash"
        assert _map_asset_class("money_market") == "cash"
        assert _map_asset_class("deposit") == "cash"

    def test_fallback_heuristic(self):
        assert _map_asset_class("some_stock") == "equity"
        assert _map_asset_class("growth_fund_x") == "fund"
        assert _map_asset_class("corp_bond_2025") == "bond"

    def test_unknown(self):
        assert _map_asset_class("") == "unknown"
        assert _map_asset_class("something_unusual") == "other"


# ── ConcentrationItem ─────────────────────────────────────────────────────


class TestConcentrationItem:
    def test_construction(self):
        item = ConcentrationItem(
            dimension="currency",
            key="USD",
            value=100000.0,
            pct=0.6,
            asset_ids=["AAPL", "MSFT"],
        )
        assert item.dimension == "currency"
        assert item.key == "USD"
        assert item.value == 100000.0
        assert item.pct == 0.6
        assert item.asset_ids == ["AAPL", "MSFT"]
        assert is_dataclass(item)
        _assert_frozen(item)

    def test_to_dict(self):
        item = ConcentrationItem(
            dimension="issuer",
            key="Apple Inc.",
            value=50000.0,
            pct=0.3,
            asset_ids=["AAPL"],
        )
        d = item.to_dict()
        assert d["dimension"] == "issuer"
        assert d["key"] == "Apple Inc."
        assert d["value"] == 50000.0
        assert d["pct"] == 0.3
        assert d["asset_ids"] == ["AAPL"]


# ── ConcentrationReport ───────────────────────────────────────────────────


class TestConcentrationReport:
    def test_construction_minimal(self):
        r = ConcentrationReport(as_of=date(2026, 6, 1), total_value=100000.0)
        assert r.as_of == date(2026, 6, 1)
        assert r.total_value == 100000.0
        assert r.by_currency == []
        assert r.by_asset_class == []
        assert r.by_issuer == []
        assert r.warnings == []
        assert is_dataclass(r)
        _assert_frozen(r)

    def test_to_dict(self):
        item = ConcentrationItem(
            dimension="currency", key="USD", value=80000.0,
            pct=0.8, asset_ids=["AAPL"],
        )
        r = ConcentrationReport(
            as_of=date(2026, 6, 1),
            total_value=100000.0,
            by_currency=[item],
            warnings=["单一币种 USD 占比 80.0%，超过 80% 阈值"],
        )
        d = r.to_dict()
        assert d["as_of"] == "2026-06-01"
        assert d["total_value"] == 100000.0
        assert len(d["by_currency"]) == 1
        assert d["by_currency"][0]["key"] == "USD"
        assert len(d["warnings"]) == 1


# ── ConcentrationAnalyzer ─────────────────────────────────────────────────


class TestConcentrationAnalyzer:
    def test_empty_positions(self):
        analyzer = ConcentrationAnalyzer()
        report = analyzer.analyze({}, {}, as_of=date(2026, 6, 1))
        assert report.total_value == 0.0
        assert report.by_currency == []
        assert report.by_asset_class == []
        assert report.by_issuer == []
        assert report.warnings == []

    def test_zero_total_value(self):
        analyzer = ConcentrationAnalyzer()
        positions = {
            "AAPL": _pos("AAPL", 0.0),
        }
        report = analyzer.analyze(positions, {"AAPL": {"name": "AAPL", "asset_type": "us_equity"}}, as_of=date(2026, 6, 1))
        assert report.total_value == 0.0

    def test_currency_breakdown(self):
        analyzer = ConcentrationAnalyzer()
        positions = {
            "AAPL": _pos("AAPL", 60000.0, currency="USD"),
            "GOOGL": _pos("GOOGL", 30000.0, currency="USD"),
            "sh600519": _pos("sh600519", 10000.0, currency="CNY"),
        }
        meta = {
            "AAPL": {"name": "AAPL", "asset_type": "us_equity"},
            "GOOGL": {"name": "Alphabet Inc.", "asset_type": "us_equity"},
            "sh600519": {"name": "贵州茅台", "asset_type": "cn_stock_sh"},
        }
        report = analyzer.analyze(positions, meta, as_of=date(2026, 6, 1))

        assert report.total_value == 100000.0
        assert len(report.by_currency) == 2

        usd_item = next(i for i in report.by_currency if i.key == "USD")
        assert usd_item.value == 90000.0
        assert usd_item.pct == 0.9
        assert set(usd_item.asset_ids) == {"AAPL", "GOOGL"}

        cny_item = next(i for i in report.by_currency if i.key == "CNY")
        assert cny_item.value == 10000.0
        assert cny_item.pct == 0.1

    def test_asset_class_breakdown(self):
        analyzer = ConcentrationAnalyzer()
        positions = {
            "AAPL": _pos("AAPL", 50000.0),
            "QQQ": _pos("QQQ", 30000.0),
            "SHV": _pos("SHV", 20000.0),
        }
        meta = {
            "AAPL": {"name": "AAPL", "asset_type": "us_equity"},
            "QQQ": {"name": "Invesco QQQ", "asset_type": "etf"},
            "SHV": {"name": "iShares Short Treasury", "asset_type": "bond"},
        }
        report = analyzer.analyze(positions, meta, as_of=date(2026, 6, 1))

        assert report.total_value == 100000.0
        assert len(report.by_asset_class) >= 2

        equity_item = next(i for i in report.by_asset_class if i.key == "equity")
        assert equity_item.value == 50000.0
        assert equity_item.pct == 0.5

        fund_item = next(i for i in report.by_asset_class if i.key == "fund")
        assert fund_item.value == 30000.0
        assert fund_item.pct == 0.3

        bond_item = next(i for i in report.by_asset_class if i.key == "bond")
        assert bond_item.value == 20000.0
        assert bond_item.pct == 0.2

    def test_issuer_breakdown(self):
        analyzer = ConcentrationAnalyzer()
        positions = {
            "AAPL": _pos("AAPL", 40000.0),
            "MSFT": _pos("MSFT", 35000.0),
            "GOOGL": _pos("GOOGL", 25000.0),
        }
        meta = {
            "AAPL": {"name": "Apple Inc.", "asset_type": "us_equity"},
            "MSFT": {"name": "Microsoft Corporation", "asset_type": "us_equity"},
            "GOOGL": {"name": "Alphabet Inc.", "asset_type": "us_equity"},
        }
        report = analyzer.analyze(positions, meta, as_of=date(2026, 6, 1))

        assert len(report.by_issuer) == 3
        apple = next(i for i in report.by_issuer if i.key == "Apple Inc.")
        assert apple.value == 40000.0
        assert apple.pct == 0.4
        assert apple.asset_ids == ["AAPL"]

    def test_issuer_falls_back_to_name(self):
        analyzer = ConcentrationAnalyzer()
        positions = {"AAPL": _pos("AAPL", 100000.0)}
        meta = {"AAPL": {"name": "Apple Inc.", "asset_type": "us_equity"}}
        report = analyzer.analyze(positions, meta, as_of=date(2026, 6, 1))
        assert report.by_issuer[0].key == "Apple Inc."

    def test_issuer_falls_back_to_asset_id(self):
        analyzer = ConcentrationAnalyzer()
        positions = {"UNKNOWN_ASSET": _pos("UNKNOWN_ASSET", 100000.0)}
        meta = {"UNKNOWN_ASSET": {}}
        report = analyzer.analyze(positions, meta, as_of=date(2026, 6, 1))
        assert report.by_issuer[0].key == "UNKNOWN_ASSET"

    def test_warning_single_currency(self):
        analyzer = ConcentrationAnalyzer()
        positions = {
            "AAPL": _pos("AAPL", 90000.0, currency="USD"),
            "MSFT": _pos("MSFT", 9000.0, currency="USD"),
            "EUR_ASSET": _pos("EUR_ASSET", 1000.0, currency="EUR"),
        }
        meta = {
            "AAPL": {"name": "AAPL", "asset_type": "us_equity"},
            "MSFT": {"name": "MSFT", "asset_type": "us_equity"},
            "EUR_ASSET": {"name": "EUR Asset", "asset_type": "us_equity"},
        }
        report = analyzer.analyze(positions, meta, as_of=date(2026, 6, 1))
        warnings = report.warnings
        assert any("USD" in w and "80%" in w for w in warnings)

    def test_no_warning_when_below_threshold(self):
        analyzer = ConcentrationAnalyzer()
        positions = {
            "AAPL": _pos("AAPL", 40000.0, currency="USD"),
            "CNY_1": _pos("CNY_1", 30000.0, currency="CNY"),
            "EUR_1": _pos("EUR_1", 30000.0, currency="EUR"),
        }
        meta = {
            "AAPL": {"name": "AAPL", "asset_type": "us_equity"},
            "CNY_1": {"name": "A Share 1", "asset_type": "cn_stock"},
            "EUR_1": {"name": "EU Asset", "asset_type": "hk_equity"},
        }
        report = analyzer.analyze(positions, meta, as_of=date(2026, 6, 1))
        # No single currency exceeds 80%
        assert not any("币种" in w for w in report.warnings)

    def test_warning_single_issuer(self):
        analyzer = ConcentrationAnalyzer()
        positions = {"AAPL": _pos("AAPL", 50000.0)}
        meta = {"AAPL": {"name": "Apple Inc.", "asset_type": "us_equity"}}
        report = analyzer.analyze(positions, meta, as_of=date(2026, 6, 1))
        assert any("Apple Inc." in w and "30%" in w for w in report.warnings)

    def test_warning_equity_heavy(self):
        analyzer = ConcentrationAnalyzer()
        positions = {
            "AAPL": _pos("AAPL", 50000.0),
            "MSFT": _pos("MSFT", 40000.0),
            "BOND1": _pos("BOND1", 10000.0),
        }
        meta = {
            "AAPL": {"name": "AAPL", "asset_type": "us_equity"},
            "MSFT": {"name": "MSFT", "asset_type": "us_equity"},
            "BOND1": {"name": "Treasury Bond", "asset_type": "bond"},
        }
        report = analyzer.analyze(positions, meta, as_of=date(2026, 6, 1))
        assert any("权益" in w and "70%" in w for w in report.warnings)

    def test_sorted_descending(self):
        analyzer = ConcentrationAnalyzer()
        positions = {
            "A": _pos("A", 10000.0, currency="CNY"),
            "B": _pos("B", 50000.0, currency="USD"),
            "C": _pos("C", 30000.0, currency="USD"),
        }
        meta = {
            "A": {"name": "A", "asset_type": "cn_stock"},
            "B": {"name": "B", "asset_type": "us_equity"},
            "C": {"name": "C", "asset_type": "us_equity"},
        }
        report = analyzer.analyze(positions, meta, as_of=date(2026, 6, 1))
        # USD should be first (80k), CNY second (10k)
        assert report.by_currency[0].key == "USD"
        assert report.by_currency[0].value == 80000.0
        assert report.by_currency[1].key == "CNY"
        assert report.by_currency[1].value == 10000.0

    def test_uses_issuer_field_when_present(self):
        analyzer = ConcentrationAnalyzer()
        positions = {"WMP1": _pos("WMP1", 50000.0, currency="CNY")}
        meta = {
            "WMP1": {
                "name": "稳健理财1号",
                "asset_type": "bank_wmp",
                "issuer": "中国银行",
                "manager": "中银理财",
            },
        }
        report = analyzer.analyze(positions, meta, as_of=date(2026, 6, 1))
        assert report.by_issuer[0].key == "中国银行"

    def test_uses_manager_when_no_issuer(self):
        analyzer = ConcentrationAnalyzer()
        positions = {"FUND1": _pos("FUND1", 50000.0, currency="CNY")}
        meta = {
            "FUND1": {
                "name": "XX基金",
                "asset_type": "fund",
                "manager": "华夏基金",
            },
        }
        report = analyzer.analyze(positions, meta, as_of=date(2026, 6, 1))
        assert report.by_issuer[0].key == "华夏基金"

    def test_multiple_warnings_combined(self):
        analyzer = ConcentrationAnalyzer()
        positions = {
            "AAPL": _pos("AAPL", 90000.0, currency="USD"),
        }
        meta = {"AAPL": {"name": "Apple Inc.", "asset_type": "us_equity"}}
        report = analyzer.analyze(positions, meta, as_of=date(2026, 6, 1))
        # Should have both single-currency warning AND single-issuer warning AND equity warning
        assert len(report.warnings) >= 2
