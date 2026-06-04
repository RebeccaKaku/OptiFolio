"""Unit tests for Ghostfolio export — activity conversion logic and symbol normalization."""

from datetime import date
from unittest.mock import ANY, MagicMock, patch

import pytest

from tools.export_to_ghostfolio import (
    GhostfolioExporter,
    GhostfolioClient,
    normalize_symbol,
    load_portfolio,
)


# ── Symbol normalization ─────────────────────────────────────────────────


def test_normalize_us_equity_passes_through():
    assert normalize_symbol("AAPL") == "AAPL"
    assert normalize_symbol("QQQ") == "QQQ"
    assert normalize_symbol("GOOGL") == "GOOGL"


def test_normalize_numeric_etf_passes_through():
    assert normalize_symbol("510300") == "510300"


def test_normalize_cn_stock_sh_strips_prefix():
    assert normalize_symbol("sh600519") == "600519"
    assert normalize_symbol("sh601398") == "601398"
    assert normalize_symbol("sh600028") == "600028"


def test_normalize_cn_stock_sz_strips_prefix():
    assert normalize_symbol("sz000001") == "000001"
    assert normalize_symbol("sz300750") == "300750"


def test_normalize_cn_fund_strips_prefix():
    assert normalize_symbol("sh005827") == "005827"


def test_normalize_already_clean_is_idempotent():
    assert normalize_symbol("600519") == "600519"
    assert normalize_symbol("000001") == "000001"


def test_normalize_nonstandard_is_identity():
    assert normalize_symbol("AMHQLXTTUSD01B") == "AMHQLXTTUSD01B"
    assert normalize_symbol("23GS8125") == "23GS8125"
    assert normalize_symbol("004502") == "004502"


# ── Activity building ───────────────────────────────────────────────────


class FakeClient(GhostfolioClient):
    """A fake client that never makes real HTTP calls."""

    def __init__(self):
        pass  # skip real __init__

    def get_accounts(self):
        return [{"id": "fake-account-uuid", "name": "OptiFolio"}]

    def get_or_create_account(self, name, currency):
        return "fake-account-uuid"


def test_build_activities_basic(monkeypatch):
    """Verify that holdings + prices produce correctly-shaped Ghostfolio activities."""
    monkeypatch.setattr(
        "tools.export_to_ghostfolio._resolve_currency",
        lambda asset_id: "USD" if asset_id == "AAPL" else "CNY",
    )

    exporter = GhostfolioExporter("http://localhost:3333", "fake-token")
    exporter.client = FakeClient()

    holdings = {"AAPL": 100, "510300": 250}
    prices = {"AAPL": 185.50, "510300": 3.95}
    activities = exporter._build_activities(holdings, prices, "2026-06-03", "fake-uuid")

    assert len(activities) == 2

    # Sorted by asset_id: "510300" < "AAPL"
    by_symbol = {a["symbol"]: a for a in activities}

    aapl = by_symbol["AAPL"]
    assert aapl["type"] == "BUY"
    assert aapl["quantity"] == 100
    assert aapl["unitPrice"] == 185.50
    assert aapl["currency"] == "USD"
    assert aapl["dataSource"] == "MANUAL"
    assert aapl["accountId"] == "fake-uuid"
    assert aapl["fee"] == 0.0
    assert aapl["date"].endswith("Z")

    etf = by_symbol["510300"]
    assert etf["symbol"] == "510300"
    assert etf["type"] == "BUY"
    assert etf["quantity"] == 250
    assert etf["unitPrice"] == 3.95
    assert etf["currency"] == "CNY"


def test_build_activities_skips_zero_quantity():
    """Positions with zero quantity should be filtered out."""
    exporter = GhostfolioExporter("http://localhost:3333", "fake-token")
    exporter.client = FakeClient()

    holdings = {"AAPL": 0, "QQQ": 50}
    prices = {"AAPL": 185.50, "QQQ": 420.0}
    activities = exporter._build_activities(holdings, prices, "2026-06-03", "fake-uuid")

    assert len(activities) == 1
    assert activities[0]["symbol"] == "QQQ"


def test_build_activities_skips_negative_quantity():
    """Negative quantities should be filtered out."""
    exporter = GhostfolioExporter("http://localhost:3333", "fake-token")
    exporter.client = FakeClient()

    holdings = {"AAPL": -10}
    prices = {"AAPL": 185.50}
    activities = exporter._build_activities(holdings, prices, "2026-06-03", "fake-uuid")

    assert len(activities) == 0


def test_build_activities_skips_missing_price(monkeypatch):
    """Assets without price data should be skipped."""
    monkeypatch.setattr(
        "tools.export_to_ghostfolio._resolve_currency",
        lambda aid: "USD",
    )
    exporter = GhostfolioExporter("http://localhost:3333", "fake-token")
    exporter.client = FakeClient()

    holdings = {"AAPL": 100, "MISSING": 50}
    prices = {"AAPL": 185.50}
    activities = exporter._build_activities(holdings, prices, "2026-06-03", "fake-uuid")

    assert len(activities) == 1
    assert activities[0]["symbol"] == "AAPL"


def test_build_activities_cn_stock_normalization(monkeypatch):
    """Verify that CN stock symbols are normalized (sh prefix stripped)."""
    monkeypatch.setattr(
        "tools.export_to_ghostfolio._resolve_currency",
        lambda aid: "CNY",
    )
    exporter = GhostfolioExporter("http://localhost:3333", "fake-token")
    exporter.client = FakeClient()

    holdings = {"sh600519": 100}
    prices = {"sh600519": 1600.0}
    activities = exporter._build_activities(holdings, prices, "2026-06-03", "fake-uuid")

    assert len(activities) == 1
    assert activities[0]["symbol"] == "600519"


def test_activity_date_format():
    """Verify the date is formatted as Ghostfolio's expected ISO 8601 with Z suffix."""
    result = GhostfolioExporter._format_datetime("2026-06-03")
    assert result == "2026-06-03T00:00:00.000Z"

    result2 = GhostfolioExporter._format_datetime("2025-01-15")
    assert result2 == "2025-01-15T00:00:00.000Z"


def test_activity_json_matches_ghostfolio_format(monkeypatch):
    """Verify the full activity dict matches Ghostfolio's expected format exactly."""
    monkeypatch.setattr(
        "tools.export_to_ghostfolio._resolve_currency",
        lambda aid: "USD",
    )
    exporter = GhostfolioExporter("http://localhost:3333", "fake-token")
    exporter.client = FakeClient()

    holdings = {"AAPL": 100}
    prices = {"AAPL": 150.00}
    activities = exporter._build_activities(holdings, prices, "2024-01-15", "fake-uuid")

    assert len(activities) == 1
    act = activities[0]

    # Must match Ghostfolio's expected keys and types
    assert set(act.keys()) == {
        "accountId", "comment", "currency", "dataSource", "date",
        "fee", "quantity", "symbol", "type", "unitPrice",
    }
    assert isinstance(act["accountId"], str)
    assert isinstance(act["currency"], str)
    assert isinstance(act["dataSource"], str)
    assert isinstance(act["date"], str)
    assert isinstance(act["fee"], float)
    assert isinstance(act["quantity"], float)
    assert isinstance(act["symbol"], str)
    assert act["type"] == "BUY"
    assert isinstance(act["unitPrice"], float)
    assert act["unitPrice"] == 150.0


# ── export_valuation_history ─────────────────────────────────────────────


def test_export_valuation_history_is_noop():
    """Ghostfolio does NOT ingest historical valuations — it's a documented no-op."""
    exporter = GhostfolioExporter("http://localhost:3333", "fake-token")
    exporter.client = FakeClient()

    import pandas as pd
    df = pd.DataFrame()
    result = exporter.export_valuation_history(df)
    assert result == 0


# ── export_holdings with mock HTTP ───────────────────────────────────────


def test_export_holdings_posts_and_returns_count(monkeypatch):
    """Integration test: export_holdings should POST activities and return the count."""
    monkeypatch.setattr(
        "tools.export_to_ghostfolio._resolve_currency",
        lambda aid: "USD",
    )

    class MockClient(FakeClient):
        def import_activities(self, activities):
            return {"activities": activities}

    exporter = GhostfolioExporter("http://localhost:3333", "fake-token")
    exporter.client = MockClient()

    holdings = {"AAPL": 100, "QQQ": 50}
    prices = {"AAPL": 185.50, "QQQ": 420.00}
    count = exporter.export_holdings(holdings, {}, prices, "2026-06-03",
                                     account_id="fixed-id")
    assert count == 2


def test_export_holdings_empty_returns_zero():
    """Empty holdings should return 0 without error."""
    exporter = GhostfolioExporter("http://localhost:3333", "fake-token")
    exporter.client = FakeClient()

    count = exporter.export_holdings({}, {}, {}, "2026-06-03",
                                     account_id="fixed-id")
    assert count == 0


# ── load_portfolio ───────────────────────────────────────────────────────


def test_load_portfolio_returns_dicts(tmp_path, monkeypatch):
    """load_portfolio reads a YAML file and returns (holdings, cash) dicts."""
    import yaml
    portfolio = {"cash": {"USD": 5000.0}, "positions": {"AAPL": 100}}
    p = tmp_path / "portfolio.yaml"
    with open(p, "w") as f:
        yaml.dump(portfolio, f)

    monkeypatch.setattr(
        "tools.export_to_ghostfolio.PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        "tools.export_to_ghostfolio.os.environ",
        {},
    )

    # Create local/ dir so it's tried first; portfolio.yaml goes there
    local = tmp_path / "local"
    local.mkdir()
    with open(local / "portfolio.yaml", "w") as f:
        yaml.dump(portfolio, f)

    h, c = load_portfolio()
    assert h == {"AAPL": 100.0}
    assert c == {"USD": 5000.0}
