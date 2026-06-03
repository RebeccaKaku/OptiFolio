"""Tests for the FX return decomposition module."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.analytics.returns import FxDecomposition, ReturnAnalyzer


# ── helpers ────────────────────────────────────────────────────────────────

def _make_equity_curve(
    dates: list,
    total: list,
    **currency_values: list,
) -> pd.DataFrame:
    """Build a test equity curve DataFrame."""
    data = {"date": pd.to_datetime(dates), "total_value": total}
    for cur, vals in currency_values.items():
        data[cur] = vals
    return pd.DataFrame(data)


def _make_fx_series(dates: list, rates: list) -> pd.Series:
    """Build a pd.Series of FX rates indexed by date."""
    return pd.Series(rates, index=pd.to_datetime(dates))


# ── FxDecomposition unit tests ─────────────────────────────────────────────

class TestFxDecomposition:
    """Unit tests for the FxDecomposition dataclass and decompose_fx()."""

    def test_basic_decomposition_positive_returns(self):
        """Happy path: both asset and FX contribute positively."""
        d = date(2025, 1, 1)
        decomp = ReturnAnalyzer.decompose_fx(
            start_value=100_000, end_value=110_000,
            start_fx=7.0, end_fx=7.7,
            period_start=d, period_end=date(2025, 1, 31),
            base_currency="CNY",
        )
        # base return = 110k/100k - 1 = 0.10
        assert decomp.base_return == pytest.approx(0.10)
        # local value end = 110000/7.7, start = 100000/7.0
        assert decomp.local_return == pytest.approx(0.0)  # price flat, FX moved
        # fx return = 7.7/7.0 - 1 = 0.10
        assert decomp.fx_return == pytest.approx(0.10)
        # interaction = 0 * 0.10 = 0
        assert decomp.interaction == pytest.approx(0.0)

    def test_roundtrip_identity(self):
        """(1 + r_base) must equal (1 + r_local) × (1 + r_fx)."""
        decomp = ReturnAnalyzer.decompose_fx(
            start_value=100_000, end_value=108_000,
            start_fx=7.2, end_fx=6.8,
            period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
            base_currency="CNY",
        )
        lhs = 1 + decomp.base_return
        rhs = (1 + decomp.local_return) * (1 + decomp.fx_return)
        assert lhs == pytest.approx(rhs, rel=1e-12)

    def test_roundtrip_identity_many_scenarios(self):
        """Verify the roundtrip identity across a range of scenarios."""
        scenarios = [
            # (start_v, end_v, start_fx, end_fx)
            (100, 100, 1.0, 1.0),          # no change
            (100, 110, 1.0, 1.0),           # pure asset gain, no FX
            (100, 100, 1.0, 1.1),           # pure FX gain, no asset
            (100, 110, 1.0, 1.1),           # both positive
            (100, 90, 1.0, 1.0),            # asset loss
            (100, 100, 1.0, 0.9),           # FX loss
            (100, 90, 1.0, 0.9),            # both negative
            (100, 95, 7.2, 7.0),            # mixed: asset up, FX down
            (100, 105, 7.0, 7.5),           # mixed: asset down, FX up
            (100_000, 98_500, 6.8, 7.1),    # realistic large values
        ]
        for sv, ev, s_fx, e_fx in scenarios:
            decomp = ReturnAnalyzer.decompose_fx(
                start_value=sv, end_value=ev,
                start_fx=s_fx, end_fx=e_fx,
                period_start=date(2025, 1, 1), period_end=date(2025, 1, 2),
                base_currency="CNY",
            )
            lhs = 1 + decomp.base_return
            rhs = (1 + decomp.local_return) * (1 + decomp.fx_return)
            assert lhs == pytest.approx(rhs, rel=1e-12), (
                f"Roundtrip failed: sv={sv}, ev={ev}, "
                f"s_fx={s_fx}, e_fx={e_fx}"
            )

    def test_sum_decomposition(self):
        """r_base = r_local + r_fx + interaction."""
        decomp = ReturnAnalyzer.decompose_fx(
            start_value=100_000, end_value=102_000,
            start_fx=7.2, end_fx=7.3,
            period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
            base_currency="CNY",
        )
        expected = decomp.local_return + decomp.fx_return + decomp.interaction
        assert decomp.base_return == pytest.approx(expected, rel=1e-12)

    def test_pure_fx_move_local_flat(self):
        """When the local asset value is unchanged, base return = FX return."""
        # value_base = local_value * fx.  If local_value is constant,
        # then end_value / start_value = end_fx / start_fx.
        start_fx = 7.2
        end_fx = 6.48  # -10%
        local_value = 10_000  # constant in local currency
        start_value = local_value * start_fx
        end_value = local_value * end_fx

        decomp = ReturnAnalyzer.decompose_fx(
            start_value=start_value, end_value=end_value,
            start_fx=start_fx, end_fx=end_fx,
            period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
            base_currency="CNY",
        )
        assert decomp.local_return == pytest.approx(0.0, abs=1e-12)
        assert decomp.base_return == pytest.approx(decomp.fx_return, rel=1e-12)

    def test_pure_asset_move_fx_flat(self):
        """When FX is flat, base return = local return."""
        decomp = ReturnAnalyzer.decompose_fx(
            start_value=100_000, end_value=105_000,
            start_fx=7.0, end_fx=7.0,
            period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
            base_currency="CNY",
        )
        assert decomp.fx_return == pytest.approx(0.0, abs=1e-12)
        assert decomp.base_return == pytest.approx(decomp.local_return, rel=1e-12)
        assert decomp.interaction == pytest.approx(0.0, abs=1e-12)

    def test_negative_base_return(self):
        """Decomposition works correctly for losses."""
        decomp = ReturnAnalyzer.decompose_fx(
            start_value=100_000, end_value=90_000,
            start_fx=7.0, end_fx=6.3,
            period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
            base_currency="CNY",
        )
        assert decomp.base_return == pytest.approx(-0.10)
        lhs = 1 + decomp.base_return
        rhs = (1 + decomp.local_return) * (1 + decomp.fx_return)
        assert lhs == pytest.approx(rhs, rel=1e-12)

    def test_zero_fx_change_nonzero_asset(self):
        """Zero FX return, positive local return."""
        decomp = ReturnAnalyzer.decompose_fx(
            start_value=100_000, end_value=110_000,
            start_fx=7.2, end_fx=7.2,
            period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
            base_currency="CNY",
        )
        assert decomp.fx_return == 0.0
        assert decomp.interaction == 0.0
        assert decomp.local_return == pytest.approx(0.10)

    def test_value_error_on_zero_start_value(self):
        with pytest.raises(ValueError, match="start_value must be positive"):
            ReturnAnalyzer.decompose_fx(
                start_value=0, end_value=100,
                start_fx=7.0, end_fx=7.0,
                period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
            )

    def test_value_error_on_zero_start_fx(self):
        with pytest.raises(ValueError, match="start_fx must be positive"):
            ReturnAnalyzer.decompose_fx(
                start_value=100, end_value=100,
                start_fx=0, end_fx=7.0,
                period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
            )

    def test_negative_start_value_raises(self):
        with pytest.raises(ValueError, match="start_value must be positive"):
            ReturnAnalyzer.decompose_fx(
                start_value=-100, end_value=100,
                start_fx=7.0, end_fx=7.0,
                period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
            )

    # ── dataclass ──────────────────────────────────────────────────────

    def test_is_frozen(self):
        decomp = ReturnAnalyzer.decompose_fx(
            start_value=100, end_value=110,
            start_fx=7.0, end_fx=7.0,
            period_start=date(2025, 1, 1), period_end=date(2025, 1, 2),
        )
        from dataclasses import FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            decomp.base_return = 0.99  # type: ignore[misc]

    def test_to_dict_keys(self):
        decomp = ReturnAnalyzer.decompose_fx(
            start_value=100_000, end_value=105_000,
            start_fx=7.2, end_fx=7.0,
            period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
            base_currency="CNY",
        )
        d = decomp.to_dict()
        expected_keys = {
            "period_start", "period_end", "base_return", "local_return",
            "fx_return", "interaction", "base_currency",
        }
        assert set(d.keys()) == expected_keys
        assert d["base_currency"] == "CNY"
        assert isinstance(d["period_start"], str)
        assert isinstance(d["period_end"], str)
        assert all(isinstance(d[k], (int, float)) for k in expected_keys - {"period_start", "period_end", "base_currency"})

    def test_to_dict_roundtrip_values(self):
        decomp = ReturnAnalyzer.decompose_fx(
            start_value=100_000, end_value=105_000,
            start_fx=7.2, end_fx=7.0,
            period_start=date(2025, 6, 15), period_end=date(2025, 7, 15),
            base_currency="USD",
        )
        d = decomp.to_dict()
        assert d["period_start"] == "2025-06-15"
        assert d["period_end"] == "2025-07-15"
        assert d["base_currency"] == "USD"
        # to_dict rounds to 6 decimal places — use abs tolerance
        assert d["base_return"] == pytest.approx(decomp.base_return, abs=1e-6)
        assert d["local_return"] == pytest.approx(decomp.local_return, abs=1e-6)
        assert d["fx_return"] == pytest.approx(decomp.fx_return, abs=1e-6)


# ── compute_returns tests ───────────────────────────────────────────────────

class TestComputeReturns:
    """Tests for ReturnAnalyzer.compute_returns()."""

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["date", "total_value"])
        result = ReturnAnalyzer.compute_returns(df)
        assert result.empty
        assert list(result.columns) == [
            "date", "base_return", "local_return", "fx_return", "interaction",
        ]

    def test_single_row_returns_empty(self):
        df = _make_equity_curve(["2025-01-01"], [100_000])
        result = ReturnAnalyzer.compute_returns(df)
        assert result.empty

    def test_simple_two_day_equity_curve(self):
        """Without FX rates, local_return == base_return."""
        df = _make_equity_curve(
            ["2025-01-01", "2025-01-02", "2025-01-03"],
            [100_000, 101_000, 103_020],
        )
        result = ReturnAnalyzer.compute_returns(df)
        assert len(result) == 2
        # Day 1: (101000/100000 - 1) = 0.01
        assert result.iloc[0]["base_return"] == pytest.approx(0.01)
        assert result.iloc[0]["local_return"] == pytest.approx(0.01)
        assert result.iloc[0]["fx_return"] == pytest.approx(0.0)
        assert result.iloc[0]["interaction"] == pytest.approx(0.0)
        # Day 2: (103020/101000 - 1) = 0.02
        assert result.iloc[1]["base_return"] == pytest.approx(0.02)

    def test_simple_equity_curve_with_date_column(self):
        """Equity curve with 'date' as a column (not index)."""
        df = pd.DataFrame({
            "date": pd.to_datetime(["2025-01-01", "2025-01-02"]),
            "total_value": [100_000, 102_000],
        })
        result = ReturnAnalyzer.compute_returns(df)
        assert len(result) == 1
        assert result.iloc[0]["base_return"] == pytest.approx(0.02)

    def test_multi_currency_decomposition(self):
        """Portfolio with USD and CNY positions + FX rates."""
        dates = ["2025-01-01", "2025-01-02", "2025-01-03"]
        df = _make_equity_curve(
            dates,
            total=[100_000, 102_000, 105_000],
            USD=[60_000, 61_500, 63_000],
            CNY=[40_000, 40_500, 42_000],
        )
        fx_rates = {
            "USD": _make_fx_series(dates, [7.2, 7.1, 7.0]),
            "CNY": _make_fx_series(dates, [1.0, 1.0, 1.0]),
        }
        result = ReturnAnalyzer.compute_returns(df, fx_rates=fx_rates)
        assert len(result) == 2

        # Check roundtrip identity for each period
        for _, row in result.iterrows():
            lhs = 1 + row["base_return"]
            rhs = (1 + row["local_return"]) * (1 + row["fx_return"])
            assert lhs == pytest.approx(rhs, rel=1e-10), (
                f"Roundtrip failed: {row.to_dict()}"
            )

    def test_multi_currency_fx_not_provided_falls_back(self):
        """When currency cols exist but no fx_rates, local = base."""
        df = _make_equity_curve(
            ["2025-01-01", "2025-01-02"],
            total=[100_000, 102_000],
            USD=[60_000, 61_500],
        )
        result = ReturnAnalyzer.compute_returns(df, fx_rates=None)
        assert len(result) == 1
        assert result.iloc[0]["local_return"] == pytest.approx(0.02)
        assert result.iloc[0]["fx_return"] == pytest.approx(0.0)

    def test_weighted_average_different_asset_growth(self):
        """USD assets grow 5%, CNY assets grow 0%, USD/CNY drops 2%."""
        dates = ["2025-01-01", "2025-01-02"]
        fx_usd = [7.2, 7.056]  # -2%
        # USD value: local = 10000, fx moves from 7.2 to 7.056
        # base_start = 10000 * 7.2 = 72000, local grows 5%
        # local_end = 10500, base_end = 10500 * 7.056 = 74088
        # CNY value: constant at 28000 (no growth)
        df = _make_equity_curve(
            dates,
            total=[100_000, 102_088],  # 72000 + 28000 start; 74088 + 28000 end
            USD=[72_000, 74_088],       # local: 10000 -> 10500, fx: 7.2 -> 7.056
            CNY=[28_000, 28_000],       # flat
        )
        fx_rates = {
            "USD": _make_fx_series(dates, fx_usd),
            "CNY": _make_fx_series(dates, [1.0, 1.0]),
        }
        result = ReturnAnalyzer.compute_returns(df, fx_rates=fx_rates)
        assert len(result) == 1

        row = result.iloc[0]
        # Base return = 102088 / 100000 - 1 = 0.02088
        assert row["base_return"] == pytest.approx(0.02088, rel=1e-5)
        # Roundtrip
        lhs = 1 + row["base_return"]
        rhs = (1 + row["local_return"]) * (1 + row["fx_return"])
        assert lhs == pytest.approx(rhs, rel=1e-10)

    def test_nan_values_handled(self):
        """NaN total_value rows should result in NaN returns, not crash."""
        df = _make_equity_curve(
            ["2025-01-01", "2025-01-02", "2025-01-03"],
            [100_000, np.nan, 105_000],
        )
        result = ReturnAnalyzer.compute_returns(df)
        assert len(result) == 2
        assert np.isnan(result.iloc[0]["base_return"])  # NaN at end
        assert np.isnan(result.iloc[1]["base_return"])  # NaN at start

    def test_zero_start_value_skipped(self):
        df = _make_equity_curve(
            ["2025-01-01", "2025-01-02", "2025-01-03"],
            [0, 100_000, 102_000],
        )
        result = ReturnAnalyzer.compute_returns(df)
        assert len(result) == 2
        assert np.isnan(result.iloc[0]["base_return"])  # start=0 → NaN
        assert result.iloc[1]["base_return"] == pytest.approx(0.02)  # normal

    def test_missing_total_value_column_raises(self):
        df = pd.DataFrame({"date": pd.to_datetime(["2025-01-01"]), "wrong_col": [100]})
        with pytest.raises(ValueError, match="total_value"):
            ReturnAnalyzer.compute_returns(df)

    def test_already_indexed_dataframe(self):
        """Works when equity_curve already has a DatetimeIndex."""
        idx = pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"])
        df = pd.DataFrame({"total_value": [100_000, 102_000, 101_000]}, index=idx)
        result = ReturnAnalyzer.compute_returns(df)
        assert len(result) == 2
        assert result.iloc[0]["base_return"] == pytest.approx(0.02)

    def test_output_columns_and_types(self):
        df = _make_equity_curve(
            ["2025-01-01", "2025-01-02"],
            [100_000, 102_000],
        )
        result = ReturnAnalyzer.compute_returns(df)
        expected_cols = ["date", "base_return", "local_return", "fx_return", "interaction"]
        assert list(result.columns) == expected_cols
        assert pd.api.types.is_datetime64_any_dtype(result["date"])
        for col in ["base_return", "local_return", "fx_return", "interaction"]:
            assert result[col].dtype == np.float64


# ── decompose_period tests ──────────────────────────────────────────────────

class TestDecomposePeriod:
    """Tests for ReturnAnalyzer.decompose_period()."""

    def test_simple_period_no_fx(self):
        df = _make_equity_curve(
            ["2025-01-01", "2025-01-15", "2025-01-31"],
            [100_000, 103_000, 106_000],
        )
        decomp = ReturnAnalyzer.decompose_period(
            equity_curve=df,
            fx_rates={},
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
        )
        assert decomp.base_return == pytest.approx(0.06)
        assert decomp.local_return == pytest.approx(0.06)
        assert decomp.fx_return == pytest.approx(0.0)

    def test_period_with_fx(self):
        dates = ["2025-01-01", "2025-01-15", "2025-01-31"]
        # USD local value grows ~5.56%, CNY flat
        # USD/CNY: 7.2 -> 7.0 (-2.78%)
        df = _make_equity_curve(
            dates,
            total=[100_000, 102_000, 104_500],
            USD=[60_000, 61_200, 62_500],
            CNY=[40_000, 40_800, 42_000],
        )
        fx_rates = {
            "USD": _make_fx_series(dates, [7.2, 7.1, 7.0]),
            "CNY": _make_fx_series(dates, [1.0, 1.0, 1.0]),
        }
        decomp = ReturnAnalyzer.decompose_period(
            equity_curve=df,
            fx_rates=fx_rates,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
        )
        # Verify roundtrip
        lhs = 1 + decomp.base_return
        rhs = (1 + decomp.local_return) * (1 + decomp.fx_return)
        assert lhs == pytest.approx(rhs, rel=1e-10)
        assert decomp.base_return == pytest.approx(0.045)

    def test_period_closest_dates(self):
        """When exact dates are not in the equity curve, nearest dates are used."""
        df = _make_equity_curve(
            ["2025-01-02", "2025-01-10", "2025-01-20"],
            [100_000, 102_000, 105_000],
        )
        decomp = ReturnAnalyzer.decompose_period(
            equity_curve=df,
            fx_rates={},
            period_start=date(2025, 1, 1),   # before first date → snapped to 01-02
            period_end=date(2025, 1, 25),     # after last date → snapped to 01-20
        )
        assert decomp.base_return == pytest.approx(0.05)

    def test_period_start_before_data_snaps_to_first(self):
        """When period_start is before the earliest data, snap to first date."""
        df = _make_equity_curve(
            ["2025-01-10", "2025-01-15"],
            [100_000, 102_000],
        )
        decomp = ReturnAnalyzer.decompose_period(
            equity_curve=df,
            fx_rates={},
            period_start=date(2025, 1, 1),   # before all data → snaps to Jan 10
            period_end=date(2025, 1, 15),
        )
        assert decomp.period_start == date(2025, 1, 10)
        assert decomp.period_end == date(2025, 1, 15)
        assert decomp.base_return == pytest.approx(0.02)

    def test_period_end_after_data_snaps_to_last(self):
        """When period_end is after the latest data, snap to last date."""
        df = _make_equity_curve(
            ["2025-01-10", "2025-01-15"],
            [100_000, 102_000],
        )
        decomp = ReturnAnalyzer.decompose_period(
            equity_curve=df,
            fx_rates={},
            period_start=date(2025, 1, 10),
            period_end=date(2025, 2, 1),     # after all data → snaps to Jan 15
        )
        assert decomp.period_start == date(2025, 1, 10)
        assert decomp.period_end == date(2025, 1, 15)
        assert decomp.base_return == pytest.approx(0.02)


# ── integration-style tests ─────────────────────────────────────────────────

class TestReturnAnalyzerIntegration:
    """End-to-end scenarios combining decompose_fx and compute_returns."""

    def test_decompose_fx_matches_compute_returns_single_currency(self):
        """Single-currency compute_returns should match decompose_fx for each period."""
        dates = ["2025-01-01", "2025-01-02", "2025-01-03"]
        df = _make_equity_curve(dates, total=[100_000, 102_000, 101_000])
        result = ReturnAnalyzer.compute_returns(df)

        for i, (_, row) in enumerate(result.iterrows()):
            t0 = dates[i]
            t1 = dates[i + 1] if i + 1 < len(dates) else None
            if t1 is None:
                break
            decomp = ReturnAnalyzer.decompose_fx(
                start_value=df.loc[df["date"] == t0, "total_value"].iloc[0],
                end_value=df.loc[df["date"] == t1, "total_value"].iloc[0],
                start_fx=1.0,
                end_fx=1.0,
                period_start=pd.Timestamp(t0).date(),
                period_end=pd.Timestamp(t1).date(),
            )
            assert row["base_return"] == pytest.approx(decomp.base_return)
            assert row["local_return"] == pytest.approx(decomp.local_return)

    def test_large_numerical_stability(self):
        """Ensure no floating-point issues with large values."""
        decomp = ReturnAnalyzer.decompose_fx(
            start_value=1_000_000_000.0,
            end_value=1_000_000_001.0,
            start_fx=123.456789,
            end_fx=123.456788,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 2),
        )
        lhs = 1 + decomp.base_return
        rhs = (1 + decomp.local_return) * (1 + decomp.fx_return)
        assert lhs == pytest.approx(rhs, rel=1e-12)

    def test_to_dict_all_fields_serializable(self):
        """Ensure to_dict() output is JSON-safe."""
        decomp = ReturnAnalyzer.decompose_fx(
            start_value=100_000, end_value=105_000,
            start_fx=7.2, end_fx=7.0,
            period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
            base_currency="CNY",
        )
        d = decomp.to_dict()
        import json
        json.dumps(d)  # must not raise
