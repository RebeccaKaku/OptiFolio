"""Tests for product screening engine — normalisation, scoring, ranking."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from src.analytics.screening import (
    MoneyFundScreener,
    ProductScreener,
    ScreenedProduct,
    ScreeningCriteria,
)


# ── Helpers ───────────────────────────────────────────────────────────────


def _make_criteria(
    name="test",
    weight=1.0,
    higher_is_better=True,
    field="value",
) -> ScreeningCriteria:
    return ScreeningCriteria(
        name=name,
        weight=weight,
        higher_is_better=higher_is_better,
        field=field,
    )


def _make_fund(
    product_id="F001",
    name="Test Fund",
    annualized_7d=2.0,
    per_10k_yield=0.50,
    fund_scale=5000,
    mgmt_fee=0.30,
    redemption_days=1,
) -> dict:
    return {
        "product_id": product_id,
        "name": name,
        "product_type": "money_market_fund",
        "annualized_7d": annualized_7d,
        "per_10k_yield": per_10k_yield,
        "fund_scale": fund_scale,
        "mgmt_fee": mgmt_fee,
        "redemption_days": redemption_days,
    }


# ── ScreeningCriteria ─────────────────────────────────────────────────────


class TestScreeningCriteria:
    def test_is_frozen_dataclass(self):
        assert is_dataclass(ScreeningCriteria)
        assert ScreeningCriteria.__dataclass_params__.frozen

    def test_construction(self):
        c = ScreeningCriteria(
            name="7日年化收益率",
            weight=0.40,
            higher_is_better=True,
            field="annualized_7d",
        )
        assert c.name == "7日年化收益率"
        assert c.weight == 0.40
        assert c.higher_is_better is True
        assert c.field == "annualized_7d"

    def test_frozen_prevents_mutation(self):
        c = _make_criteria()
        with pytest.raises(FrozenInstanceError):
            c.weight = 0.5  # type: ignore[misc]

    def test_lower_is_better_false(self):
        c = ScreeningCriteria(
            name="管理费率",
            weight=0.15,
            higher_is_better=False,
            field="mgmt_fee",
        )
        assert c.higher_is_better is False


# ── ScreenedProduct ───────────────────────────────────────────────────────


class TestScreenedProduct:
    def test_is_frozen_dataclass(self):
        assert is_dataclass(ScreenedProduct)
        assert ScreenedProduct.__dataclass_params__.frozen

    def test_construction(self):
        sp = ScreenedProduct(
            product_id="004502",
            name="中银如意宝货币A",
            product_type="money_market_fund",
            score=85.0,
            rank=1,
            metrics={"annualized_7d": 2.5, "mgmt_fee": 0.25},
        )
        assert sp.product_id == "004502"
        assert sp.name == "中银如意宝货币A"
        assert sp.product_type == "money_market_fund"
        assert sp.score == 85.0
        assert sp.rank == 1
        assert sp.metrics == {"annualized_7d": 2.5, "mgmt_fee": 0.25}

    def test_frozen_prevents_mutation(self):
        sp = ScreenedProduct(
            product_id="X",
            name="X",
            product_type="fund",
            score=50.0,
            rank=1,
        )
        with pytest.raises(FrozenInstanceError):
            sp.rank = 2  # type: ignore[misc]

    def test_default_metrics_is_empty_dict(self):
        sp = ScreenedProduct(
            product_id="X",
            name="X",
            product_type="fund",
            score=50.0,
            rank=1,
        )
        assert sp.metrics == {}

    def test_to_dict(self):
        sp = ScreenedProduct(
            product_id="000198",
            name="天弘余额宝货币",
            product_type="money_market_fund",
            score=92.5,
            rank=1,
            metrics={"annualized_7d": 2.8, "per_10k_yield": 0.62},
        )
        d = sp.to_dict()
        assert d["product_id"] == "000198"
        assert d["name"] == "天弘余额宝货币"
        assert d["product_type"] == "money_market_fund"
        assert d["score"] == 92.5
        assert d["rank"] == 1
        assert d["metrics"] == {"annualized_7d": 2.8, "per_10k_yield": 0.62}

    def test_rank_is_tied_when_score_identical(self):
        """Rank-tie behaviour is exercised in the screener classes below."""
        pass


# ── ProductScreener: normalisation ───────────────────────────────────────


class _DummyScreener(ProductScreener):
    """Concrete subclass so we can test the base class."""
    pass


class TestProductScreenerNormalisation:
    def test_empty_products_returns_empty(self):
        screener = _DummyScreener()
        result = screener.screen([], [_make_criteria()])
        assert result == []

    def test_single_product_gets_score_50(self):
        """With one product all norm values are 0.5 (identical span=0),
        so weighted sum is 0.5 * 100 = 50."""
        screener = _DummyScreener()
        result = screener.screen(
            [{"product_id": "A", "name": "Fund A", "product_type": "fund", "value": 10.0}],
            [_make_criteria(field="value")],
        )
        assert len(result) == 1
        assert result[0].score == 50.0
        assert result[0].rank == 1

    def test_all_identical_values_all_score_50(self):
        screener = _DummyScreener()
        products = [
            {"product_id": "A", "name": "A", "product_type": "fund", "value": 5.0},
            {"product_id": "B", "name": "B", "product_type": "fund", "value": 5.0},
        ]
        result = screener.screen(products, [_make_criteria(field="value")])
        assert len(result) == 2
        for r in result:
            assert r.score == 50.0
        # Tied score → tied rank
        ranks = [r.rank for r in result]
        assert ranks == [1, 1]

    def test_higher_is_better_awarding(self):
        """When higher_is_better and values differ, the largest raw value
        gets the highest score."""
        screener = _DummyScreener()
        products = [
            {"product_id": "low", "name": "Low", "product_type": "fund", "yield": 1.0},
            {"product_id": "hi", "name": "Hi", "product_type": "fund", "yield": 5.0},
        ]
        result = screener.screen(
            products,
            [_make_criteria(name="yield", weight=1.0, higher_is_better=True, field="yield")],
        )
        # hi has max value → norm=1.0, low has min → norm=0.0
        sorted_result = sorted(result, key=lambda r: r.score, reverse=True)
        assert sorted_result[0].product_id == "hi"
        assert sorted_result[0].score == 100.0
        assert sorted_result[0].rank == 1
        assert sorted_result[1].product_id == "low"
        assert sorted_result[1].score == 0.0
        assert sorted_result[1].rank == 2

    def test_lower_is_better_inverts(self):
        """When higher_is_better=False, the smallest raw value gets the
        highest score."""
        screener = _DummyScreener()
        products = [
            {"product_id": "expensive", "name": "Exp", "product_type": "fund", "fee": 0.50},
            {"product_id": "cheap", "name": "Chp", "product_type": "fund", "fee": 0.10},
        ]
        result = screener.screen(
            products,
            [_make_criteria(name="fee", weight=1.0, higher_is_better=False, field="fee")],
        )
        sorted_result = sorted(result, key=lambda r: r.score, reverse=True)
        # cheap (0.10) should beat expensive (0.50)
        assert sorted_result[0].product_id == "cheap"
        assert sorted_result[0].score == 100.0
        assert sorted_result[1].product_id == "expensive"
        assert sorted_result[1].score == 0.0

    def test_missing_field_treated_as_zero(self):
        """A product missing a field gets the raw value 0.0."""
        screener = _DummyScreener()
        products = [
            {"product_id": "has_val", "name": "Has", "product_type": "fund", "yield": 5.0},
            {"product_id": "no_val", "name": "None", "product_type": "fund"},
        ]
        result = screener.screen(
            products,
            [_make_criteria(name="yield", weight=1.0, higher_is_better=True, field="yield")],
        )
        sorted_result = sorted(result, key=lambda r: r.score, reverse=True)
        assert sorted_result[0].product_id == "has_val"
        assert sorted_result[0].score == 100.0
        assert sorted_result[1].product_id == "no_val"
        assert sorted_result[1].score == 0.0

    def test_none_value_treated_as_zero(self):
        screener = _DummyScreener()
        products = [
            {"product_id": "has_val", "name": "Has", "product_type": "fund", "yield": 5.0},
            {"product_id": "none_val", "name": "None", "product_type": "fund", "yield": None},
        ]
        result = screener.screen(
            products,
            [_make_criteria(name="yield", weight=1.0, higher_is_better=True, field="yield")],
        )
        sorted_result = sorted(result, key=lambda r: r.score, reverse=True)
        assert sorted_result[0].product_id == "has_val"
        assert sorted_result[0].score == 100.0
        assert sorted_result[1].score == 0.0

    def test_product_id_defaults_to_index(self):
        screener = _DummyScreener()
        products = [
            {"name": "A", "product_type": "fund", "value": 3.0},
            {"name": "B", "product_type": "fund", "value": 1.0},
        ]
        result = screener.screen(products, [_make_criteria(field="value")])
        assert result[0].product_id == "0"
        assert result[1].product_id == "1"

    def test_name_defaults_to_empty_string(self):
        screener = _DummyScreener()
        result = screener.screen(
            [{"product_id": "X", "product_type": "fund", "value": 1.0}],
            [_make_criteria(field="value")],
        )
        assert result[0].name == ""


# ── ProductScreener: weighted scoring ──────────────────────────────────


class TestProductScreenerWeighted:
    def test_weights_renormalised_to_sum_1(self):
        """Weights 0.6 and 0.4 are already 1.0; no-op renormalisation."""
        screener = _DummyScreener()
        products = [
            {"product_id": "A", "name": "A", "product_type": "fund", "a": 10.0, "b": 0.0},
            {"product_id": "B", "name": "B", "product_type": "fund", "a": 0.0, "b": 10.0},
        ]
        criteria = [
            _make_criteria(name="a", weight=0.6, higher_is_better=True, field="a"),
            _make_criteria(name="b", weight=0.4, higher_is_better=True, field="b"),
        ]
        result = screener.screen(products, criteria)
        # A: a_norm=1.0, b_norm=0.0 → 1.0*0.6 + 0.0*0.4 = 0.6 → 60
        # B: a_norm=0.0, b_norm=1.0 → 0.0*0.6 + 1.0*0.4 = 0.4 → 40
        by_id = {r.product_id: r for r in result}
        assert by_id["A"].score == 60.0
        assert by_id["B"].score == 40.0

    def test_zero_total_weight_falls_back_to_equal(self):
        """If all weights are 0, each criterion gets equal weight."""
        screener = _DummyScreener()
        products = [
            {"product_id": "A", "name": "A", "product_type": "fund", "a": 10.0, "b": 0.0},
            {"product_id": "B", "name": "B", "product_type": "fund", "a": 0.0, "b": 10.0},
        ]
        criteria = [
            _make_criteria(name="a", weight=0.0, higher_is_better=True, field="a"),
            _make_criteria(name="b", weight=0.0, higher_is_better=True, field="b"),
        ]
        result = screener.screen(products, criteria)
        # Equal weights → 0.5 each → both get 50
        for r in result:
            assert r.score == 50.0

    def test_mixed_higher_lower_criteria(self):
        """Verify that higher_is_better and lower_is_better mix correctly."""
        screener = _DummyScreener()
        products = [
            {"product_id": "good", "name": "Good", "product_type": "fund",
             "yield": 5.0, "fee": 0.1},
            {"product_id": "bad", "name": "Bad", "product_type": "fund",
             "yield": 1.0, "fee": 0.5},
        ]
        criteria = [
            _make_criteria(name="yield", weight=0.5, higher_is_better=True, field="yield"),
            _make_criteria(name="fee", weight=0.5, higher_is_better=False, field="fee"),
        ]
        result = screener.screen(products, criteria)
        # good: yield_norm=1.0, fee_norm=1.0 → 0.5*1.0+0.5*1.0 = 1.0 → 100
        # bad:  yield_norm=0.0, fee_norm=0.0 → 0.0 → 0
        by_id = {r.product_id: r for r in result}
        assert by_id["good"].score == 100.0
        assert by_id["bad"].score == 0.0

    def test_score_is_percentage_0_to_100(self):
        screener = _DummyScreener()
        products = [
            {"product_id": f"F{i}", "name": f"F{i}", "product_type": "fund", "value": float(i)}
            for i in range(10)
        ]
        result = screener.screen(products, [_make_criteria(field="value")])
        for r in result:
            assert 0.0 <= r.score <= 100.0


# ── ProductScreener: ranking ──────────────────────────────────────────────


class TestProductScreenerRanking:
    def test_rank_1_is_highest_score(self):
        screener = _DummyScreener()
        products = [
            {"product_id": f"F{i}", "name": f"F{i}", "product_type": "fund", "value": float(i)}
            for i in range(5)
        ]
        result = screener.screen(products, [_make_criteria(field="value")])
        sorted_result = sorted(result, key=lambda r: r.rank)
        assert sorted_result[0].rank == 1
        assert sorted_result[0].score == 100.0  # F4 has max value

    def test_tied_score_same_rank(self):
        screener = _DummyScreener()
        products = [
            {"product_id": "A", "name": "A", "product_type": "fund", "value": 5.0},
            {"product_id": "B", "name": "B", "product_type": "fund", "value": 5.0},
            {"product_id": "C", "name": "C", "product_type": "fund", "value": 1.0},
        ]
        result = screener.screen(products, [_make_criteria(field="value")])
        ranks = {r.product_id: r.rank for r in result}
        # A and B tied at 100, C at 0
        assert ranks["A"] == 1
        assert ranks["B"] == 1
        assert ranks["C"] == 3  # skips 2

    def test_sort_is_stable(self):
        """The result list is sorted descending by score (best first)."""
        screener = _DummyScreener()
        products = [
            {"product_id": "low", "name": "low", "product_type": "fund", "value": 1.0},
            {"product_id": "mid", "name": "mid", "product_type": "fund", "value": 3.0},
            {"product_id": "hi", "name": "hi", "product_type": "fund", "value": 9.0},
        ]
        result = screener.screen(products, [_make_criteria(field="value")])
        # The screen() method sorts descending
        scores = [r.score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_ranks_are_consecutive_when_no_ties(self):
        screener = _DummyScreener()
        products = [
            {"product_id": f"F{i}", "name": f"F{i}", "product_type": "fund", "value": float(i)}
            for i in range(5)
        ]
        result = screener.screen(products, [_make_criteria(field="value")])
        ranks = sorted(r.rank for r in result)
        assert ranks == [1, 2, 3, 4, 5]


# ── MoneyFundScreener ─────────────────────────────────────────────────────


class TestMoneyFundScreener:
    @staticmethod
    def _typical_funds() -> list:
        return [
            _make_fund("F001", "高收益货币A", annualized_7d=2.80, per_10k_yield=0.62,
                       fund_scale=10000, mgmt_fee=0.25, redemption_days=1),
            _make_fund("F002", "稳健货币B", annualized_7d=2.10, per_10k_yield=0.48,
                       fund_scale=50000, mgmt_fee=0.15, redemption_days=1),
            _make_fund("F003", "零钱通C", annualized_7d=2.50, per_10k_yield=0.55,
                       fund_scale=20000, mgmt_fee=0.20, redemption_days=2),
        ]

    def test_screen_from_fund_data_returns_ranked_list(self):
        screener = MoneyFundScreener()
        result = screener.screen_from_fund_data(self._typical_funds())
        assert len(result) == 3
        for r in result:
            assert isinstance(r, ScreenedProduct)
            assert r.product_type == "money_market_fund"
            assert 0.0 <= r.score <= 100.0

    def test_best_fund_has_rank_1(self):
        screener = MoneyFundScreener()
        result = screener.screen_from_fund_data(self._typical_funds())
        assert result[0].rank == 1
        assert result[0].score >= result[-1].score

    def test_lowest_fee_helps(self):
        """Fund with lowest mgmt_fee should be advantaged on that dimension."""
        screener = MoneyFundScreener()
        # F_low_fee: great fee (0.10), modest yield
        # F_high_fee: terrible fee (0.50), great yield
        funds = [
            _make_fund("F_low_fee", "低费率", annualized_7d=2.20, per_10k_yield=0.50,
                       fund_scale=5000, mgmt_fee=0.10, redemption_days=1),
            _make_fund("F_high_fee", "高费率", annualized_7d=3.00, per_10k_yield=0.70,
                       fund_scale=5000, mgmt_fee=0.50, redemption_days=1),
        ]
        result = screener.screen_from_fund_data(funds)
        # The high-fee fund gets penalty on mgmt_fee dimension (0.15 weight)
        # High-yield advantage is 0.4 + 0.2 = 0.6 vs fee penalty 0.15
        # → high-fee fund likely wins overall
        by_id = {r.product_id: r for r in result}
        assert by_id["F_high_fee"].rank == 1

    def test_empty_funds_list(self):
        screener = MoneyFundScreener()
        result = screener.screen_from_fund_data([])
        assert result == []

    def test_single_fund(self):
        screener = MoneyFundScreener()
        result = screener.screen_from_fund_data([_make_fund()])
        assert len(result) == 1
        assert result[0].rank == 1

    def test_default_criteria_count(self):
        assert len(MoneyFundScreener.DEFAULT_CRITERIA) == 5
        fields = {c.field for c in MoneyFundScreener.DEFAULT_CRITERIA}
        assert fields == {"annualized_7d", "per_10k_yield", "fund_scale", "mgmt_fee", "redemption_days"}

    def test_default_criteria_weights_sum_to_one(self):
        total = sum(c.weight for c in MoneyFundScreener.DEFAULT_CRITERIA)
        assert abs(total - 1.0) < 0.001

    def test_metrics_are_included_in_result(self):
        screener = MoneyFundScreener()
        result = screener.screen_from_fund_data(self._typical_funds())
        for r in result:
            assert "annualized_7d" in r.metrics
            assert "per_10k_yield" in r.metrics
            assert "fund_scale" in r.metrics
            assert "mgmt_fee" in r.metrics
            assert "redemption_days" in r.metrics

    def test_rank_is_monotonic_with_score(self):
        """Rank should be non-decreasing as score decreases."""
        screener = MoneyFundScreener()
        result = screener.screen_from_fund_data(self._typical_funds())
        for i in range(1, len(result)):
            assert result[i].score <= result[i - 1].score

    def test_redemption_speed_advantage(self):
        """Fund with faster redemption should edge ahead when yields equal."""
        screener = MoneyFundScreener()
        funds = [
            _make_fund("F_fast", "快速赎回", redemption_days=1),
            _make_fund("F_slow", "慢速赎回", redemption_days=3),
        ]
        result = screener.screen_from_fund_data(funds)
        by_id = {r.product_id: r for r in result}
        assert by_id["F_fast"].rank == 1
        assert by_id["F_slow"].rank == 2

    def test_screen_with_custom_criteria(self):
        """MoneyFundScreener also supports the base screen() with custom criteria."""
        screener = MoneyFundScreener()
        products = [
            {"product_id": "A", "name": "A", "product_type": "fund", "yld": 5.0},
            {"product_id": "B", "name": "B", "product_type": "fund", "yld": 1.0},
        ]
        custom = [_make_criteria(name="yld", weight=1.0, higher_is_better=True, field="yld")]
        result = screener.screen(products, custom)
        assert len(result) == 2
        assert result[0].product_id == "A"
        assert result[0].rank == 1


# ── Edge cases ────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_negative_values(self):
        """Negative metric values should normalise correctly (min is negative)."""
        screener = _DummyScreener()
        products = [
            {"product_id": "neg", "name": "Neg", "product_type": "fund", "value": -5.0},
            {"product_id": "pos", "name": "Pos", "product_type": "fund", "value": 5.0},
        ]
        result = screener.screen(
            products,
            [_make_criteria(field="value", higher_is_better=True)],
        )
        sorted_result = sorted(result, key=lambda r: r.score, reverse=True)
        assert sorted_result[0].product_id == "pos"
        assert sorted_result[0].score == 100.0
        assert sorted_result[1].product_id == "neg"
        assert sorted_result[1].score == 0.0

    def test_very_large_values(self):
        """Large values should not break min-max normalisation."""
        screener = _DummyScreener()
        products = [
            {"product_id": "small", "name": "S", "product_type": "fund", "value": 1.0},
            {"product_id": "big", "name": "B", "product_type": "fund", "value": 1e9},
        ]
        result = screener.screen(
            products,
            [_make_criteria(field="value")],
        )
        sorted_result = sorted(result, key=lambda r: r.score, reverse=True)
        assert sorted_result[0].product_id == "big"
        assert sorted_result[0].score == 100.0

    def test_many_products(self):
        """Screening 100 products should work without issue."""
        screener = _DummyScreener()
        products = [
            {"product_id": f"F{i:03d}", "name": f"Fund {i}", "product_type": "fund",
             "value": float(i % 10)}
            for i in range(100)
        ]
        result = screener.screen(products, [_make_criteria(field="value")])
        assert len(result) == 100
        # 10 distinct values → 10 rank tiers (1, 11, 21, ... 91)
        unique_ranks = set(r.rank for r in result)
        assert len(unique_ranks) == 10
        assert min(r.rank for r in result) == 1

    def test_product_id_preserved(self):
        screener = _DummyScreener()
        products = [
            {"product_id": "004502", "name": "中银如意宝", "product_type": "money_market_fund",
             "value": 1.0},
            {"product_id": "000198", "name": "天弘余额宝", "product_type": "money_market_fund",
             "value": 2.0},
        ]
        result = screener.screen(products, [_make_criteria(field="value")])
        ids = {r.product_id for r in result}
        assert ids == {"004502", "000198"}
