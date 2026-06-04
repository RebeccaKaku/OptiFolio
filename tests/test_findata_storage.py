"""Tests for the FinData storage department — QualityGate, CanonicalStore, and fd singleton."""

from __future__ import annotations

import pandas as pd
import pytest

from FinData import fd as fd_import
from FinData.storage_dept.quality import QualityGate, QualityReport
from FinData.storage_dept.store import CanonicalStore
from FinData.storage_dept.schemas import CANONICAL_COLUMNS, store_version


# ── Helpers ────────────────────────────────────────────────────────────

def _make_df(dates=None, close=None, extra_cols=None):
    """Build a minimal OHLCV-style DataFrame for testing."""
    if dates is None:
        dates = pd.date_range("2024-01-01", periods=20, freq="B")
    if close is None:
        import numpy as np
        close = np.linspace(100, 120, len(dates))
    data = {"date": dates, "close": close}
    if extra_cols:
        data.update(extra_cols)
    return pd.DataFrame(data)


# ── QualityGate tests ──────────────────────────────────────────────────

class TestQualityGateRejectEmpty:
    def test_empty_dataframe_is_rejected(self):
        gate = QualityGate()
        report = gate.inspect(pd.DataFrame())
        assert not report.passed
        assert any("Empty DataFrame" in r for r in report.reject_reasons)
        assert report.checks[0]["name"] == "non_empty"
        assert not report.checks[0]["passed"]


class TestQualityGateRejectMissingClose:
    def test_no_close_column_is_rejected(self):
        gate = QualityGate()
        df = pd.DataFrame({"date": ["2024-01-01"], "open": [100], "volume": [1000]})
        report = gate.inspect(df)
        assert not report.passed
        assert any("Missing price column" in r for r in report.reject_reasons)


class TestQualityGateRejectTimeReversal:
    def test_new_data_older_than_existing_is_rejected(self):
        gate = QualityGate()
        new_df = _make_df(
            dates=pd.date_range("2023-01-01", periods=5, freq="B"),
            close=[10, 11, 12, 13, 14],
        )
        existing = _make_df(
            dates=pd.date_range("2024-01-01", periods=20, freq="B"),
            close=[100] * 20,
        )
        report = gate.inspect(new_df, existing_data=existing)
        assert not report.passed
        assert any("Newer data already exists" in r for r in report.reject_reasons)

    def test_new_data_same_or_newer_is_accepted(self):
        gate = QualityGate()
        new_df = _make_df(
            dates=pd.date_range("2024-06-01", periods=5, freq="B"),
            close=[130, 131, 132, 133, 134],
        )
        existing = _make_df(
            dates=pd.date_range("2024-01-01", periods=20, freq="B"),
            close=[100] * 20,
        )
        report = gate.inspect(new_df, existing_data=existing)
        assert report.passed


class TestQualityGateFlagFewRows:
    def test_few_rows_over_long_span_is_flagged_not_rejected(self):
        gate = QualityGate()
        df = _make_df(
            dates=["2024-01-01", "2024-06-15", "2024-12-31"],
            close=[100, 105, 110],
        )
        report = gate.inspect(df)
        # Should pass (not rejected), but flagged
        assert report.passed
        assert any("Suspiciously few rows" in f for f in report.flags)

    def test_enough_rows_over_short_span_is_not_flagged(self):
        gate = QualityGate()
        df = _make_df()  # 20 rows over ~1 month
        report = gate.inspect(df)
        assert report.passed
        assert not any("Suspiciously few rows" in f for f in report.flags)


class TestQualityGateFlagPriceSpike:
    def test_extreme_daily_change_is_flagged(self):
        gate = QualityGate()
        df = _make_df(
            dates=pd.date_range("2024-01-01", periods=10, freq="B"),
            close=[100, 101, 102, 103, 104, 200, 201, 202, 203, 204],
        )
        report = gate.inspect(df)
        assert report.passed  # spike is a flag, not reject
        assert any("Extreme price movements" in f for f in report.flags)

    def test_normal_changes_not_flagged(self):
        gate = QualityGate()
        df = _make_df()  # smooth 100→120
        report = gate.inspect(df)
        assert report.passed
        assert not any("Extreme price movements" in f for f in report.flags)


class TestQualityGateRejectNaN:
    def test_majority_nan_in_close_is_rejected(self):
        gate = QualityGate()
        import numpy as np
        close_vals = [np.nan] * 15 + [100] * 5
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=20, freq="B"),
            "close": close_vals,
        })
        report = gate.inspect(df)
        assert not report.passed
        assert any("Majority NaN" in r for r in report.reject_reasons)


class TestQualityGateRejectDuplicate:
    def test_identical_data_is_rejected(self):
        gate = QualityGate()
        df = _make_df()
        report = gate.inspect(df, existing_data=df.copy())
        assert not report.passed
        assert any("Duplicate data" in r for r in report.reject_reasons)

    def test_different_data_is_not_duplicate(self):
        gate = QualityGate()
        new_df = _make_df(
            dates=pd.date_range("2024-06-01", periods=5, freq="B"),
            close=[200, 201, 202, 203, 204],
        )
        existing = _make_df(
            dates=pd.date_range("2024-01-01", periods=5, freq="B"),
            close=[100, 101, 102, 103, 104],
        )
        report = gate.inspect(new_df, existing_data=existing)
        assert report.passed


class TestQualityGatePassCleanData:
    def test_valid_data_passes_all_checks(self):
        gate = QualityGate()
        df = _make_df()  # 20 clean rows
        report = gate.inspect(df)
        assert report.passed
        assert len(report.reject_reasons) == 0
        # All 8 checks should have run
        assert len(report.checks) == 8

    def test_quality_report_has_expected_structure(self):
        gate = QualityGate()
        df = _make_df()
        report = gate.inspect(df)
        assert isinstance(report, QualityReport)
        assert isinstance(report.passed, bool)
        assert isinstance(report.checks, list)
        assert isinstance(report.reject_reasons, list)
        assert isinstance(report.flags, list)
        for check in report.checks:
            assert "name" in check
            assert "passed" in check
            assert "detail" in check

    def test_non_positive_prices_are_flagged(self):
        gate = QualityGate()
        df = _make_df(
            dates=pd.date_range("2024-01-01", periods=5, freq="B"),
            close=[100, 0, 102, -5, 104],
        )
        report = gate.inspect(df)
        # NaN check would fire first if we have 0 or negative — 0 and -5 are not NaN
        # Actually, the non-positive check is a FLAG, not a rejection.
        # But the validate_market_frame would reject <=0. The gate just flags.
        # Let's see: close values are [100, 0, 102, -5, 104]
        # NaN rate = 0/5 = 0% → pass
        # Non-positive = [0, -5] → flag
        assert any("Non-positive prices" in f for f in report.flags)


# ── CanonicalStore tests ───────────────────────────────────────────────

class TestCanonicalStoreAccept:
    def test_valid_data_is_stored(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        df = _make_df()
        report = store.accept(df, asset_id="TEST", source="unit", currency="USD")
        assert report.passed
        # Data should now be queryable
        prices = store.get_prices(["TEST"])
        assert not prices.empty
        assert "TEST" in prices.columns
        assert len(prices) == 20

    def test_multiple_assets_stored_and_queried(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")
        store.accept(
            _make_df(close=[50] * 20), asset_id="BBB", source="unit", currency="USD"
        )
        prices = store.get_prices(["AAA", "BBB"])
        assert list(prices.columns) == ["AAA", "BBB"]
        assert prices.shape == (20, 2)


class TestCanonicalStoreRejectDoesNotOverwrite:
    def test_rejected_data_does_not_touch_storage(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        # First, store valid data
        store.accept(_make_df(), asset_id="TEST", source="unit", currency="USD")

        # Then try to store empty data — should be rejected
        report = store.accept(pd.DataFrame(), asset_id="TEST", source="unit", currency="USD")
        assert not report.passed

        # The original data should still be intact
        prices = store.get_prices(["TEST"])
        assert len(prices) == 20  # original 20 rows still there


class TestCanonicalStoreDelegates:
    def test_list_assets(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")
        store.accept(_make_df(), asset_id="BBB", source="unit", currency="USD")
        assets = store.list_assets()
        assert sorted(assets) == ["AAA", "BBB"]

    def test_missing_report(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")
        store.accept(_make_df(), asset_id="BBB", source="unit", currency="USD")
        report = store.missing_report(["AAA", "BBB"])
        assert report["missing"].sum() == 0

    def test_get_returns(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")
        returns = store.get_returns(["AAA"])
        # 20 rows → 19 daily returns
        assert len(returns) == 19


# ── fd singleton tests ─────────────────────────────────────────────────

class TestFdPrices:
    def test_fd_prices_returns_series(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAPL", source="unit", currency="USD")

        # Create a fresh fd that points at the same store
        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        prices = fd_test.prices("AAPL")
        assert prices is not None
        assert isinstance(prices, pd.Series)
        assert len(prices) == 20

    def test_fd_prices_unknown_symbol_returns_none(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        prices = fd_test.prices("NONEXISTENT")
        assert prices is None


class TestFdPanel:
    def test_fd_panel_returns_pivoted_matrix(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")
        store.accept(
            _make_df(close=[50] * 20), asset_id="BBB", source="unit", currency="USD"
        )

        from FinData import FinData
        fd_test = FinData()
        fd_test._store = store

        panel = fd_test.panel(["AAA", "BBB"])
        assert isinstance(panel, pd.DataFrame)
        assert list(panel.columns) == ["AAA", "BBB"]
        assert panel.shape == (20, 2)


class TestFdSingleton:
    def test_same_instance_on_multiple_imports(self):
        import FinData
        from FinData import fd as fd1
        from FinData import fd as fd2

        assert fd1 is fd2
        assert fd1 is FinData.fd

    def test_fd_is_findata_instance(self):
        from FinData import fd, FinData
        assert isinstance(fd, FinData)


# ── Schemas tests ──────────────────────────────────────────────────────

class TestSchemas:
    def test_store_version_is_set(self):
        assert store_version == "1.0"

    def test_canonical_columns_contains_required_fields(self):
        required = {"asset_id", "date", "open", "high", "low", "close", "adj_close", "volume", "currency", "source", "timezone"}
        assert set(CANONICAL_COLUMNS) == required
