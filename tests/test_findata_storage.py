"""Tests for the FinData storage department — QualityGate, CanonicalStore, and fd singleton."""

from __future__ import annotations

import pandas as pd
import pytest

from findata import fd as fd_import
from findata.store import QualityGate, QualityReport
from findata.store import CanonicalStore
from findata.store.schemas import CANONICAL_MARKET_COLUMNS, STORE_VERSION


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


class TestQualityGateFlagFlatTradingDays:
    def test_flat_ohlcv_with_zero_volume_is_flagged(self):
        gate = QualityGate()
        import numpy as np
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=5, freq="B"),
            "open":  [100, 101, 102, 103, 104],
            "high":  [100, 101, 102, 103, 104],  # O=H rows 0-3
            "low":   [100, 101, 102, 103, 104],  # O=L rows 0-3
            "close": [100, 101, 102, 103, 104],  # O=C rows 0-3
            "volume": [1000, 0, 0, 1000, 1000],
        })
        report = gate.inspect(df)
        assert report.passed  # flag only, not reject
        assert any("Suspicious flat trading days" in f for f in report.flags)

    def test_normal_ohlcv_not_flagged(self):
        gate = QualityGate()
        import numpy as np
        df = _make_df(extra_cols={
            "open": np.linspace(99, 119, 20),
            "high": np.linspace(101, 121, 20),
            "low": np.linspace(98, 118, 20),
            "volume": [1000] * 20,
        })
        report = gate.inspect(df)
        assert report.passed
        assert not any("Suspicious flat trading days" in f for f in report.flags)


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
        # All 9 checks should have run
        assert len(report.checks) == 9

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

    def test_non_positive_prices_are_rejected(self):
        gate = QualityGate()
        df = _make_df(
            dates=pd.date_range("2024-01-01", periods=5, freq="B"),
            close=[100, 0, 102, -5, 104],
        )
        report = gate.inspect(df)
        # close values are [100, 0, 102, -5, 104]
        # NaN rate = 0/5 = 0% → pass NaN check
        # Non-positive = [0, -5] → REJECT
        assert not report.passed
        assert any("Non-positive prices" in r for r in report.reject_reasons)


# ── CanonicalStore tests ───────────────────────────────────────────────

class TestCanonicalStoreAccept:
    def test_valid_data_is_stored(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        df = _make_df()
        report = store.accept(df, asset_id="TEST", source="unit", currency="USD")
        assert report.passed
        # Data should now be queryable (canonical ID is equity.us.test)
        prices = store.get_prices(["TEST"])
        assert not prices.empty
        assert "equity.us.test" in prices.columns
        assert len(prices) == 20

    def test_multiple_assets_stored_and_queried(self, tmp_path):
        store = CanonicalStore(root_dir=str(tmp_path))
        store.accept(_make_df(), asset_id="AAA", source="unit", currency="USD")
        store.accept(
            _make_df(close=[50] * 20), asset_id="BBB", source="unit", currency="USD"
        )
        prices = store.get_prices(["AAA", "BBB"])
        assert list(prices.columns) == ["equity.us.aaa", "equity.us.bbb"]
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
        assert sorted(assets) == ["equity.us.aaa", "equity.us.bbb"]

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


# ── Schemas tests ──────────────────────────────────────────────────────

class TestSchemas:
    def test_store_version_is_set(self):
        assert STORE_VERSION == "2.0"

    def test_canonical_columns_contains_required_fields(self):
        required = {"asset_id", "date", "open", "high", "low", "close", "adj_close", "volume", "currency", "source", "timezone"}
        assert set(CANONICAL_MARKET_COLUMNS) == required


# ── Merged from test_data_foundation.py ──

import pandas as pd

from findata.store import MarketDataRepository
from findata.store.schemas import normalize_market_frame


def test_normalize_market_frame_accepts_provider_columns():
    raw = pd.DataFrame(
        {
            "Date": ["2024-01-01", "2024-01-02"],
            "Close": [100, 101],
            "Volume": [1000, 1100],
        }
    )

    normalized = normalize_market_frame(raw, asset_id="AAA", source="unit", currency="USD")

    assert list(normalized["asset_id"].unique()) == ["equity.us.aaa"]
    assert list(normalized["adj_close"]) == [100, 101]
    assert normalized["source"].eq("unit").all()


def test_normalize_market_frame_normalizes_cn_stock_ids():
    """sh/sz/bj prefixed and bare CN stock codes become canonical IDs."""
    raw = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02"],
        "close": [100, 101],
        "volume": [1000, 1100],
    })

    # sh-prefixed
    df_sh = normalize_market_frame(raw.copy(), asset_id="sh600519", source="unit", currency="CNY")
    assert df_sh["asset_id"].iloc[0] == "equity.cn.sh.600519"

    # sz-prefixed
    df_sz = normalize_market_frame(raw.copy(), asset_id="sz000001", source="unit", currency="CNY")
    assert df_sz["asset_id"].iloc[0] == "equity.cn.sz.000001"

    # Bare code with asset_type hint becomes canonical
    df_bare = normalize_market_frame(
        raw.copy(), asset_id="600028", source="unit", currency="CNY", asset_type="cn_stock"
    )
    assert df_bare["asset_id"].iloc[0] == "equity.cn.sh.600028"

    # Non-CN codes become canonical US equity IDs
    df_us = normalize_market_frame(raw.copy(), asset_id="AAPL", source="unit", currency="USD")
    assert df_us["asset_id"].iloc[0] == "equity.us.aapl"


def test_market_data_repository_saves_and_queries_price_matrix(tmp_path):
    repo = MarketDataRepository(tmp_path)
    repo.save_canonical(
        pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [100, 102, 101],
            }
        ),
        asset_id="AAA",
        source="unit",
        currency="USD",
    )
    repo.save_canonical(
        pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "close": [50, 51, 52],
            }
        ),
        asset_id="BBB",
        source="unit",
        currency="USD",
    )

    prices = repo.get_prices(["AAA", "BBB"], start="2024-01-02")
    returns = repo.get_returns(["AAA", "BBB"])
    report = repo.missing_report(["AAA", "BBB"])

    assert list(prices.columns) == ["equity.us.aaa", "equity.us.bbb"]
    assert prices.shape == (2, 2)
    assert returns.shape == (2, 2)
    assert report["missing"].sum() == 0


def test_market_data_repository_observations_round_trip(tmp_path):
    repo = MarketDataRepository(tmp_path)
    saved = repo.save_observations(
        pd.DataFrame({
            "effective_date": ["2024-01-31"],
            "value": [0.021],
            "known_at": ["2024-02-01T09:00:00"],
        }),
        series_id="rate.cn.shibor.1y",
        source="unit",
        unit="decimal",
        currency="CNY",
    )

    assert len(saved) == 1
    latest = repo.latest_observation("rate.cn.shibor.1y", as_of="2024-02-05")
    assert latest is not None
    assert latest["value"] == pytest.approx(0.021)
    assert latest["source"] == "unit"


def test_market_data_repository_observations_reject_future_leakage(tmp_path):
    repo = MarketDataRepository(tmp_path)
    with pytest.raises(ValueError, match="known_at cannot be before effective_date"):
        repo.save_observations(
            pd.DataFrame({
                "effective_date": ["2024-02-01"],
                "value": [0.021],
                "known_at": ["2024-01-31T09:00:00"],
            }),
            series_id="rate.cn.shibor.1y",
            source="unit",
        )


def test_market_data_repository_lists_observation_series(tmp_path):
    repo = MarketDataRepository(tmp_path)
    repo.save_observations(
        pd.DataFrame({
            "effective_date": ["2024-01-01", "2024-01-02"],
            "value": [0.01, 0.011],
        }),
        series_id="rate.us.sofr.on",
        source="unit",
        unit="decimal",
        currency="USD",
    )

    series = repo.list_observation_series()

    assert len(series) == 1
    assert series["series_id"].iloc[0] == "rate.us.sofr.on"
    assert series["observations"].iloc[0] == 2


def test_market_data_repository_observation_coverage_marks_missing(tmp_path):
    repo = MarketDataRepository(tmp_path)
    repo.save_observations(
        pd.DataFrame({
            "effective_date": ["2024-01-01"],
            "value": [0.01],
        }),
        series_id="rate.us.sofr.on",
        source="unit",
    )

    coverage = repo.observation_coverage(
        ["rate.us.sofr.on", "rate.uk.sonia.on"],
        expected_stale_days=5,
        as_of="2024-01-10",
    )
    by_id = {row["series_id"]: row for row in coverage.to_dict(orient="records")}

    assert by_id["rate.us.sofr.on"]["stale_days"] == 9
    assert by_id["rate.us.sofr.on"]["is_stale"] is True
    assert by_id["rate.uk.sonia.on"]["missing"] is True
