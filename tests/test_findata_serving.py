"""Tests for the FinData serving department — DataProvider, fd transforms, metrics, rates, and export."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from findata import fd as fd_import
from findata.store import CanonicalStore


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
    from findata.serving.provider import DataProvider
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

    def test_prices_invalid_date_range_returns_none(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        prices = provider.prices("AAPL", start="2024-03-01", end="2024-02-01")
        assert prices is None

    def test_prices_drops_na_values(self, tmp_path, monkeypatch):
        provider, _ = _populated_provider(tmp_path, "AAPL")

        # Mock get_prices to return a panel with NaNs
        dates = pd.date_range("2024-01-01", periods=3, freq="B")
        mock_panel = pd.DataFrame({"equity.us.aapl": [100.0, np.nan, 102.0]}, index=dates)
        monkeypatch.setattr(provider._store, "get_prices", lambda *args, **kwargs: mock_panel)

        prices = provider.prices("AAPL")
        assert prices is not None
        assert len(prices) == 2
        assert not prices.isna().any()

    def test_prices_empty_symbol_returns_none(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        prices = provider.prices("")
        assert prices is None

    def test_prices_empty_panel_returns_none(self, tmp_path, monkeypatch):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        monkeypatch.setattr(provider._store, "get_prices", lambda *args, **kwargs: pd.DataFrame())
        prices = provider.prices("AAPL")
        assert prices is None

    def test_prices_symbol_not_in_panel_returns_none(self, tmp_path, monkeypatch):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        monkeypatch.setattr(provider._store, "get_prices", lambda *args, **kwargs: pd.DataFrame({"OTHER": [1.0, 2.0]}))
        prices = provider.prices("AAPL")
        assert prices is None

    def test_prices_live_mode_triggers_refresh(self, tmp_path, monkeypatch):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        # live mode should call _trigger_refresh and still return data.
        # Patch Orchestrator.schedule to avoid real network fetches
        # from contaminating the tmp_path store.
        called = {"schedule": False, "dispatch": False}

        def fake_schedule(self, asset_ids=None, asset_types=None):
            called["schedule"] = True
            return []

        def fake_dispatch(self, tasks):
            called["dispatch"] = True
            return {}

        monkeypatch.setattr(
            "findata.orchestration.orchestrator.Orchestrator.schedule",
            fake_schedule,
        )
        monkeypatch.setattr(
            "findata.orchestration.orchestrator.Orchestrator.dispatch",
            fake_dispatch,
        )
        prices = provider.prices("AAPL", mode="live")
        assert prices is not None
        assert len(prices) == 60
        assert called["schedule"], "live mode should trigger refresh schedule"


class TestDataProviderOhlcv:
    def test_ohlcv_returns_dataframe(self, tmp_path):
        provider, _ = _populated_provider(tmp_path, "AAPL")
        df = provider.ohlcv("AAPL")
        assert isinstance(df, pd.DataFrame)
        # Multi-field returns flat (date, asset_id, o, h, l, c, adj_close, vol)
        assert "open" in df.columns
        assert "high" in df.columns
        assert "close" in df.columns
        assert "adj_close" in df.columns
        assert "volume" in df.columns
        assert df["asset_id"].iloc[0] == "equity.us.aapl"


class TestDataProviderPanel:
    def test_panel_returns_pivoted_matrix(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")
        store.accept(
            _make_df(close=np.linspace(50, 70, 60)),
            asset_id="BBB", source="unit", currency="USD",
        )
        from findata.serving.provider import DataProvider
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
        from findata.serving.provider import DataProvider
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
        from findata.serving.provider import DataProvider
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
        from findata.serving.provider import DataProvider
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
        from findata.serving.provider import DataProvider
        provider = DataProvider(store=store)
        result = provider.metrics("SINGLE", "all")
        # max_drawdown is None when no data (distinguishes from zero drawdown)
        for k, v in result.items():
            if k == "max_drawdown":
                assert v is None, f"max_drawdown should be None for no data, got {v}"
            else:
                assert v == 0.0, f"{k} should be 0.0 for no data, got {v}"

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
    def test_rate_prefers_stored_observation(self, tmp_path):
        """Stored SHIBOR 1Y observation is authoritative for 1y_cn."""
        provider, store = _populated_provider(tmp_path)
        store.repo.save_observations(
            pd.DataFrame({
                "effective_date": ["2024-01-31"],
                "value": [0.0215],
                "known_at": ["2024-02-01T09:00:00"],
            }),
            series_id="RATE_SHIBOR_CNY_1Y",
            source="unit_rate_feed",
            unit="decimal",
            currency="CNY",
        )

        result = provider.rate("1y_cn", date_str="2024-02-05")

        assert result["value"] == pytest.approx(0.0215)
        assert result["source"] == "unit_rate_feed"
        assert result["as_of"] == "2024-01-31"
        assert result["warning"] is None

    def test_rate_prefers_stored_observation_for_1y_us(self, tmp_path):
        """Stored SOFR observation is authoritative for 1y_us."""
        provider, store = _populated_provider(tmp_path)
        store.repo.save_observations(
            pd.DataFrame({
                "effective_date": ["2024-01-31"],
                "value": [0.0531],
                "known_at": ["2024-02-01T09:00:00"],
            }),
            series_id="rate.us.sofr.on",
            source="fred",
            unit="decimal",
            currency="USD",
        )

        result = provider.rate("1y_us", date_str="2024-02-05")

        assert result["value"] == pytest.approx(0.0531)
        assert result["source"] == "fred"
        assert result["as_of"] == "2024-01-31"
        assert result["warning"] is None

    def test_rate_5y_cn_stored_shows_tenor_mismatch_warning(self, tmp_path):
        """5y_cn uses SHIBOR 1Y as proxy — should warn about tenor mismatch."""
        provider, store = _populated_provider(tmp_path)
        store.repo.save_observations(
            pd.DataFrame({
                "effective_date": ["2024-01-31"],
                "value": [0.0215],
            }),
            series_id="RATE_SHIBOR_CNY_1Y",
            source="unit_rate_feed",
            unit="decimal",
            currency="CNY",
        )

        result = provider.rate("5y_cn", date_str="2024-02-05")

        assert result["value"] == pytest.approx(0.0215)
        assert result["source"] == "unit_rate_feed"
        assert result["warning"] is not None
        assert "TENOR MISMATCH" in result["warning"]
        assert "shibor" in result["warning"].lower()

    def test_rate_1y_cn_no_observation_returns_missing(self, tmp_path):
        """When repo exists but no observation stored, report as missing."""
        provider, _ = _populated_provider(tmp_path)
        result = provider.rate("1y_cn")
        assert isinstance(result, dict)
        assert result["rate_id"] == "1y_cn"
        assert result["value"] == 0.0
        assert result["source"] == "missing_observation"
        assert result["as_of"] is None
        assert result["warning"] is not None
        assert "No stored observation" in result["warning"]

    def test_rate_5y_cn_no_observation_returns_missing(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        result = provider.rate("5y_cn")
        assert result["rate_id"] == "5y_cn"
        assert result["value"] == 0.0
        assert result["source"] == "missing_observation"

    def test_rate_10y_cn_no_observation_returns_missing(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        result = provider.rate("10y_cn")
        assert result["rate_id"] == "10y_cn"
        assert result["value"] == 0.0
        assert result["source"] == "missing_observation"

    def test_rate_default_is_1y_cn(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        result = provider.rate()
        assert isinstance(result, dict)
        assert result["rate_id"] == "1y_cn"
        # Without stored observation, returns missing
        assert result["source"] == "missing_observation"

    def test_rate_unknown_returns_missing(self, tmp_path):
        """Unknown rate_id with repo available returns missing_observation."""
        provider, _ = _populated_provider(tmp_path)
        result = provider.rate("nonexistent")
        assert isinstance(result, dict)
        assert result["rate_id"] == "nonexistent"
        assert result["value"] == 0.0
        assert result["source"] == "missing_observation"
        assert result["warning"] is not None

    def test_rate_no_repo_returns_missing(self):
        """When store has no repo at all, report as missing_observation."""
        from findata.serving.provider import DataProvider
        # Create a provider with a store that has no 'repo' attribute
        provider = DataProvider(store=object())  # object() has no .repo
        result = provider.rate("1y_cn")
        assert result["source"] == "missing_observation"
        assert result["value"] == 0.0

    def test_rate_1y_us_no_observation_returns_missing(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        result = provider.rate("1y_us")
        assert result["rate_id"] == "1y_us"
        assert result["source"] == "missing_observation"
        assert result["value"] == 0.0


class TestDataProviderFxRates:
    def test_fx_rate_prefers_current_store_repository(self, tmp_path):
        provider, store = _populated_provider(tmp_path)
        store.accept(
            pd.DataFrame({
                "date": ["2025-06-02", "2025-06-03"],
                "close": [7.11, 7.22],
            }),
            asset_id="fx.usd_cny.spot",
            source="unit_fx",
            currency="CNY",
        )

        result = provider.fx_rate("USD", "CNY", date_str="2025-06-03")

        assert result == pytest.approx(7.22)

    def test_fx_rate_usd_cny_returns_float(self, tmp_path):
        provider, store = _populated_provider(tmp_path)
        # Seed a cached FX observation so the test does not require network.
        store.accept(
            pd.DataFrame({
                "date": pd.date_range(end=pd.Timestamp.today(), periods=3, freq="D"),
                "close": [7.20, 7.21, 7.22],
            }),
            asset_id="fx.usd_cny.spot",
            source="test",
            currency="CNY",
            timezone="UTC",
        )
        result = provider.fx_rate("USD", "CNY")
        assert isinstance(result, float)
        assert result > 0

    def test_fx_rate_same_currency_returns_one(self, tmp_path):
        provider, _ = _populated_provider(tmp_path)
        result = provider.fx_rate("USD", "USD")
        assert result == 1.0


class TestDataProviderObservations:
    def test_observations_returns_canonical_rows(self, tmp_path):
        provider, store = _populated_provider(tmp_path)
        store.repo.save_observations(
            pd.DataFrame({
                "effective_date": ["2024-01-02", "2024-01-03"],
                "value": [0.031, 0.032],
            }),
            series_id="rate.us.sofr.on",
            source="unit",
            unit="decimal",
            currency="USD",
        )

        df = provider.observations(["rate.us.sofr.on"], start="2024-01-03")

        assert len(df) == 1
        assert df["series_id"].iloc[0] == "rate.us.sofr.on"
        assert df["value"].iloc[0] == pytest.approx(0.032)

    def test_latest_observation_serializes_dates(self, tmp_path):
        provider, store = _populated_provider(tmp_path)
        store.repo.save_observations(
            pd.DataFrame({
                "effective_date": ["2024-01-02"],
                "value": [0.031],
                "known_at": ["2024-01-03T09:00:00"],
            }),
            series_id="rate.us.sofr.on",
            source="unit",
            unit="decimal",
            currency="USD",
        )

        row = provider.latest_observation("rate.us.sofr.on")

        assert row["series_id"] == "rate.us.sofr.on"
        assert row["effective_date"] == "2024-01-02"
        assert row["known_at"].startswith("2024-01-03T09:00:00")

    def test_observation_coverage_returns_missing_series(self, tmp_path):
        provider, store = _populated_provider(tmp_path)
        store.repo.save_observations(
            pd.DataFrame({
                "effective_date": ["2024-01-02"],
                "value": [0.031],
            }),
            series_id="rate.us.sofr.on",
            source="unit",
        )

        coverage = provider.observation_coverage(
            ["RATE_SOFR_USD_ON", "RATE_SONIA_GBP_ON"],
            expected_stale_days=2,
            as_of="2024-01-10",
        )

        assert set(coverage["series_id"]) == {"rate.us.sofr.on", "rate.uk.sonia.on"}
        missing = coverage[coverage["series_id"] == "rate.uk.sonia.on"].iloc[0]
        assert bool(missing["missing"]) is True


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

        from findata import FinData
        fd_test = FinData()
        fd_test._store = store

        prices = fd_test.prices("AAPL")
        assert prices is not None
        assert isinstance(prices, pd.Series)
        assert len(prices) == 60

    def test_fd_prices_unknown_symbol_returns_none(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        from findata import FinData
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

        from findata import FinData
        fd_test = FinData()
        fd_test._store = store

        panel = fd_test.panel(["AAA", "BBB"])
        assert isinstance(panel, pd.DataFrame)
        assert list(panel.columns) == ["AAA", "BBB"]
        assert panel.shape == (60, 2)

    def test_fd_same_instance_on_multiple_imports(self):
        import findata
        from findata import fd as fd1
        from findata import fd as fd2

        assert fd1 is fd2
        assert fd1 is findata.fd

    def test_fd_is_findata_instance(self):
        from findata import fd, FinData
        assert isinstance(fd, FinData)

    def test_fd_returns_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAPL", source="unit", currency="USD")

        from findata import FinData
        fd_test = FinData()
        fd_test._store = store

        returns = fd_test.returns("AAPL")
        assert isinstance(returns, pd.Series)
        assert len(returns) == 59

    def test_fd_ohlcv_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAPL", source="unit", currency="USD")

        from findata import FinData
        fd_test = FinData()
        fd_test._store = store

        df = fd_test.ohlcv("AAPL")
        assert isinstance(df, pd.DataFrame)
        # Multi-field OHLCV: flat DataFrame with date index + field columns
        for col in ("open", "high", "low", "close", "adj_close", "volume"):
            assert col in df.columns, f"Expected OHLCV column {col}"
        assert df["asset_id"].iloc[0] == "equity.us.aapl"

    def test_fd_metrics_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAPL", source="unit", currency="USD")

        from findata import FinData
        fd_test = FinData()
        fd_test._store = store

        result = fd_test.metrics("AAPL", "sharpe_ratio")
        assert isinstance(result["sharpe_ratio"], float)

    def test_fd_rate_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        from findata import FinData
        fd_test = FinData()
        fd_test._store = store

        result = fd_test.rate("5y_cn")
        assert isinstance(result, dict)
        assert result["rate_id"] == "5y_cn"
        assert result["source"] == "missing_observation"
        assert "warning" in result

    def test_fd_export_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAPL", source="unit", currency="USD")

        from findata import FinData
        fd_test = FinData()
        fd_test._store = store

        csv_str = fd_test.export("AAPL", format="csv")
        assert isinstance(csv_str, str)
        assert "2024" in csv_str

    def test_fd_list_assets_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")
        store.accept(_make_df(), asset_id="BBB", source="unit", currency="USD")

        from findata import FinData
        fd_test = FinData()
        fd_test._store = store

        assets = fd_test.list_assets()
        assert sorted(assets) == ["equity.us.aaa", "equity.us.bbb"]

    def test_fd_missing_report_works(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")

        from findata import FinData
        fd_test = FinData()
        fd_test._store = store

        report = fd_test.missing_report(["AAA"])
        assert report["missing"].sum() == 0


# ── fd singleton deferred import tests ─────────────────────────────────────

class TestFdSingletonDeferred:
    def test_fd_singleton_imports_cleanly(self):
        """Verify that importing fd does not crash."""
        from findata import fd
        assert fd is not None

    def test_fd_has_all_public_methods(self):
        from findata import fd
        public_methods = [
            "prices", "ohlcv", "panel", "returns", "metrics",
            "rate", "fx_rate", "observations", "latest_observation",
            "observation_series", "observation_coverage",
            "export", "list_assets", "missing_report",
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

        from findata import FinData
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

        from findata import FinData
        fd_test = FinData()
        fd_test._store = store

        panel = fd_test.panel(["AAA", "BBB"])
        assert panel.shape == (60, 2)
