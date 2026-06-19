"""Tests for the PermanentLossAnalyzer."""

from datetime import date
import pytest
from src.domain import PositionValue, ProductDefinition
from src.analytics.liquidity import LiquidityAnalyzer
from src.analytics.permanent_loss import PermanentLossAnalyzer


def test_permanent_loss_basic_assets():
    as_of = date(2026, 6, 1)
    analyzer = PermanentLossAnalyzer()

    positions = {
        "CASH_CNY": PositionValue("CASH_CNY", 1.0, 10000.0, "CNY", 1.0, 10000.0),
        "600519": PositionValue("600519", 10.0, 1500.0, "CNY", 1.0, 15000.0),
        "UST_10Y": PositionValue("UST_10Y", 100.0, 105.0, "USD", 7.2, 75600.0),
        "UNKNOWN_ASSET": PositionValue("UNKNOWN_ASSET", 1.0, 5000.0, "CNY", 1.0, 5000.0),
    }

    registry = {
        "CASH_CNY": ProductDefinition("CASH_CNY", "现金", "cash"),
        "600519": ProductDefinition("600519", "贵州茅台", "equity"),
        "UST_10Y": ProductDefinition("UST_10Y", "US Treasury 10Y", "bond"),
    }

    # Pre-calculate liquidity for the analyzer
    liq_analyzer = LiquidityAnalyzer()
    liq_report = liq_analyzer.analyze(positions, registry, 105600.0, as_of)

    report = analyzer.analyze(positions, registry, liq_report, as_of)

    assert report.total_value == 105600.0

    # Check CASH_CNY (Low risk across the board)
    cash_risk = next(p for p in report.positions if p.asset_id == "CASH_CNY")
    assert cash_risk.market_volatility.level == "low"
    assert cash_risk.liquidity_restriction.level == "low"
    assert cash_risk.permanent_loss.level == "low"
    assert cash_risk.data_unknown.level == "low"

    # Check 600519 (High market volatility)
    equity_risk = next(p for p in report.positions if p.asset_id == "600519")
    assert equity_risk.market_volatility.level == "high"
    assert equity_risk.permanent_loss.level == "medium"

    # Check UST_10Y (Medium volatility, low permanent loss - sovereign credit)
    bond_risk = next(p for p in report.positions if p.asset_id == "UST_10Y")
    assert bond_risk.market_volatility.level == "medium"
    assert bond_risk.permanent_loss.level == "low"

    # Check UNKNOWN_ASSET (Unknown data)
    unk_risk = next(p for p in report.positions if p.asset_id == "UNKNOWN_ASSET")
    assert unk_risk.data_unknown.level == "unknown"
    assert unk_risk.liquidity_restriction.level == "unknown"
    assert unk_risk.permanent_loss.level == "unknown"

    # Check unknown_value
    # UNKNOWN_ASSET (5000.0) has unknown in data_unknown, liquidity_restriction, permanent_loss, market_volatility
    # Others should NOT be unknown if possible.
    # If 80600.0 is shown, it means other assets are also considered unknown.
    # CASH_CNY (10000.0), 600519 (15000.0), UST_10Y (75600.0), UNKNOWN_ASSET (5000.0)
    # Total = 105600.0
    # 80600 = 75600 + 5000.
    # It seems UST_10Y or 600519 is unknown in some dimension.
    # Let's debug by printing or inspecting.
    # From the failure, UNKNOWN_ASSET is 5000.
    # Wait, UST_10Y is 75600.0. 75600 + 5000 = 80600.
    # So UST_10Y has an 'unknown' level in some dimension.
    assert report.unknown_value == 5000.0


def test_permanent_loss_high_risk_product():
    as_of = date(2026, 6, 1)
    analyzer = PermanentLossAnalyzer()

    positions = {
        "RISKY_WMP": PositionValue("RISKY_WMP", 1.0, 100000.0, "CNY", 1.0, 100000.0),
    }

    registry = {
        "RISKY_WMP": ProductDefinition(
            "RISKY_WMP", "非保本理财", "bank_wmp",
            metadata={"principal_guaranteed": False}
        ),
    }

    report = analyzer.analyze(positions, registry, None, as_of)
    risky_risk = report.positions[0]

    assert risky_risk.permanent_loss.level == "high"
    assert risky_risk.permanent_loss.rule_id == "pl_no_guarantee"
    assert "永久损失风险高" in report.warnings[0]


def test_permanent_loss_summary_calculation():
    as_of = date(2026, 6, 1)
    analyzer = PermanentLossAnalyzer()

    positions = {
        "A": PositionValue("A", 1.0, 60.0, "CNY", 1.0, 60.0),
        "B": PositionValue("B", 1.0, 40.0, "CNY", 1.0, 40.0),
    }

    # A is low risk, B is high volatility
    registry = {
        "A": ProductDefinition("A", "A", "cash"),
        "B": ProductDefinition("B", "B", "equity"),
    }

    report = analyzer.analyze(positions, registry, None, as_of)

    vol_summary = report.summary["market_volatility"]
    low_vol = next(s for s in vol_summary if s.level == "low")
    high_vol = next(s for s in vol_summary if s.level == "high")

    assert low_vol.value == 60.0
    assert low_vol.pct == 0.6
    assert high_vol.value == 40.0
    assert high_vol.pct == 0.4
