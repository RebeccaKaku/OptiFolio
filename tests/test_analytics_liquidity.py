"""Tests for the LiquidityAnalyzer."""

from datetime import date, datetime, timedelta
from typing import Dict

import pytest

from src.domain import CashHolding, PositionValue, ProductDefinition
from src.analytics.liquidity import (
    BUCKET_ORDER,
    LiquidityAnalyzer,
    LiquidityBucket,
    LiquidityReport,
)


# ── helpers ─────────────────────────────────────────────────────────────


def _pv(asset_id: str, value_base: float, currency: str = "CNY") -> PositionValue:
    """Create a minimal PositionValue for testing."""
    return PositionValue(
        asset_id=asset_id,
        quantity=1.0,
        price=value_base,
        currency=currency,
        fx_rate=1.0,
        value_base=value_base,
    )


def _product(
    product_id: str,
    product_type: str,
    name: str = "",
    liquidity_type: str = None,
    metadata: dict = None,
) -> ProductDefinition:
    """Create a minimal ProductDefinition for testing."""
    return ProductDefinition(
        product_id=product_id,
        name=name or product_id,
        product_type=product_type,
        liquidity_type=liquidity_type,
        metadata=metadata or {},
    )


def _cash(currency: str, value_base: float) -> CashHolding:
    """Create a minimal CashHolding for testing."""
    return CashHolding(
        currency=currency,
        amount=value_base,
        fx_rate=1.0,
        value_base=value_base,
    )


# ── report structure ────────────────────────────────────────────────────


def test_liquidity_bucket_to_dict():
    bucket = LiquidityBucket(name="T+0", value=10000.0, pct=20.0, asset_ids=["CASH"])
    d = bucket.to_dict()
    assert d["name"] == "T+0"
    assert d["value"] == 10000.0
    assert d["pct"] == 20.0
    assert d["asset_ids"] == ["CASH"]


def test_liquidity_report_to_dict():
    today = date.today()
    bucket = LiquidityBucket(name="T+0", value=10000.0, pct=50.0, asset_ids=["CASH"])
    report = LiquidityReport(
        as_of=today,
        total_value=20000.0,
        buckets=[bucket],
        available_7d_pct=50.0,
        locked_pct=0.0,
    )
    d = report.to_dict()
    assert d["as_of"] == today.isoformat()
    assert d["total_value"] == 20000.0
    assert len(d["buckets"]) == 1
    assert d["available_7d_pct"] == 50.0
    assert d["locked_pct"] == 0.0


def test_liquidity_bucket_is_frozen():
    bucket = LiquidityBucket(name="T+0", value=1.0, pct=1.0, asset_ids=[])
    with pytest.raises(Exception):
        bucket.name = "X"  # type: ignore


def test_liquidity_report_is_frozen():
    report = LiquidityReport(
        as_of=date.today(),
        total_value=100.0,
        buckets=[],
        available_7d_pct=0.0,
        locked_pct=0.0,
    )
    with pytest.raises(Exception):
        report.total_value = 999.0  # type: ignore


# ── empty input ─────────────────────────────────────────────────────────


def test_empty_positions_returns_zero_total():
    analyzer = LiquidityAnalyzer()
    report = analyzer.analyze(
        positions={},
        product_registry={},
        as_of=date.today(), total_value=0.0,
        cash_breakdown={},
    )
    assert report.total_value == 0.0
    for b in report.buckets:
        assert b.value == 0.0
        assert b.pct == 0.0


# ── cash classification ─────────────────────────────────────────────────


def test_cash_is_t0():
    analyzer = LiquidityAnalyzer()
    cash_bd = {"CNY": _cash("CNY", 5000.0)}
    report = analyzer.analyze(
        positions={},
        product_registry={},
        as_of=date.today(), total_value=5000.0,
        cash_breakdown=cash_bd,
    )
    t0 = _find_bucket(report, "T+0")
    assert t0.value == 5000.0
    assert t0.pct == 100.0
    assert "CASH" in t0.asset_ids


# ── stock classification (symbol-pattern heuristics) ────────────────────


def test_us_stock_is_t1():
    analyzer = LiquidityAnalyzer()
    positions = {"AAPL": _pv("AAPL", 30000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry={},
        as_of=date.today(), total_value=30000.0,
    )
    t1 = _find_bucket(report, "T+1")
    assert t1.value == 30000.0
    assert "AAPL" in t1.asset_ids


def test_a_share_numeric_is_t1():
    analyzer = LiquidityAnalyzer()
    positions = {"600519": _pv("600519", 20000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry={},
        as_of=date.today(), total_value=20000.0,
    )
    t1 = _find_bucket(report, "T+1")
    assert t1.value == 20000.0
    assert "600519" in t1.asset_ids


def test_a_share_sh_prefix_is_t1():
    analyzer = LiquidityAnalyzer()
    positions = {"sh600519": _pv("sh600519", 15000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry={},
        as_of=date.today(), total_value=15000.0,
    )
    t1 = _find_bucket(report, "T+1")
    assert t1.value == 15000.0


def test_a_share_sz_prefix_is_t1():
    analyzer = LiquidityAnalyzer()
    positions = {"sz000001": _pv("sz000001", 10000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry={},
        as_of=date.today(), total_value=10000.0,
    )
    t1 = _find_bucket(report, "T+1")
    assert t1.value == 10000.0


# ── money market fund ───────────────────────────────────────────────────


def test_money_fund_is_t1():
    analyzer = LiquidityAnalyzer()
    registry = {"MF001": _product("MF001", "money_fund", "货币基金A")}
    positions = {"MF001": _pv("MF001", 8000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=8000.0,
    )
    t1 = _find_bucket(report, "T+1")
    assert t1.value == 8000.0


def test_money_fund_by_name_contains_huobi():
    analyzer = LiquidityAnalyzer()
    registry = {"MF002": _product("MF002", "unknown", "某某货币基金")}
    positions = {"MF002": _pv("MF002", 6000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=6000.0,
    )
    t1 = _find_bucket(report, "T+1")
    assert t1.value == 6000.0


# ── open-end funds ──────────────────────────────────────────────────────


@pytest.mark.parametrize("ptype", [
    "mixed_fund", "bond_fund", "equity_fund", "stock_fund", "index_fund", "etf_fund",
])
def test_open_end_fund_is_t2_t4(ptype):
    analyzer = LiquidityAnalyzer()
    registry = {"F001": _product("F001", ptype, "某基金")}
    positions = {"F001": _pv("F001", 12000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=12000.0,
    )
    bucket = _find_bucket(report, "T+2~T+4")
    assert bucket.value == 12000.0


# ── bank WMP ────────────────────────────────────────────────────────────


def test_bank_wmp_default_1_month():
    analyzer = LiquidityAnalyzer()
    registry = {"WMP001": _product("WMP001", "bank_wmp", "银行理财A")}
    positions = {"WMP001": _pv("WMP001", 25000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=25000.0,
    )
    bucket = _find_bucket(report, "1个月内")
    assert bucket.value == 25000.0


def test_bank_wmp_lockup_15_days():
    """Lockup ending in 15 days → 1个月内."""
    future = (date.today() + timedelta(days=15)).isoformat()
    analyzer = LiquidityAnalyzer()
    registry = {
        "WMP002": _product("WMP002", "bank_wmp", "理财B", metadata={
            "lockup_end_date": future,
        }),
    }
    positions = {"WMP002": _pv("WMP002", 30000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=30000.0,
    )
    bucket = _find_bucket(report, "1个月内")
    assert bucket.value == 30000.0


def test_bank_wmp_lockup_60_days():
    """Lockup ending in 60 days → 3个月内."""
    future = (date.today() + timedelta(days=60)).isoformat()
    analyzer = LiquidityAnalyzer()
    registry = {
        "WMP003": _product("WMP003", "bank_wmp", "理财C", metadata={
            "lockup_end_date": future,
        }),
    }
    positions = {"WMP003": _pv("WMP003", 40000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=40000.0,
    )
    bucket = _find_bucket(report, "3个月内")
    assert bucket.value == 40000.0


def test_bank_wmp_lockup_200_days():
    """Lockup ending in 200 days → 1年内."""
    future = (date.today() + timedelta(days=200)).isoformat()
    analyzer = LiquidityAnalyzer()
    registry = {
        "WMP004": _product("WMP004", "bank_wmp", "理财D", metadata={
            "lockup_end_date": future,
        }),
    }
    positions = {"WMP004": _pv("WMP004", 50000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=50000.0,
    )
    bucket = _find_bucket(report, "1年内")
    assert bucket.value == 50000.0


def test_bank_wmp_lockup_500_days():
    """Lockup ending in 500 days → 锁仓."""
    future = (date.today() + timedelta(days=500)).isoformat()
    analyzer = LiquidityAnalyzer()
    registry = {
        "WMP005": _product("WMP005", "bank_wmp", "理财E", metadata={
            "lockup_end_date": future,
        }),
    }
    positions = {"WMP005": _pv("WMP005", 60000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=60000.0,
    )
    bucket = _find_bucket(report, "锁仓")
    assert bucket.value == 60000.0


def test_bank_wmp_lockup_past_is_t0():
    """Lockup already expired → T+0."""
    past = (date.today() - timedelta(days=10)).isoformat()
    analyzer = LiquidityAnalyzer()
    registry = {
        "WMP006": _product("WMP006", "bank_wmp", "理财F", metadata={
            "lockup_end_date": past,
        }),
    }
    positions = {"WMP006": _pv("WMP006", 70000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=70000.0,
    )
    t0 = _find_bucket(report, "T+0")
    # value should include this WMP (70000)
    assert t0.value == 70000.0


def test_bank_wmp_liquidity_type_t0():
    analyzer = LiquidityAnalyzer()
    registry = {
        "WMP007": _product("WMP007", "bank_wmp", "理财G", liquidity_type="T+0"),
    }
    positions = {"WMP007": _pv("WMP007", 8000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=8000.0,
    )
    t0 = _find_bucket(report, "T+0")
    assert t0.value == 8000.0


# ── unknown / default ───────────────────────────────────────────────────


def test_unknown_symbol_is_unknown():
    analyzer = LiquidityAnalyzer()
    positions = {"X_UNKNOWN123": _pv("X_UNKNOWN123", 5000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry={},
        as_of=date.today(), total_value=5000.0,
    )
    bucket = _find_bucket(report, "未知")
    assert bucket.value == 5000.0


# ── portfolio integration test ──────────────────────────────────────────


def test_full_portfolio_buckets_sum_to_100():
    """End-to-end test with stocks, money fund, bond fund, bank WMP, and cash."""
    analyzer = LiquidityAnalyzer()

    positions = {
        "AAPL": _pv("AAPL", 35000.0, "USD"),
        "600519": _pv("600519", 25000.0, "CNY"),
    }
    registry = {
        "MF001": _product("MF001", "money_fund", "货币基金"),
        "BF001": _product("BF001", "bond_fund", "纯债基金"),
        "WMP001": _product("WMP001", "bank_wmp", "理财A"),
    }
    # Also add the fund/WMP positions
    positions["MF001"] = _pv("MF001", 15000.0)
    positions["BF001"] = _pv("BF001", 10000.0)
    positions["WMP001"] = _pv("WMP001", 10000.0)

    cash_bd = {"CNY": _cash("CNY", 5000.0)}

    total_value = sum(p.value_base for p in positions.values()) + sum(
        c.value_base for c in cash_bd.values()
    )  # 100000

    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=total_value,
        cash_breakdown=cash_bd,
    )

    assert report.total_value == 100000.0

    # Check specific buckets
    t0 = _find_bucket(report, "T+0")
    assert t0.value == 5000.0  # cash only

    t1 = _find_bucket(report, "T+1")
    assert t1.value == 75000.0  # AAPL + 600519 + MF001 (money fund)

    t2t4 = _find_bucket(report, "T+2~T+4")
    assert t2t4.value == 10000.0  # BF001 (bond fund)

    m1 = _find_bucket(report, "1个月内")
    assert m1.value == 10000.0  # WMP001

    # All pct should sum close to 100
    total_pct = sum(b.pct for b in report.buckets)
    assert abs(total_pct - 100.0) < 0.1, f"Total pct = {total_pct}, expected ~100"

    # available_7d_pct = T+0 + T+1 + T+2~T+4 = 5% + 75% + 10% = 90%
    assert abs(report.available_7d_pct - 90.0) < 0.1

    # locked_pct = 锁仓
    assert report.locked_pct == 0.0


def test_all_buckets_present_in_order():
    """Every bucket in BUCKET_ORDER appears in the report, in order."""
    analyzer = LiquidityAnalyzer()
    report = analyzer.analyze(
        positions={},
        product_registry={},
        as_of=date.today(), total_value=0.0,
    )
    assert len(report.buckets) == len(BUCKET_ORDER)
    for i, b in enumerate(report.buckets):
        assert b.name == BUCKET_ORDER[i], f"Bucket {i}: expected {BUCKET_ORDER[i]}, got {b.name}"


# ── deposit classification ─────────────────────────────────────────────


def test_demand_deposit_is_t0():
    """Demand deposit (no maturity/term metadata) → T+0."""
    analyzer = LiquidityAnalyzer()
    registry = {"DEP001": _product("DEP001", "deposit", "活期存款")}
    positions = {"DEP001": _pv("DEP001", 3000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=3000.0,
    )
    t0 = _find_bucket(report, "T+0")
    assert t0.value == 3000.0


def test_time_deposit_maturity_60_days():
    """Time deposit with maturity_date 60 days out → 3个月内."""
    future = (date.today() + timedelta(days=60)).isoformat()
    analyzer = LiquidityAnalyzer()
    registry = {
        "TD001": _product("TD001", "deposit", "定期存款60天", metadata={
            "maturity_date": future,
        }),
    }
    positions = {"TD001": _pv("TD001", 50000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=50000.0,
    )
    bucket = _find_bucket(report, "3个月内")
    assert bucket.value == 50000.0
    assert "TD001" in bucket.asset_ids


def test_time_deposit_term_365_days():
    """Time deposit with term=365 → 1年内."""
    analyzer = LiquidityAnalyzer()
    registry = {
        "TD002": _product("TD002", "deposit", "定期存款365天", metadata={
            "term": 365,
        }),
    }
    positions = {"TD002": _pv("TD002", 80000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=80000.0,
    )
    bucket = _find_bucket(report, "1年内")
    assert bucket.value == 80000.0
    assert "TD002" in bucket.asset_ids


def test_time_deposit_lockup_500_days():
    """Time deposit with lockup_end_date 500 days out → 锁仓."""
    future = (date.today() + timedelta(days=500)).isoformat()
    analyzer = LiquidityAnalyzer()
    registry = {
        "TD003": _product("TD003", "deposit", "定期存款500天", metadata={
            "lockup_end_date": future,
        }),
    }
    positions = {"TD003": _pv("TD003", 100000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=100000.0,
    )
    bucket = _find_bucket(report, "锁仓")
    assert bucket.value == 100000.0
    assert "TD003" in bucket.asset_ids


def test_time_deposit_past_maturity_is_t0():
    """Time deposit with already-expired maturity → T+0."""
    past = (date.today() - timedelta(days=10)).isoformat()
    analyzer = LiquidityAnalyzer()
    registry = {
        "TD004": _product("TD004", "deposit", "已到期定期", metadata={
            "maturity_date": past,
        }),
    }
    positions = {"TD004": _pv("TD004", 20000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=20000.0,
    )
    t0 = _find_bucket(report, "T+0")
    assert t0.value == 20000.0


def test_deposit_unknown_type_warns():
    """Deposit with no maturity/term metadata warns and defaults to Unknown."""
    analyzer = LiquidityAnalyzer()
    registry = {"DEP_UNK": _product("DEP_UNK", "deposit", "未知存款类型")}
    positions = {"DEP_UNK": _pv("DEP_UNK", 5000.0)}
    report = analyzer.analyze(
        positions=positions,
        product_registry=registry,
        as_of=date.today(), total_value=5000.0,
    )
    unk = _find_bucket(report, "未知")
    assert unk.value == 5000.0
    assert hasattr(analyzer, "_warnings")
    assert any("DEP_UNK" in w for w in analyzer._warnings)


# ── helpers ─────────────────────────────────────────────────────────────


def _find_bucket(report: LiquidityReport, name: str) -> LiquidityBucket:
    """Find a bucket by name, raising if not found."""
    for b in report.buckets:
        if b.name == name:
            return b
    raise KeyError(f"Bucket '{name}' not found in report")
