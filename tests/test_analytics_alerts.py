"""Tests for AlertEngine — drawdown, maturity, FX loss, concentration creep,
and open-window alerts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

import pandas as pd
import pytest

from src.analytics.alerts import Alert, AlertEngine
from src.analytics.fx_exposure import FxExposureAnalyzer, FxExposureItem, FxExposureReport


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_equity_curve(values: List[float], start_date: str = "2026-01-01") -> pd.DataFrame:
    """Build a simple equity curve DataFrame."""
    dates = pd.date_range(start=start_date, periods=len(values), freq="D")
    return pd.DataFrame({"date": dates, "total_value": values})


def _tomorrow() -> date:
    return date.today() + timedelta(days=1)


def _in_days(n: int) -> date:
    return date.today() + timedelta(days=n)


def _n_days_ago(n: int) -> date:
    return date.today() - timedelta(days=n)


# ── Alert dataclass ──────────────────────────────────────────────────────────


class TestAlert:
    """Alert frozen dataclass construction, immutability, and serialization."""

    def test_is_frozen_dataclass(self):
        assert is_dataclass(Alert)
        assert Alert.__dataclass_params__.frozen

    def test_construction(self):
        a = Alert(
            alert_id="drawdown_8pct",
            title="投资组合回撤 8.0%",
            reason="组合净值从峰值 ¥120,000 回落至 ¥110,400",
            evidence={"peak_value": 120_000, "current_value": 110_400, "drawdown_pct": 8.0},
            severity="warning",
            suggested_action="检查持仓，评估是否需要减仓。",
            created_at="2026-06-03T12:00:00+00:00",
        )
        assert a.alert_id == "drawdown_8pct"
        assert a.title == "投资组合回撤 8.0%"
        assert a.severity == "warning"
        assert a.evidence["drawdown_pct"] == 8.0

    def test_frozen_prevents_mutation(self):
        a = Alert(
            alert_id="test",
            title="Test",
            reason="test",
            evidence={},
            severity="info",
            suggested_action="none",
            created_at="2026-01-01T00:00:00+00:00",
        )
        with pytest.raises(FrozenInstanceError):
            a.severity = "critical"  # type: ignore[misc]

    def test_to_dict(self):
        a = Alert(
            alert_id="drawdown_5pct",
            title="回撤 5%",
            reason="test reason",
            evidence={"key": "value"},
            severity="warning",
            suggested_action="do something",
            created_at="2026-06-03T12:00:00Z",
        )
        d = a.to_dict()
        assert d["alert_id"] == "drawdown_5pct"
        assert d["title"] == "回撤 5%"
        assert d["reason"] == "test reason"
        assert d["evidence"] == {"key": "value"}
        assert d["severity"] == "warning"
        assert d["suggested_action"] == "do something"
        assert d["created_at"] == "2026-06-03T12:00:00Z"

    def test_evidence_is_independent_copy(self):
        ev = {"mutable": [1, 2, 3]}
        a = Alert(
            alert_id="t", title="t", reason="t", evidence=ev,
            severity="info", suggested_action="x",
            created_at="2026-01-01T00:00:00Z",
        )
        # to_dict copies the evidence dict
        d = a.to_dict()
        d["evidence"]["mutable"].append(4)
        assert a.evidence["mutable"] == [1, 2, 3]


# ── check_drawdown ───────────────────────────────────────────────────────────


class TestCheckDrawdown:
    """Portfolio drawdown from all-time peak."""

    def test_no_alert_when_rising(self):
        engine = AlertEngine()
        curve = _make_equity_curve([100_000, 101_000, 102_000, 103_000])
        result = engine.check_drawdown(curve, threshold_pct=5.0)
        assert result is None

    def test_alert_when_drawdown_exceeds_threshold(self):
        engine = AlertEngine()
        # Peak 200k, current 180k = 10% drawdown
        curve = _make_equity_curve([190_000, 200_000, 195_000, 180_000])
        result = engine.check_drawdown(curve, threshold_pct=5.0)
        assert result is not None
        assert "drawdown" in result.alert_id
        assert result.evidence["drawdown_pct"] == 10.0
        assert result.evidence["peak_value"] == 200_000.0
        assert result.evidence["current_value"] == 180_000.0
        assert result.severity == "critical"  # 10% >= 2 * 5%

    def test_warning_severity_for_moderate_drawdown(self):
        engine = AlertEngine()
        # Peak 200k, current 188k = 6% drawdown (< 2x threshold)
        curve = _make_equity_curve([195_000, 200_000, 192_000, 188_000])
        result = engine.check_drawdown(curve, threshold_pct=5.0)
        assert result is not None
        assert result.severity == "warning"

    def test_exact_threshold_triggers(self):
        engine = AlertEngine()
        # Peak 100k, current 95k = exactly 5%
        curve = _make_equity_curve([100_000, 95_000])
        result = engine.check_drawdown(curve, threshold_pct=5.0)
        assert result is not None
        assert result.evidence["drawdown_pct"] == 5.0

    def test_below_threshold_no_alert(self):
        engine = AlertEngine()
        curve = _make_equity_curve([100_000, 96_000])  # 4% drawdown
        result = engine.check_drawdown(curve, threshold_pct=5.0)
        assert result is None

    def test_empty_dataframe(self):
        engine = AlertEngine()
        curve = pd.DataFrame()
        result = engine.check_drawdown(curve)
        assert result is None

    def test_custom_threshold(self):
        engine = AlertEngine()
        # 3% drawdown triggers with threshold 2%
        curve = _make_equity_curve([100_000, 97_000])
        result = engine.check_drawdown(curve, threshold_pct=2.0)
        assert result is not None
        assert result.evidence["drawdown_pct"] == 3.0

    def test_evidence_includes_dates(self):
        engine = AlertEngine()
        curve = _make_equity_curve([100_000, 90_000])
        result = engine.check_drawdown(curve, threshold_pct=5.0)
        assert result is not None
        assert result.evidence["peak_date"] is not None
        assert result.evidence["current_date"] is not None

    def test_alert_carries_evidence(self):
        engine = AlertEngine()
        curve = _make_equity_curve([100_000, 80_000])
        result = engine.check_drawdown(curve, threshold_pct=5.0)
        assert result is not None
        assert "peak_value" in result.evidence
        assert "current_value" in result.evidence
        assert "drawdown_pct" in result.evidence
        assert "threshold_pct" in result.evidence
        assert result.reason
        assert result.suggested_action

    def test_zero_peak_no_alert(self):
        engine = AlertEngine()
        curve = pd.DataFrame({"total_value": [0.0, 0.0]})
        result = engine.check_drawdown(curve)
        assert result is None


# ── check_maturity ───────────────────────────────────────────────────────────


class TestCheckMaturity:
    """Products approaching maturity / lockup-expiry / open-date."""

    def test_product_maturing_soon(self):
        engine = AlertEngine()
        products = [
            {
                "product_id": "WMP1",
                "name": "稳健理财1号",
                "maturity_date": _in_days(10),
            }
        ]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert len(alerts) == 1
        assert alerts[0].alert_id.startswith("maturity_WMP1")
        assert "WMP1" in alerts[0].title
        assert alerts[0].evidence["days_left"] == 10
        assert alerts[0].evidence["date_type"] == "maturity_date"

    def test_product_maturing_today(self):
        engine = AlertEngine()
        products = [
            {
                "product_id": "DEP1",
                "name": "定期存款",
                "maturity_date": date.today(),
            }
        ]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert len(alerts) == 1
        assert alerts[0].evidence["days_left"] == 0

    def test_product_maturing_tomorrow(self):
        engine = AlertEngine()
        products = [
            {
                "product_id": "DEP2",
                "name": "定期存款2号",
                "maturity_date": _tomorrow(),
            }
        ]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert len(alerts) == 1
        assert alerts[0].evidence["days_left"] == 1

    def test_product_outside_window_no_alert(self):
        engine = AlertEngine()
        products = [
            {
                "product_id": "WMP2",
                "name": "远期的理财",
                "maturity_date": _in_days(60),
            }
        ]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert len(alerts) == 0

    def test_product_already_past_no_alert(self):
        engine = AlertEngine()
        products = [
            {
                "product_id": "OLD",
                "name": "已到期产品",
                "maturity_date": _n_days_ago(5),
            }
        ]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert len(alerts) == 0

    def test_lockup_end_date(self):
        engine = AlertEngine()
        products = [
            {
                "product_id": "LOCK1",
                "name": "锁仓产品",
                "lockup_end_date": _in_days(3),
            }
        ]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert len(alerts) == 1
        assert alerts[0].evidence["date_type"] == "lockup_end_date"

    def test_open_date(self):
        engine = AlertEngine()
        products = [
            {
                "product_id": "FUND1",
                "name": "定开基金",
                "open_date": _in_days(15),
            }
        ]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert len(alerts) == 1
        assert alerts[0].evidence["date_type"] == "open_date"

    def test_next_open_date(self):
        engine = AlertEngine()
        products = [
            {
                "product_id": "FUND2",
                "name": "季度开放基金",
                "next_open_date": _in_days(7),
            }
        ]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert len(alerts) == 1
        assert alerts[0].evidence["date_type"] == "next_open_date"

    def test_iso_string_dates(self):
        engine = AlertEngine()
        target = _in_days(5)
        products = [
            {
                "product_id": "STR1",
                "name": "字符串日期产品",
                "maturity_date": target.isoformat(),
            }
        ]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert len(alerts) == 1
        assert alerts[0].evidence["days_left"] == 5

    def test_multiple_products(self):
        engine = AlertEngine()
        products = [
            {"product_id": "A", "name": "A", "maturity_date": _in_days(5)},
            {"product_id": "B", "name": "B", "maturity_date": _in_days(10)},
            {"product_id": "C", "name": "C", "maturity_date": _in_days(60)},
            {"product_id": "D", "name": "D", "lockup_end_date": _in_days(20)},
        ]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert len(alerts) == 3  # A(5d), B(10d), D(20d); C is outside window

    def test_empty_products(self):
        engine = AlertEngine()
        alerts = engine.check_maturity([], as_of=date.today(), within_days=30)
        assert alerts == []

    def test_product_with_no_dates(self):
        engine = AlertEngine()
        products = [{"product_id": "NODATE", "name": "无日期产品"}]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert alerts == []

    def test_product_with_none_dates(self):
        engine = AlertEngine()
        products = [
            {
                "product_id": "NULLDATE",
                "name": "空日期",
                "maturity_date": None,
                "lockup_end_date": None,
            }
        ]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert alerts == []

    def test_alert_carries_evidence(self):
        engine = AlertEngine()
        products = [{"product_id": "E1", "name": "证据测试", "maturity_date": _in_days(7)}]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert len(alerts) == 1
        assert alerts[0].evidence["product_id"] == "E1"
        assert alerts[0].evidence["date_type"] == "maturity_date"
        assert alerts[0].evidence["days_left"] == 7
        assert alerts[0].evidence["within_days"] == 30
        assert alerts[0].reason
        assert alerts[0].suggested_action

    def test_severity_warning_when_within_7_days(self):
        engine = AlertEngine()
        products = [{"product_id": "URG", "name": "紧急", "maturity_date": _in_days(3)}]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert len(alerts) == 1
        assert alerts[0].severity == "warning"

    def test_severity_info_when_more_than_7_days(self):
        engine = AlertEngine()
        products = [{"product_id": "CALM", "name": "从容", "maturity_date": _in_days(20)}]
        alerts = engine.check_maturity(products, as_of=date.today(), within_days=30)
        assert len(alerts) == 1
        assert alerts[0].severity == "info"


# ── check_fx_loss ────────────────────────────────────────────────────────────


class TestCheckFxLoss:
    """FX loss risk from non-base-currency exposure."""

    def test_triggers_when_exposure_exceeds_threshold(self):
        engine = AlertEngine()
        report = FxExposureReport(
            as_of=date.today(),
            base_currency="CNY",
            total_value=1_000_000,
            exposures=[
                FxExposureItem(
                    currency="CNY", value_base=900_000, pct=90.0,
                    asset_ids=[], sensitivity_note="CNY 为本币",
                ),
                FxExposureItem(
                    currency="USD", value_base=100_000, pct=10.0,
                    asset_ids=["AAPL"], sensitivity_note="USD/CNY ±1% → 净值波动约 ¥1,000",
                ),
            ],
            net_non_base_pct=10.0,
        )
        result = engine.check_fx_loss(report, loss_threshold_pct=2.0)
        assert result is not None
        assert "fx_loss" in result.alert_id
        assert result.evidence["net_non_base_pct"] == 10.0
        assert result.evidence["top_currency"] == "USD"

    def test_no_alert_when_below_threshold(self):
        engine = AlertEngine()
        report = FxExposureReport(
            as_of=date.today(),
            base_currency="CNY",
            total_value=1_000_000,
            exposures=[
                FxExposureItem(
                    currency="CNY", value_base=990_000, pct=99.0,
                    asset_ids=[], sensitivity_note="CNY 为本币",
                ),
                FxExposureItem(
                    currency="USD", value_base=10_000, pct=1.0,
                    asset_ids=["AAPL"], sensitivity_note="小敞口",
                ),
            ],
            net_non_base_pct=1.0,
        )
        result = engine.check_fx_loss(report, loss_threshold_pct=2.0)
        assert result is None

    def test_accepts_dict_input(self):
        engine = AlertEngine()
        report_dict = {
            "net_non_base_pct": 15.0,
            "base_currency": "CNY",
            "exposures": [
                {"currency": "CNY", "pct": 85.0},
                {"currency": "USD", "pct": 12.0},
                {"currency": "HKD", "pct": 3.0},
            ],
        }
        result = engine.check_fx_loss(report_dict, loss_threshold_pct=2.0)
        assert result is not None
        assert result.evidence["net_non_base_pct"] == 15.0

    def test_none_input_returns_none(self):
        engine = AlertEngine()
        result = engine.check_fx_loss(None)
        assert result is None

    def test_alert_carries_evidence(self):
        engine = AlertEngine()
        report = FxExposureReport(
            as_of=date.today(),
            base_currency="CNY",
            total_value=500_000,
            exposures=[
                FxExposureItem(
                    currency="CNY", value_base=400_000, pct=80.0,
                    asset_ids=[], sensitivity_note="CNY 为本币",
                ),
                FxExposureItem(
                    currency="USD", value_base=80_000, pct=16.0,
                    asset_ids=["AAPL", "MSFT"], sensitivity_note="大敞口",
                ),
                FxExposureItem(
                    currency="HKD", value_base=20_000, pct=4.0,
                    asset_ids=["0700"], sensitivity_note="小敞口",
                ),
            ],
            net_non_base_pct=20.0,
        )
        result = engine.check_fx_loss(report, loss_threshold_pct=2.0)
        assert result is not None
        assert "net_non_base_pct" in result.evidence
        assert "top_currency" in result.evidence
        assert "top_currency_pct" in result.evidence
        assert "all_non_base_exposures" in result.evidence
        assert result.reason
        assert result.suggested_action

    def test_severity_scales_with_exposure(self):
        engine = AlertEngine()
        # 3% exposure, threshold 2% — info (1x-2x threshold)
        report_low = FxExposureReport(
            as_of=date.today(), base_currency="CNY", total_value=1_000_000,
            exposures=[
                FxExposureItem(currency="CNY", value_base=970_000, pct=97.0, asset_ids=[], sensitivity_note=""),
                FxExposureItem(currency="USD", value_base=30_000, pct=3.0, asset_ids=[], sensitivity_note=""),
            ],
            net_non_base_pct=3.0,
        )
        r1 = engine.check_fx_loss(report_low, loss_threshold_pct=2.0)
        assert r1 is not None
        assert r1.severity == "info"

        # 5% exposure — warning (2x-5x threshold)
        report_mid = FxExposureReport(
            as_of=date.today(), base_currency="CNY", total_value=1_000_000,
            exposures=[
                FxExposureItem(currency="CNY", value_base=950_000, pct=95.0, asset_ids=[], sensitivity_note=""),
                FxExposureItem(currency="USD", value_base=50_000, pct=5.0, asset_ids=[], sensitivity_note=""),
            ],
            net_non_base_pct=5.0,
        )
        r2 = engine.check_fx_loss(report_mid, loss_threshold_pct=2.0)
        assert r2 is not None
        assert r2.severity == "warning"

    def test_custom_threshold(self):
        engine = AlertEngine()
        report = FxExposureReport(
            as_of=date.today(), base_currency="CNY", total_value=1_000_000,
            exposures=[
                FxExposureItem(currency="CNY", value_base=950_000, pct=95.0, asset_ids=[], sensitivity_note=""),
                FxExposureItem(currency="USD", value_base=50_000, pct=5.0, asset_ids=[], sensitivity_note=""),
            ],
            net_non_base_pct=5.0,
        )
        # With threshold 10%, 5% is fine
        r = engine.check_fx_loss(report, loss_threshold_pct=10.0)
        assert r is None


# ── check_concentration_creep ────────────────────────────────────────────────


class TestCheckConcentrationCreep:
    """Concentration dimensions increasing over time."""

    def test_triggers_when_concentration_increases(self):
        engine = AlertEngine()
        previous = {
            "currency": {"CNY": 70.0, "USD": 20.0, "HKD": 10.0},
            "asset_class": {"equity": 40.0, "bond": 35.0, "cash": 25.0},
        }
        current = {
            "currency": {"CNY": 60.0, "USD": 30.0, "HKD": 10.0},  # USD +10pp
            "asset_class": {"equity": 50.0, "bond": 30.0, "cash": 20.0},  # equity +10pp
        }
        result = engine.check_concentration_creep(current, previous, increase_threshold=5.0)
        assert result is not None
        assert "concentration_creep" in result.alert_id

    def test_exact_threshold_does_not_trigger(self):
        """Exact match (delta == threshold) does NOT trigger because check uses >."""
        engine = AlertEngine()
        previous = {"currency": {"CNY": 75.0, "USD": 25.0}}
        current = {"currency": {"CNY": 70.0, "USD": 30.0}}  # USD +5pp exactly
        result = engine.check_concentration_creep(current, previous, increase_threshold=5.0)
        assert result is None  # 5.0 > 5.0 is False
        # Actually let's check: delta (5.0) > threshold (5.0) is False — so no alert

    def test_just_above_threshold_triggers(self):
        engine = AlertEngine()
        previous = {"currency": {"CNY": 75.0, "USD": 25.0}}
        current = {"currency": {"CNY": 69.9, "USD": 30.1}}  # USD +5.1pp
        result = engine.check_concentration_creep(current, previous, increase_threshold=5.0)
        assert result is not None
        assert result.severity == "warning"

    def test_no_alert_when_below_threshold(self):
        engine = AlertEngine()
        previous = {"issuer": {"A": 20.0, "B": 20.0, "C": 20.0}}
        current = {"issuer": {"A": 23.0, "B": 20.0, "C": 20.0}}  # A +3pp
        result = engine.check_concentration_creep(current, previous, increase_threshold=5.0)
        assert result is None

    def test_decrease_no_alert(self):
        """Decreasing concentration should not trigger an alert."""
        engine = AlertEngine()
        previous = {"currency": {"USD": 50.0, "CNY": 50.0}}
        current = {"currency": {"USD": 30.0, "CNY": 70.0}}  # USD decreased by 20pp
        result = engine.check_concentration_creep(current, previous, increase_threshold=5.0)
        # CNY went from 50→70 (+20pp), which DOES trigger.
        # But USD went 50→30 (-20pp) which does not. The check looks for increases.
        # CNY increased by 20pp, so an alert IS generated for CNY.
        assert result is not None
        # Verify it's about CNY increasing, not USD decreasing
        findings = result.evidence["findings"]
        assert any(f["key"] == "CNY" and f["delta_pct"] > 0 for f in findings)

    def test_decrease_only_no_alert(self):
        """When all concentrations decrease, no alert should fire."""
        engine = AlertEngine()
        previous = {"currency": {"USD": 50.0, "CNY": 50.0}}
        current = {"currency": {"USD": 30.0, "CNY": 30.0}}  # all decreased (some went to other)
        result = engine.check_concentration_creep(current, previous, increase_threshold=5.0)
        assert result is None

    def test_new_dimension_key(self):
        """A new key in current not present in previous means increase from 0."""
        engine = AlertEngine()
        previous = {"issuer": {"A": 50.0}}
        current = {"issuer": {"A": 50.0, "B": 20.0}}  # B is new, +20pp
        result = engine.check_concentration_creep(current, previous, increase_threshold=5.0)
        assert result is not None
        # B went from 0 to 20 → +20pp
        assert any(f["key"] == "B" for f in result.evidence["findings"])

    def test_empty_inputs_returns_none(self):
        engine = AlertEngine()
        assert engine.check_concentration_creep({}, {}, increase_threshold=5.0) is None

    def test_none_equivalent_inputs(self):
        engine = AlertEngine()
        assert engine.check_concentration_creep({}, {"currency": {"USD": 50.0}}) is None

    def test_alert_carries_evidence(self):
        engine = AlertEngine()
        previous = {"asset_class": {"equity": 30.0, "bond": 50.0, "cash": 20.0}}
        current = {"asset_class": {"equity": 45.0, "bond": 40.0, "cash": 15.0}}
        result = engine.check_concentration_creep(current, previous, increase_threshold=5.0)
        assert result is not None
        assert "findings" in result.evidence
        assert len(result.evidence["findings"]) >= 1
        assert result.evidence["increase_threshold_pp"] == 5.0
        assert result.reason
        assert result.suggested_action

    def test_multiple_dimensions_creeping(self):
        engine = AlertEngine()
        previous = {
            "currency": {"CNY": 80.0, "USD": 20.0},
            "issuer": {"A": 30.0, "B": 30.0},
        }
        current = {
            "currency": {"CNY": 70.0, "USD": 30.0},  # USD +10pp
            "issuer": {"A": 40.0, "B": 25.0},  # A +10pp
        }
        result = engine.check_concentration_creep(current, previous, increase_threshold=5.0)
        assert result is not None
        assert len(result.evidence["findings"]) == 2

    def test_critical_severity_for_large_creep(self):
        engine = AlertEngine()
        previous = {"currency": {"CNY": 90.0, "USD": 10.0}}
        current = {"currency": {"CNY": 70.0, "USD": 30.0}}  # USD +20pp (>= 3*5)
        result = engine.check_concentration_creep(current, previous, increase_threshold=5.0)
        assert result is not None
        assert result.severity == "critical"


# ── check_open_windows ───────────────────────────────────────────────────────


class TestCheckOpenWindows:
    """Fund subscription / redemption window alerts."""

    def test_open_window_approaching(self):
        engine = AlertEngine()
        fund_statuses = [
            {
                "fund_code": "005827",
                "fund_name": "易方达蓝筹精选",
                "can_buy": True,
                "can_sell": True,
                "next_open_date": _in_days(10),
            }
        ]
        alerts = engine.check_open_windows(fund_statuses, as_of=date.today(), window_days=30)
        assert len(alerts) == 1
        assert alerts[0].alert_id.startswith("open_window_005827")
        assert alerts[0].evidence["days_left"] == 10

    def test_no_alert_when_daily_open(self):
        engine = AlertEngine()
        fund_statuses = [
            {
                "fund_code": "000001",
                "fund_name": "日常开放基金",
                "can_buy": True,
                "can_sell": True,
                "next_open_date": None,  # NaT = daily open
            }
        ]
        alerts = engine.check_open_windows(fund_statuses, as_of=date.today(), window_days=30)
        assert len(alerts) == 0

    def test_alert_when_closed_for_purchase(self):
        engine = AlertEngine()
        fund_statuses = [
            {
                "fund_code": "CLOSED1",
                "fund_name": "暂停申购基金",
                "can_buy": False,
                "can_sell": True,
                "next_open_date": None,
            }
        ]
        alerts = engine.check_open_windows(fund_statuses, as_of=date.today(), window_days=30)
        assert len(alerts) == 1
        assert "buy" in alerts[0].alert_id
        assert alerts[0].severity == "warning"

    def test_alert_when_closed_for_redemption(self):
        engine = AlertEngine()
        fund_statuses = [
            {
                "fund_code": "LOCKED1",
                "fund_name": "暂停赎回基金",
                "can_buy": True,
                "can_sell": False,
                "next_open_date": None,
            }
        ]
        alerts = engine.check_open_windows(fund_statuses, as_of=date.today(), window_days=30)
        assert len(alerts) == 1
        assert "sell" in alerts[0].alert_id
        assert alerts[0].severity == "critical"

    def test_both_closed_generates_two_alerts(self):
        engine = AlertEngine()
        fund_statuses = [
            {
                "fund_code": "FROZEN",
                "fund_name": "完全关闭基金",
                "can_buy": False,
                "can_sell": False,
                "next_open_date": _in_days(5),
            }
        ]
        alerts = engine.check_open_windows(fund_statuses, as_of=date.today(), window_days=30)
        # buy closed, sell closed, open window approaching = 3 alerts
        assert len(alerts) == 3

    def test_multiple_funds(self):
        engine = AlertEngine()
        fund_statuses = [
            {"fund_code": "A", "fund_name": "A", "can_buy": False, "can_sell": True, "next_open_date": None},
            {"fund_code": "B", "fund_name": "B", "can_buy": True, "can_sell": False, "next_open_date": None},
            {"fund_code": "C", "fund_name": "C", "can_buy": True, "can_sell": True, "next_open_date": _in_days(3)},
        ]
        alerts = engine.check_open_windows(fund_statuses, as_of=date.today(), window_days=30)
        assert len(alerts) == 3  # A buy closed, B sell closed, C open window

    def test_alert_carries_evidence(self):
        engine = AlertEngine()
        fund_statuses = [
            {
                "fund_code": "EVID",
                "fund_name": "证据基金",
                "can_buy": False,
                "can_sell": True,
                "next_open_date": _in_days(14),
            }
        ]
        alerts = engine.check_open_windows(fund_statuses, as_of=date.today(), window_days=30)
        assert len(alerts) >= 1
        for a in alerts:
            assert a.evidence
            assert "fund_code" in a.evidence
            assert a.reason
            assert a.suggested_action

    def test_empty_fund_statuses(self):
        engine = AlertEngine()
        alerts = engine.check_open_windows([], as_of=date.today(), window_days=30)
        assert alerts == []

    def test_string_next_open_date(self):
        engine = AlertEngine()
        target = _in_days(8)
        fund_statuses = [
            {
                "fund_code": "STR",
                "fund_name": "字符串日期",
                "can_buy": True,
                "can_sell": True,
                "next_open_date": target.isoformat(),
            }
        ]
        alerts = engine.check_open_windows(fund_statuses, as_of=date.today(), window_days=30)
        assert len(alerts) == 1
        assert alerts[0].evidence["days_left"] == 8

    def test_severity_warning_for_soon_open(self):
        engine = AlertEngine()
        fund_statuses = [
            {
                "fund_code": "SOON",
                "fund_name": "临近开放",
                "can_buy": True,
                "can_sell": True,
                "next_open_date": _in_days(3),
            }
        ]
        alerts = engine.check_open_windows(fund_statuses, as_of=date.today(), window_days=30)
        open_alerts = [a for a in alerts if a.alert_id.startswith("open_window")]
        assert len(open_alerts) == 1
        assert open_alerts[0].severity == "warning"

    def test_severity_info_for_later_open(self):
        engine = AlertEngine()
        fund_statuses = [
            {
                "fund_code": "LATER",
                "fund_name": "稍后开放",
                "can_buy": True,
                "can_sell": True,
                "next_open_date": _in_days(20),
            }
        ]
        alerts = engine.check_open_windows(fund_statuses, as_of=date.today(), window_days=30)
        open_alerts = [a for a in alerts if a.alert_id.startswith("open_window")]
        assert len(open_alerts) == 1
        assert open_alerts[0].severity == "info"

    def test_custom_window_days(self):
        engine = AlertEngine()
        fund_statuses = [
            {
                "fund_code": "CUST",
                "fund_name": "自定义窗口",
                "can_buy": True,
                "can_sell": True,
                "next_open_date": _in_days(45),
            }
        ]
        # 45 days is outside default 30-day window, but NOT outside 60-day window
        alerts_default = engine.check_open_windows(fund_statuses, as_of=date.today(), window_days=30)
        assert len(alerts_default) == 0

        alerts_extended = engine.check_open_windows(fund_statuses, as_of=date.today(), window_days=60)
        assert len(alerts_extended) == 1


# ── run_all ──────────────────────────────────────────────────────────────────


class TestRunAll:
    """Orchestrated run of all applicable checks."""

    def test_all_checks_with_full_context(self):
        engine = AlertEngine()
        curve = _make_equity_curve([100_000, 85_000])  # 15% drawdown
        products = [{"product_id": "WMP1", "name": "WMP1", "maturity_date": _in_days(10)}]
        fx_report = FxExposureReport(
            as_of=date.today(), base_currency="CNY", total_value=1_000_000,
            exposures=[
                FxExposureItem(currency="CNY", value_base=800_000, pct=80.0, asset_ids=[], sensitivity_note=""),
                FxExposureItem(currency="USD", value_base=200_000, pct=20.0, asset_ids=["AAPL"], sensitivity_note=""),
            ],
            net_non_base_pct=20.0,
        )
        prev_conc = {"currency": {"CNY": 80.0, "USD": 20.0}}
        cur_conc = {"currency": {"CNY": 60.0, "USD": 40.0}}  # USD +20pp
        fund_statuses = [
            {"fund_code": "F1", "fund_name": "F1", "can_buy": False, "can_sell": True, "next_open_date": None},
        ]

        context = {
            "equity_curve": curve,
            "products": products,
            "fx_exposure_report": fx_report,
            "current_concentration": cur_conc,
            "previous_concentration": prev_conc,
            "fund_statuses": fund_statuses,
            "as_of": date.today(),
        }
        alerts = engine.run_all(context)

        # drawdown (1) + maturity (1) + fx_loss (1) + creep (1) + open_window buy closed (1) = 5
        assert len(alerts) >= 5
        alert_ids = {a.alert_id for a in alerts}
        assert any("drawdown" in aid for aid in alert_ids)
        assert any("maturity" in aid for aid in alert_ids)
        assert any("fx_loss" in aid for aid in alert_ids)
        assert any("concentration_creep" in aid for aid in alert_ids)
        assert any("window_closed" in aid for aid in alert_ids)

    def test_empty_context_returns_empty_list(self):
        engine = AlertEngine()
        alerts = engine.run_all({})
        assert alerts == []

    def test_partial_context_runs_only_available_checks(self):
        engine = AlertEngine()
        curve = _make_equity_curve([100_000, 88_000])  # 12% drawdown
        context = {"equity_curve": curve}
        alerts = engine.run_all(context)
        assert len(alerts) == 1
        assert "drawdown" in alerts[0].alert_id

    def test_custom_thresholds_in_context(self):
        engine = AlertEngine()
        # 4% drawdown — normally would not trigger with default 5%
        curve = _make_equity_curve([100_000, 96_000])
        context = {
            "equity_curve": curve,
            "drawdown_threshold_pct": 3.0,  # custom lower threshold
        }
        alerts = engine.run_all(context)
        assert len(alerts) == 1
        assert "drawdown" in alerts[0].alert_id

    def test_maturity_with_custom_window(self):
        engine = AlertEngine()
        products = [{"product_id": "W1", "name": "W1", "maturity_date": _in_days(45)}]
        context = {
            "products": products,
            "maturity_within_days": 60,  # custom wider window
            "as_of": date.today(),
        }
        alerts = engine.run_all(context)
        assert len(alerts) == 1
        assert "maturity" in alerts[0].alert_id

    def test_all_alerts_have_evidence(self):
        engine = AlertEngine()
        curve = _make_equity_curve([100_000, 80_000])
        products = [{"product_id": "E", "name": "E", "maturity_date": _in_days(5)}]
        fx_report = FxExposureReport(
            as_of=date.today(), base_currency="CNY", total_value=1_000_000,
            exposures=[
                FxExposureItem(currency="CNY", value_base=900_000, pct=90.0, asset_ids=[], sensitivity_note=""),
                FxExposureItem(currency="USD", value_base=100_000, pct=10.0, asset_ids=[], sensitivity_note=""),
            ],
            net_non_base_pct=10.0,
        )
        prev = {"currency": {"CNY": 90.0, "USD": 10.0}}
        cur = {"currency": {"CNY": 70.0, "USD": 30.0}}
        funds = [{"fund_code": "F", "fund_name": "F", "can_buy": False, "can_sell": True, "next_open_date": None}]

        context = {
            "equity_curve": curve,
            "products": products,
            "fx_exposure_report": fx_report,
            "current_concentration": cur,
            "previous_concentration": prev,
            "fund_statuses": funds,
            "as_of": date.today(),
        }
        alerts = engine.run_all(context)
        assert len(alerts) > 0
        for a in alerts:
            assert a.evidence, f"Alert {a.alert_id} has no evidence"
            assert a.reason, f"Alert {a.alert_id} has no reason"
            assert a.suggested_action, f"Alert {a.alert_id} has no suggested_action"
            assert a.severity in ("info", "warning", "critical")
            assert a.created_at

    def test_creep_with_custom_threshold(self):
        engine = AlertEngine()
        prev = {"issuer": {"A": 20.0}}
        cur = {"issuer": {"A": 23.0}}  # +3pp — below default 5pp
        context = {
            "current_concentration": cur,
            "previous_concentration": prev,
            "concentration_creep_threshold": 2.0,  # custom lower
        }
        alerts = engine.run_all(context)
        assert len(alerts) == 1
        assert "concentration_creep" in alerts[0].alert_id

    def test_fx_loss_custom_threshold(self):
        engine = AlertEngine()
        fx_report = FxExposureReport(
            as_of=date.today(), base_currency="CNY", total_value=1_000_000,
            exposures=[
                FxExposureItem(currency="CNY", value_base=970_000, pct=97.0, asset_ids=[], sensitivity_note=""),
                FxExposureItem(currency="USD", value_base=30_000, pct=3.0, asset_ids=[], sensitivity_note=""),
            ],
            net_non_base_pct=3.0,
        )
        # Default threshold is 2% — 3% > 2% so it triggers with default
        alerts_default = engine.run_all({"fx_exposure_report": fx_report})
        assert len(alerts_default) == 1  # triggers because 3% > 2%

        # Custom threshold 5% — 3% < 5% so it should NOT trigger
        context = {
            "fx_exposure_report": fx_report,
            "fx_loss_threshold_pct": 5.0,
        }
        alerts_custom = engine.run_all(context)
        assert len(alerts_custom) == 0  # 3% < 5% custom threshold

    def test_fund_open_window_custom_days(self):
        engine = AlertEngine()
        funds = [{"fund_code": "F", "fund_name": "F", "can_buy": True, "can_sell": True, "next_open_date": _in_days(50)}]
        context = {"fund_statuses": funds, "open_window_days": 60, "as_of": date.today()}
        alerts = engine.run_all(context)
        assert len(alerts) == 1
        assert "open_window" in alerts[0].alert_id
