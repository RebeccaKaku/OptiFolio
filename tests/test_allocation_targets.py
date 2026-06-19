import pytest
from decimal import Decimal
from src.analytics.allocation_targets import (
    TargetRange,
    TargetSet,
    calculate_allocation_gaps,
    AllocationGapReport
)

def test_target_range_validation():
    # Valid range
    TargetRange("asset_class", "equity", Decimal("0.3"), Decimal("0.5"))

    # Invalid ranges
    with pytest.raises(ValueError, match="Invalid range"):
        TargetRange("asset_class", "equity", Decimal("-0.1"), Decimal("0.5"))
    with pytest.raises(ValueError, match="Invalid range"):
        TargetRange("asset_class", "equity", Decimal("0.6"), Decimal("0.5"))
    with pytest.raises(ValueError, match="Invalid range"):
        TargetRange("asset_class", "equity", Decimal("0.3"), Decimal("1.1"))

def test_target_set_validation():
    ranges = [
        TargetRange("asset_class", "equity", Decimal("0.3"), Decimal("0.5")),
        TargetRange("asset_class", "bond", Decimal("0.4"), Decimal("0.6"))
    ]
    ts = TargetSet("total", Decimal("1000000"), "CNY", True, True, ranges)
    ts.validate()

    # Mixed dimensions
    mixed_ranges = [
        TargetRange("asset_class", "equity", Decimal("0.3"), Decimal("0.5")),
        TargetRange("currency", "USD", Decimal("0.4"), Decimal("0.6"))
    ]
    ts_mixed = TargetSet("total", Decimal("1000000"), "CNY", False, False, mixed_ranges)
    with pytest.raises(ValueError, match="single dimension"):
        ts_mixed.validate()

    # Sum min > 1
    too_high_min = [
        TargetRange("asset_class", "equity", Decimal("0.6"), Decimal("0.7")),
        TargetRange("asset_class", "bond", Decimal("0.5"), Decimal("0.6"))
    ]
    ts_high_min = TargetSet("total", Decimal("1000000"), "CNY", True, True, too_high_min)
    with pytest.raises(ValueError, match="Sum of min_weights"):
        ts_high_min.validate()

    # Sum max < 1
    too_low_max = [
        TargetRange("asset_class", "equity", Decimal("0.1"), Decimal("0.2")),
        TargetRange("asset_class", "bond", Decimal("0.2"), Decimal("0.3"))
    ]
    ts_low_max = TargetSet("total", Decimal("1000000"), "CNY", True, True, too_low_max)
    with pytest.raises(ValueError, match="Sum of max_weights"):
        ts_low_max.validate()

def test_calculate_gaps_basic():
    ranges = [
        TargetRange("asset_class", "equity", Decimal("0.3"), Decimal("0.5")),
        TargetRange("asset_class", "bond", Decimal("0.4"), Decimal("0.6")),
        TargetRange("asset_class", "cash", Decimal("0.0"), Decimal("0.1"))
    ]
    ts = TargetSet("total", Decimal("1000000"), "CNY", True, True, ranges)

    current = {
        "equity": Decimal("0.2"),
        "bond": Decimal("0.5"),
        "cash": Decimal("0.3")
    }

    report = calculate_allocation_gaps(ts, current)

    # equity: 0.2 < 0.3 -> below
    equity_item = next(i for i in report.items if i.bucket == "equity")
    assert equity_item.status == "below"
    assert equity_item.gap_to_min == Decimal("0.1")
    assert equity_item.amount_range == (Decimal("300000"), Decimal("500000"))

    # bond: 0.5 is within [0.4, 0.6] -> within
    bond_item = next(i for i in report.items if i.bucket == "bond")
    assert bond_item.status == "within"
    assert bond_item.gap_to_min == Decimal("0")
    assert bond_item.gap_to_max == Decimal("0")

    # cash: 0.3 > 0.1 -> above
    cash_item = next(i for i in report.items if i.bucket == "cash")
    assert cash_item.status == "above"
    assert cash_item.gap_to_max == Decimal("0.2")

def test_calculate_gaps_with_unknown():
    tr = TargetRange("asset_class", "equity", Decimal("0.3"), Decimal("0.5"))
    ts = TargetSet("total", Decimal("1000000"), "CNY", False, False, [tr])

    # current 0.25, unknown 0.1 -> range [0.25, 0.35]
    # overlaps 0.3 boundary -> unknown/ambiguous
    current = {"equity": Decimal("0.25")}
    report = calculate_allocation_gaps(ts, current, unknown_pct=Decimal("0.1"))

    item = report.items[0]
    assert item.status == "unknown"
    assert item.gap_to_min == Decimal("0") # because max_possible (0.35) >= 0.3
    assert item.gap_to_max == Decimal("0")
    assert item.quality == "estimated"

    # current 0.1, unknown 0.05 -> range [0.1, 0.15]
    # max_possible 0.15 < 0.3 -> still below
    current_low = {"equity": Decimal("0.1")}
    report2 = calculate_allocation_gaps(ts, current_low, unknown_pct=Decimal("0.05"))
    assert report2.items[0].status == "below"
    assert report2.items[0].gap_to_min == Decimal("0.15")  # 0.3 - 0.15

def test_calculate_gaps_boundary_conditions():
    tr = TargetRange("asset_class", "equity", Decimal("0.3"), Decimal("0.3"))
    ts = TargetSet("total", Decimal("1000000"), "CNY", False, False, [tr])

    # Exactly on target
    report = calculate_allocation_gaps(ts, {"equity": Decimal("0.3")})
    assert report.items[0].status == "within"

    # Slightly below
    report = calculate_allocation_gaps(ts, {"equity": Decimal("0.2999")})
    assert report.items[0].status == "below"

    # Slightly above
    report = calculate_allocation_gaps(ts, {"equity": Decimal("0.3001")})
    assert report.items[0].status == "above"

def test_sorting_and_priority():
    ranges = [
        TargetRange("asset_class", "C", Decimal("0"), Decimal("1"), priority=1),
        TargetRange("asset_class", "A", Decimal("0"), Decimal("1"), priority=10),
        TargetRange("asset_class", "B", Decimal("0"), Decimal("1"), priority=5),
        TargetRange("asset_class", "D", Decimal("0"), Decimal("1"), priority=5),
    ]
    ts = TargetSet("total", Decimal("1000"), "CNY", False, False, ranges)
    report = calculate_allocation_gaps(ts, {})

    buckets = [i.bucket for i in report.items]
    assert buckets == ["A", "B", "D", "C"]

def test_empty_portfolio():
    tr = TargetRange("asset_class", "equity", Decimal("0.3"), Decimal("0.5"))
    ts = TargetSet("total", Decimal("0"), "CNY", False, False, [tr])

    report = calculate_allocation_gaps(ts, {})
    assert report.items[0].current_weight == Decimal("0")
    assert report.items[0].status == "below"
    assert report.items[0].amount_range == (Decimal("0"), Decimal("0"))

def test_negative_values_rejection():
    ts = TargetSet("total", Decimal("1000"), "CNY", False, False, [])
    with pytest.raises(ValueError, match="negative"):
        calculate_allocation_gaps(ts, {"equity": Decimal("-0.1")})
    with pytest.raises(ValueError, match="negative"):
        calculate_allocation_gaps(ts, {}, unknown_pct=Decimal("-0.01"))

    ts_neg = TargetSet("total", Decimal("-1"), "CNY", False, False, [])
    with pytest.raises(ValueError, match="negative"):
        calculate_allocation_gaps(ts_neg, {})

def test_exhaustive_unseen_bucket():
    ranges = [
        TargetRange("asset_class", "equity", Decimal("0.3"), Decimal("0.5")),
        TargetRange("asset_class", "bond", Decimal("0.5"), Decimal("0.7"))
    ]
    ts = TargetSet("total", Decimal("1000"), "CNY", True, True, ranges)

    # Only bond is present
    current = {"bond": Decimal("1.0")}
    report = calculate_allocation_gaps(ts, current)

    equity_item = next(i for i in report.items if i.bucket == "equity")
    assert equity_item.current_weight == Decimal("0")
    assert equity_item.status == "below"
