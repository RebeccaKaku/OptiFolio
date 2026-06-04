"""Tests for the FinData serving department — DataProvider, fd transforms, metrics, rates, and export."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from FinData import fd as fd_import
from FinData.storage_dept.store import CanonicalStore


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_df(dates=None, close=None, extra_cols=None):
    """Build a minimal OHLCV-style DataFrame for testing."""
    if dates is None:
        dates = pd.date_range("2024-01-01", periods=60, freq="B")
    if close is None:
        close = np.linspace(100, 150, len(dates))
    data = {"date": dates, "close": close}
    if extra_cols:
        data.update(extra_cols)
    return pd.DataFrame(data)


def _populated_provider(tmp_path, asset_id="AAPL", df=None):
    """Create a DataProvider backed by a tmp_path store with one asset."""
    store = CanonicalStore(root_dir=str(tmp_path))
    if df is None:
        df = _make_df()
    store.accept(df, asset_id=asset_id, source="unit", currency="USD")
    from FinData.serving_dept.provider import DataProvider
    return DataProvider(store=store), store


# ── Prices tests ───────────────────────────────────────────────────────────

class TestDataProviderPrices:
    def test_prices_returns_series(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        prices = provider.prices("AAPL")
        assert isinstance(prices, pd.Series)
        assert len(prices) == 60

    def test_prices_unknown_symbol_returns_none(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        prices = provider.prices("NONEXISTENT")
        assert prices is None

    def test_prices_with_date_range(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        prices = provider.prices("AAPL", start="2024-02-01", end="2024-03-01")
        assert prices is not None
        assert len(prices) > 0

    def test_prices_live_mode_triggers_refresh(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        # live mode should call _trigger_refresh (stub) and still return data
        prices = provider.prices("AAPL", mode="live")
        assert prices is not None
        assert len(prices) == 60


class TestDataProviderOhlcv:
    def test_ohlcv_returns_dataframe(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        df = provider.ohlcv("AAPL")
        assert isinstance(df, pd.DataFrame)
        assert "AAPL" in df.columns


class TestDataProviderPanel:
    def test_panel_returns_pivoted_matrix(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")
        store.accept(
            _make_df(close=np.linspace(50, 70, 60)),
            asset_id="BBB", source="unit", currency="USD",
        )
        from FinData.serving_dept.provider import DataProvider
        provider = DataProvider(store=store)
        panel = provider.panel(["AAA", "BBB"])
        assert isinstance(panel, pd.DataFrame)
        assert list(panel.columns) == ["AAA", "BBB"]
        assert panel.shape == (60, 2)


# ── Returns tests ──────────────────────────────────────────────────────────

class TestDataProviderReturns:
    def test_returns_computes_pct_change(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        returns = provider.returns("AAPL")
        assert isinstance(returns, pd.Series)
        # 60 rows -> 59 returns
        assert len(returns) == 59

    def test_returns_empty_data_returns_empty_series(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        from FinData.serving_dept.provider import DataProvider
        provider = DataProvider(store=store)
        returns = provider.returns("NONEXISTENT")
        assert isinstance(returns, pd.Series)
        assert len(returns) == 0

    def test_returns_single_row_returns_empty_series(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=1, freq="B"),
            "close": [100.0],
        })
        store.accept(df, asset_id="SINGLE", source="unit", currency="USD")
        from FinData.serving_dept.provider import DataProvider
        provider = DataProvider(store=store)
        returns = provider.returns("SINGLE")
        assert len(returns) == 0

    def test_returns_respects_date_range(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        returns = provider.returns("AAPL", start="2024-01-15", end="2024-02-15")
        assert isinstance(returns, pd.Series)
        assert len(returns) > 0


# ── Metrics tests ──────────────────────────────────────────────────────────

class TestDataProviderMetrics:
    def test_metrics_single_metric_returns_float(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        result = provider.metrics("AAPL", "sharpe_ratio")
        assert isinstance(result, dict)
        assert "sharpe_ratio" in result
        assert isinstance(result["sharpe_ratio"], float)

    def test_metrics_all_returns_all_keys(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        result = provider.metrics("AAPL", "all")
        assert isinstance(result, dict)
        expected_keys = {
            "sharpe_ratio", "total_return", "annualized_return",
            "volatility", "max_drawdown", "sortino_ratio",
            "calmar_ratio", "win_rate",
        }
        assert set(result.keys()) == expected_keys
        for val in result.values():
            assert isinstance(val, float)

    def test_metrics_list_of_keys(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        result = provider.metrics("AAPL", ["total_return", "volatility"])
        assert set(result.keys()) == {"total_return", "volatility"}

    def test_metrics_empty_data_returns_zeros(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        from FinData.serving_dept.provider import DataProvider
        provider = DataProvider(store=store)
        result = provider.metrics("NONEXISTENT", "sharpe_ratio")
        assert result["sharpe_ratio"] == 0.0

    def test_metrics_single_row_returns_zeros(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=1, freq="B"),
            "close": [100.0],
        })
        store.accept(df, asset_id="SINGLE", source="unit", currency="USD")
        from FinData.serving_dept.provider import DataProvider
        provider = DataProvider(store=store)
        result = provider.metrics("SINGLE", "all")
        assert all(v == 0.0 for v in result.values())

    def test_metrics_unknown_metric_returns_empty(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        result = provider.metrics("AAPL", "nonexistent_metric")
        assert result == {}

    def test_sharpe_ratio_reasonable(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        result = provider.metrics("AAPL", "sharpe_ratio")
        # With a smooth upward trend, Sharpe should be positive and high
        assert result["sharpe_ratio"] > 0

    def test_max_drawdown_is_negative_or_zero(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        result = provider.metrics("AAPL", "max_drawdown")
        assert result["max_drawdown"] <= 0

    def test_total_return_matches_manual(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        result = provider.metrics("AAPL", "total_return")
        expected = 150.0 / 100.0 - 1  # 50% return
        assert abs(result["total_return"] - expected) < 1e-10

    def test_win_rate_between_zero_and_one(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        result = provider.metrics("AAPL", "win_rate")
        assert 0.0 <= result["win_rate"] <= 1.0

    def test_volatility_non_negative(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        result = provider.metrics("AAPL", "volatility")
        assert result["volatility"] >= 0

    def test_all_metric_calculators_run_without_error(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        # Each individual metric should work
        for metric in [
            "sharpe_ratio", "total_return", "annualized_return",
            "volatility", "max_drawdown", "sortino_ratio",
            "calmar_ratio", "win_rate",
        ]:
            result = provider.metrics("AAPL", metric)
            assert isinstance(result[metric], float), f"{metric} failed"


# ── Rates tests ────────────────────────────────────────────────────────────

class TestDataProviderRates:
    def test_rate_1y_cn_returns_float(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        result = provider.rate("1y_cn")
        assert isinstance(result, float)
        assert result == pytest.approx(0.017)

    def test_rate_5y_cn_returns_float(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        result = provider.rate("5y_cn")
        assert isinstance(result, float)
        assert result == pytest.approx(0.036)

    def test_rate_10y_cn_returns_float(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        result = provider.rate("10y_cn")
        assert isinstance(result, float)
        assert result == pytest.approx(0.028)

    def test_rate_default_is_1y_cn(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        result = provider.rate()
        assert result == pytest.approx(0.017)

    def test_rate_unknown_returns_zero(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        result = provider.rate("nonexistent")
        assert result == 0.0


class TestDataProviderFxRates:
    def test_fx_rate_usd_cny_returns_float(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        result = provider.fx_rate("USD", "CNY")
        assert isinstance(result, float)
        assert result > 0

    def test_fx_rate_same_currency_returns_one(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        result = provider.fx_rate("USD", "USD")
        assert result == 1.0


# ── Export tests ───────────────────────────────────────────────────────────

class TestDataProviderExport:
    def test_export_csv_returns_csv_string(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        csv_str = provider.export("AAPL", format="csv")
        assert isinstance(csv_str, str)
        assert "AAPL" in csv_str or "," in csv_str
        # Should contain date and price
        assert "2024" in csv_str

    def test_export_json_returns_json_string(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        json_str = provider.export("AAPL", format="json")
        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["symbol"] == "AAPL"
        assert isinstance(data["data"], dict)
        assert len(data["data"]) == 60

    def test_export_csv_unknown_symbol_returns_empty(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        csv_str = provider.export("NONEXISTENT", format="csv")
        assert csv_str == ""

    def test_export_json_unknown_symbol_returns_empty_array(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        json_str = provider.export("NONEXISTENT", format="json")
        assert json_str == "[]"

    def test_export_invalid_format_raises(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        with pytest.raises(ValueError, match="Unknown format"):
            provider.export("AAPL", format="xml")

    def test_export_respects_date_range(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        csv_str = provider.export("AAPL", start="2024-01-15", end="2024-01-20", format="csv")
        assert isinstance(csv_str, str)
        assert len(csv_str) > 0


# ── fd singleton back-compat tests ─────────────────────────────────────────

class TestFdBackCompat:
    """Ensure existing fd.prices() / fd.panel() patterns still work."""

    def test_fd_prices_returns_series(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAPL", source="unit", currency="USD")

        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        prices = fd_test.prices("AAPL")
        assert prices is not None
        assert isinstance(prices, pd.Series)
        assert len(prices) == 60

    def test_fd_prices_unknown_symbol_returns_none(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        prices = fd_test.prices("NONEXISTENT")
        assert prices is None

    def test_fd_panel_returns_pivoted_matrix(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")
        store.accept(
            _make_df(close=np.linspace(50, 70, 60)),
            asset_id="BBB", source="unit", currency="USD",
        )

        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        panel = fd_test.panel(["AAA", "BBB"])
        assert isinstance(panel, pd.DataFrame)
        assert list(panel.columns) == ["AAA", "BBB"]
        assert panel.shape == (60, 2)

    def test_fd_same_instance_on_multiple_imports(self):
        import FinData
        from FinData import fd as fd1
        from FinData import fd as fd2

        assert fd1 is fd2
        assert fd1 is FinData.fd

    def test_fd_is_findata_instance(self):
        from FinData import fd, FinData
        assert isinstance(fd, FinData)

    def test_fd_returns_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAPL", source="unit", currency="USD")

        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        returns = fd_test.returns("AAPL")
        assert isinstance(returns, pd.Series)
        assert len(returns) == 59

    def test_fd_ohlcv_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAPL", source="unit", currency="USD")

        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        df = fd_test.ohlcv("AAPL")
        assert isinstance(df, pd.DataFrame)
        assert "AAPL" in df.columns

    def test_fd_metrics_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAPL", source="unit", currency="USD")

        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        result = fd_test.metrics("AAPL", "sharpe_ratio")
        assert isinstance(result["sharpe_ratio"], float)

    def test_fd_rate_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        result = fd_test.rate("5y_cn")
        assert result == pytest.approx(0.036)

    def test_fd_export_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAPL", source="unit", currency="USD")

        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        csv_str = fd_test.export("AAPL", format="csv")
        assert isinstance(csv_str, str)
        assert "2024" in csv_str

    def test_fd_list_assets_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")
        store.accept(_make_df(), asset_id="BBB", source="unit", currency="USD")

        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        assets = fd_test.list_assets()
        assert sorted(assets) == ["AAA", "BBB"]

    def test_fd_missing_report_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")

        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        report = fd_test.missing_report(["AAA"])
        assert report["missing"].sum() == 0


# ── fd singleton deferred import tests ─────────────────────────────────────

class TestFdSingletonDeferred:
    def test_fd_singleton_imports_cleanly(self):
        """Verify that importing fd does not crash."""
        from FinData import fd
        assert fd is not None

    def test_fd_has_all_public_methods(self):
        from FinData import fd
        public_methods = [
            "prices", "ohlcv", "panel", "returns", "metrics",
            "rate", "fx_rate", "export", "list_assets", "missing_report",
        ]
        for method in public_methods:
            assert hasattr(fd, method), f"fd missing method: {method}"
            assert callable(getattr(fd, method)), f"fd.{method} is not callable"


# ── Edge case: original test_findata_storage.py patterns ───────────────────

class TestFdStoragePatternsStillWork:
    """Confirm the patterns from test_findata_storage.py still function."""

    def test_inject_store_and_query_prices(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAPL", source="unit", currency="USD")

        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store  # Back-compat injection

        prices = fd_test.prices("AAPL")
        assert prices is not None
        assert isinstance(prices, pd.Series)

    def test_inject_store_and_query_panel(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")
        store.accept(
            _make_df(close=np.linspace(50, 70, 60)),
            asset_id="BBB", source="unit", currency="USD",
        )

        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        panel = fd_test.panel(["AAA", "BBB"])
        assert panel.shape == (60, 2)
