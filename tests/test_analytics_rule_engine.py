"""Tests for RuleEngine — risk rule evaluation and summary aggregation."""

from __future__ import annotations

from dataclasses import is_dataclass

import pytest

from src.analytics.rule_engine import RiskRule, RuleEngine


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_rule(rule_id="test", passed=True, severity="info", category="test") -> RiskRule:
    return RiskRule(
        rule_id=rule_id,
        category=category,
        severity=severity,
        title="Test Rule",
        description="Test description",
        recommendation="Test recommendation",
        passed=passed,
    )


# ── RiskRule dataclass ─────────────────────────────────────────────────────


class TestRiskRule:
    """RiskRule frozen dataclass construction and serialization."""

    def test_is_frozen_dataclass(self):
        assert is_dataclass(RiskRule)
        assert RiskRule.__dataclass_params__.frozen

    def test_construction(self):
        r = RiskRule(
            rule_id="liquidity_emergency_fund",
            category="liquidity",
            severity="warning",
            title="紧急备用金不足",
            description="7天内可变现金额不足。",
            recommendation="建议增加流动性资产。",
            passed=False,
        )
        assert r.rule_id == "liquidity_emergency_fund"
        assert r.category == "liquidity"
        assert r.severity == "warning"
        assert r.title == "紧急备用金不足"
        assert r.passed is False

    def test_frozen_prevents_mutation(self):
        from dataclasses import FrozenInstanceError

        r = _make_rule()
        with pytest.raises(FrozenInstanceError):
            r.passed = False  # type: ignore[misc]

    def test_to_dict(self):
        r = RiskRule(
            rule_id="concentration_single_currency",
            category="concentration",
            severity="warning",
            title="单一币种集中度偏高",
            description="USD 占比 85%",
            recommendation="建议分散币种。",
            passed=False,
        )
        d = r.to_dict()
        assert d["rule_id"] == "concentration_single_currency"
        assert d["category"] == "concentration"
        assert d["severity"] == "warning"
        assert d["title"] == "单一币种集中度偏高"
        assert d["description"] == "USD 占比 85%"
        assert d["recommendation"] == "建议分散币种。"
        assert d["passed"] is False


# ── Rule a: Liquidity — emergency fund ─────────────────────────────────────


class TestEmergencyFundRule:
    """Liquidity rule: 7-day available cash >= emergency_months * monthly_spending."""

    def test_passes_when_sufficient(self):
        """7-day cash of 150k covers 6 months * 20k = 120k."""
        liquidity = {"available_7d": 150_000}
        targets = {"emergency_months": 6, "monthly_spending": 20_000}
        rules = RuleEngine.run(liquidity_report=liquidity, user_targets=targets)
        emergency = [r for r in rules if r.rule_id == "liquidity_emergency_fund"]
        assert len(emergency) == 1
        assert emergency[0].passed is True
        assert emergency[0].severity == "info"

    def test_fails_when_insufficient(self):
        """7-day cash of 50k does NOT cover 6 months * 20k = 120k."""
        liquidity = {"available_7d": 50_000}
        targets = {"emergency_months": 6, "monthly_spending": 20_000}
        rules = RuleEngine.run(liquidity_report=liquidity, user_targets=targets)
        emergency = [r for r in rules if r.rule_id == "liquidity_emergency_fund"]
        assert len(emergency) == 1
        assert emergency[0].passed is False
        assert emergency[0].severity == "warning"
        assert "缺口" in emergency[0].description

    def test_exact_match_passes(self):
        """Exact coverage (120k = 6 * 20k) should pass."""
        liquidity = {"available_7d": 120_000}
        targets = {"emergency_months": 6, "monthly_spending": 20_000}
        rules = RuleEngine.run(liquidity_report=liquidity, user_targets=targets)
        emergency = [r for r in rules if r.rule_id == "liquidity_emergency_fund"]
        assert emergency[0].passed is True

    def test_monthly_spending_zero_skips_with_info(self):
        """When monthly_spending is 0, the rule returns passed=True as info."""
        liquidity = {"available_7d": 100_000}
        targets = {"emergency_months": 6, "monthly_spending": 0}
        rules = RuleEngine.run(liquidity_report=liquidity, user_targets=targets)
        emergency = [r for r in rules if r.rule_id == "liquidity_emergency_fund"]
        assert len(emergency) == 1
        assert emergency[0].passed is True
        assert emergency[0].severity == "info"
        assert "月度支出" in emergency[0].description

    def test_user_targets_control_threshold(self):
        """Changing emergency_months from 6 to 3 changes the threshold."""
        liquidity = {"available_7d": 80_000}

        # 3 months * 20k = 60k → passes
        rules_low = RuleEngine.run(
            liquidity_report=liquidity,
            user_targets={"emergency_months": 3, "monthly_spending": 20_000},
        )
        r_low = [r for r in rules_low if r.rule_id == "liquidity_emergency_fund"][0]
        assert r_low.passed is True

        # 6 months * 20k = 120k → fails
        rules_high = RuleEngine.run(
            liquidity_report=liquidity,
            user_targets={"emergency_months": 6, "monthly_spending": 20_000},
        )
        r_high = [r for r in rules_high if r.rule_id == "liquidity_emergency_fund"][0]
        assert r_high.passed is False

    def test_default_thresholds(self):
        """Without user_targets, uses defaults (6 months, 0 spending → skips)."""
        liquidity = {"available_7d": 100_000}
        rules = RuleEngine.run(liquidity_report=liquidity)
        emergency = [r for r in rules if r.rule_id == "liquidity_emergency_fund"]
        assert len(emergency) == 1
        # Default monthly_spending = 0 → info, passed
        assert emergency[0].severity == "info"
        assert emergency[0].passed is True


# ── Rule b: Concentration — single currency ────────────────────────────────


class TestCurrencyConcentrationRule:
    """Concentration rule: single currency > 80% triggers warning."""

    def test_passes_when_under_threshold(self):
        conc = {"currency_distribution": {"CNY": 0.70, "USD": 0.20, "HKD": 0.10}}
        rules = RuleEngine.run(concentration_report=conc, base_currency="CNY")
        currency_r = [r for r in rules if r.rule_id == "concentration_single_currency"]
        assert len(currency_r) == 1
        assert currency_r[0].passed is True

    def test_fails_when_over_threshold(self):
        conc = {"currency_distribution": {"CNY": 0.85, "USD": 0.15}}
        rules = RuleEngine.run(concentration_report=conc, base_currency="CNY")
        currency_r = [r for r in rules if r.rule_id == "concentration_single_currency"]
        assert len(currency_r) == 1
        assert currency_r[0].passed is False
        assert currency_r[0].severity == "warning"
        assert "CNY" in currency_r[0].description
        assert "85" in currency_r[0].description.replace("%", "").replace(".", "").replace("0", "") or "85" in currency_r[0].description

    def test_exact_80_pct_passes(self):
        """Exactly 80% is not > 80%, so it passes."""
        conc = {"currency_distribution": {"CNY": 0.80, "USD": 0.20}}
        rules = RuleEngine.run(concentration_report=conc, base_currency="CNY")
        currency_r = [r for r in rules if r.rule_id == "concentration_single_currency"]
        assert currency_r[0].passed is True

    def test_just_above_threshold_fails(self):
        """80.1% is > 80%, so it fails."""
        conc = {"currency_distribution": {"CNY": 0.801, "USD": 0.199}}
        rules = RuleEngine.run(concentration_report=conc, base_currency="CNY")
        currency_r = [r for r in rules if r.rule_id == "concentration_single_currency"]
        assert currency_r[0].passed is False

    def test_empty_distribution_skips(self):
        conc = {"currency_distribution": {}}
        rules = RuleEngine.run(concentration_report=conc, base_currency="CNY")
        currency_r = [r for r in rules if r.rule_id == "concentration_single_currency"]
        assert len(currency_r) == 1
        assert currency_r[0].passed is True
        assert currency_r[0].severity == "info"


# ── Rule c: Concentration — single issuer ──────────────────────────────────


class TestIssuerConcentrationRule:
    """Concentration rule: single issuer > 30% triggers warning."""

    def test_passes_when_under_threshold(self):
        conc = {
            "issuer_distribution": {
                "中国工商银行": 0.20,
                "中国银行": 0.20,
                "招商银行": 0.15,
                "建设银行": 0.15,
                "农业银行": 0.15,
                "交通银行": 0.15,
            }
        }
        rules = RuleEngine.run(concentration_report=conc)
        issuer_r = [r for r in rules if r.rule_id == "concentration_single_issuer"]
        assert len(issuer_r) == 1
        assert issuer_r[0].passed is True

    def test_fails_when_over_threshold(self):
        conc = {
            "issuer_distribution": {
                "某基金公司": 0.45,
                "工商银行": 0.20,
                "招商银行": 0.15,
                "建设银行": 0.10,
                "农业银行": 0.10,
            }
        }
        rules = RuleEngine.run(concentration_report=conc)
        issuer_r = [r for r in rules if r.rule_id == "concentration_single_issuer"]
        assert len(issuer_r) == 1
        assert issuer_r[0].passed is False
        assert issuer_r[0].severity == "warning"
        assert "某基金公司" in issuer_r[0].description

    def test_exact_30_pct_passes(self):
        conc = {
            "issuer_distribution": {
                "发行人A": 0.25,
                "发行人B": 0.25,
                "发行人C": 0.25,
                "发行人D": 0.25,
            }
        }
        rules = RuleEngine.run(concentration_report=conc)
        issuer_r = [r for r in rules if r.rule_id == "concentration_single_issuer"]
        assert issuer_r[0].passed is True

    def test_empty_issuer_distribution_skips(self):
        conc = {"issuer_distribution": {}}
        rules = RuleEngine.run(concentration_report=conc)
        issuer_r = [r for r in rules if r.rule_id == "concentration_single_issuer"]
        assert len(issuer_r) == 1
        assert issuer_r[0].passed is True
        assert issuer_r[0].severity == "info"


# ── Rule d: FX exposure ────────────────────────────────────────────────────


class TestFxExposureRule:
    """FX exposure rule: non-base currency exposure > target% triggers warning."""

    def test_passes_when_under_target(self):
        fx = {"non_base_exposure_pct": 0.15}
        targets = {"fx_target_pct": 20}
        rules = RuleEngine.run(fx_exposure_report=fx, user_targets=targets)
        fx_r = [r for r in rules if r.rule_id == "fx_exposure"]
        assert len(fx_r) == 1
        assert fx_r[0].passed is True

    def test_fails_when_over_target(self):
        fx = {"non_base_exposure_pct": 0.35}
        targets = {"fx_target_pct": 20}
        rules = RuleEngine.run(fx_exposure_report=fx, user_targets=targets)
        fx_r = [r for r in rules if r.rule_id == "fx_exposure"]
        assert len(fx_r) == 1
        assert fx_r[0].passed is False
        assert fx_r[0].severity == "warning"

    def test_user_target_controls_threshold(self):
        fx = {"non_base_exposure_pct": 0.25}
        # Target 30% → 25% is under → passes
        rules_pass = RuleEngine.run(
            fx_exposure_report=fx, user_targets={"fx_target_pct": 30}
        )
        r_pass = [r for r in rules_pass if r.rule_id == "fx_exposure"][0]
        assert r_pass.passed is True

        # Target 10% → 25% is over → fails
        rules_fail = RuleEngine.run(
            fx_exposure_report=fx, user_targets={"fx_target_pct": 10}
        )
        r_fail = [r for r in rules_fail if r.rule_id == "fx_exposure"][0]
        assert r_fail.passed is False

    def test_exact_target_passes(self):
        fx = {"non_base_exposure_pct": 0.20}
        targets = {"fx_target_pct": 20}
        rules = RuleEngine.run(fx_exposure_report=fx, user_targets=targets)
        fx_r = [r for r in rules if r.rule_id == "fx_exposure"][0]
        assert fx_r.passed is True

    def test_default_threshold(self):
        """Without user_targets, uses default fx_target_pct = 20."""
        fx = {"non_base_exposure_pct": 0.10}
        rules = RuleEngine.run(fx_exposure_report=fx)
        fx_r = [r for r in rules if r.rule_id == "fx_exposure"][0]
        assert fx_r.passed is True


# ── Rule e: Locked assets ──────────────────────────────────────────────────


class TestLockedAssetsRule:
    """Locked assets rule: locked_pct > 30% triggers critical."""

    def test_passes_when_under_threshold(self):
        liquidity = {"locked_pct": 0.15}
        rules = RuleEngine.run(liquidity_report=liquidity)
        locked_r = [r for r in rules if r.rule_id == "locked_assets"]
        assert len(locked_r) == 1
        assert locked_r[0].passed is True
        assert locked_r[0].severity == "info"

    def test_fails_when_over_threshold(self):
        liquidity = {"locked_pct": 0.45}
        rules = RuleEngine.run(liquidity_report=liquidity)
        locked_r = [r for r in rules if r.rule_id == "locked_assets"]
        assert len(locked_r) == 1
        assert locked_r[0].passed is False
        assert locked_r[0].severity == "critical"
        assert "锁仓" in locked_r[0].title

    def test_exact_30_pct_passes(self):
        liquidity = {"locked_pct": 0.30}
        rules = RuleEngine.run(liquidity_report=liquidity)
        locked_r = [r for r in rules if r.rule_id == "locked_assets"][0]
        assert locked_r.passed is True

    def test_just_above_threshold_fails(self):
        """30.1% should be > 30% and trigger critical."""
        liquidity = {"locked_pct": 0.301}
        rules = RuleEngine.run(liquidity_report=liquidity)
        locked_r = [r for r in rules if r.rule_id == "locked_assets"][0]
        assert locked_r.passed is False


# ── None / empty report handling ───────────────────────────────────────────


class TestNoneReportSkipping:
    """Rules dependent on missing reports are simply omitted."""

    def test_all_reports_none_returns_empty(self):
        rules = RuleEngine.run()
        assert rules == []

    def test_concentration_none_skips_currency_and_issuer(self):
        liquidity = {"available_7d": 100_000, "locked_pct": 0.10}
        targets = {"emergency_months": 3, "monthly_spending": 20_000}
        rules = RuleEngine.run(liquidity_report=liquidity, user_targets=targets)
        rule_ids = {r.rule_id for r in rules}
        # Liquidity rules should run, concentration rules should be skipped
        assert "liquidity_emergency_fund" in rule_ids
        assert "locked_assets" in rule_ids
        assert "concentration_single_currency" not in rule_ids
        assert "concentration_single_issuer" not in rule_ids

    def test_fx_exposure_none_skips_fx_rule(self):
        conc = {"currency_distribution": {"CNY": 0.70, "USD": 0.30}}
        rules = RuleEngine.run(concentration_report=conc, base_currency="CNY")
        rule_ids = {r.rule_id for r in rules}
        assert "concentration_single_currency" in rule_ids
        assert "concentration_single_issuer" in rule_ids
        assert "fx_exposure" not in rule_ids

    def test_empty_dict_treated_as_data(self):
        """Empty dicts are treated as having data (not None), so rules run."""
        rules = RuleEngine.run(
            liquidity_report={},
            concentration_report={},
            fx_exposure_report={},
        )
        # Empty dicts === falsy, so rules are skipped (our guard checks `and`)
        assert rules == []


# ── Summary aggregation ────────────────────────────────────────────────────


class TestSummary:
    """RuleEngine.summary() aggregates a list of RiskRule results."""

    def test_all_passed(self):
        rules = [
            _make_rule("r1", passed=True, severity="info", category="liquidity"),
            _make_rule("r2", passed=True, severity="info", category="concentration"),
        ]
        s = RuleEngine.summary(rules)
        assert s["total_rules"] == 2
        assert s["passed"] == 2
        assert s["failed"] == 0
        assert s["warning_count"] == 0
        assert s["critical_count"] == 0
        assert s["overall_healthy"] is True

    def test_mixed_results(self):
        rules = [
            _make_rule("r1", passed=True, severity="info", category="liquidity"),
            _make_rule("r2", passed=False, severity="warning", category="concentration"),
            _make_rule("r3", passed=False, severity="critical", category="liquidity"),
            _make_rule("r4", passed=True, severity="info", category="currency"),
        ]
        s = RuleEngine.summary(rules)
        assert s["total_rules"] == 4
        assert s["passed"] == 2
        assert s["failed"] == 2
        assert s["warning_count"] == 1
        assert s["critical_count"] == 1
        assert s["info_fired"] == 0
        assert s["overall_healthy"] is False
        assert s["by_category"]["liquidity"] == 2
        assert s["by_category"]["concentration"] == 1
        assert s["by_category"]["currency"] == 1

    def test_empty_rules(self):
        s = RuleEngine.summary([])
        assert s["total_rules"] == 0
        assert s["passed"] == 0
        assert s["failed"] == 0
        assert s["warning_count"] == 0
        assert s["critical_count"] == 0
        assert s["overall_healthy"] is True

    def test_all_failed(self):
        rules = [
            _make_rule("r1", passed=False, severity="warning", category="liquidity"),
            _make_rule("r2", passed=False, severity="critical", category="concentration"),
        ]
        s = RuleEngine.summary(rules)
        assert s["total_rules"] == 2
        assert s["passed"] == 0
        assert s["failed"] == 2
        assert s["overall_healthy"] is False

    def test_info_fired_counted_in_failed(self):
        """Even info-severity rules count as failed if passed=False."""
        rules = [
            _make_rule("r1", passed=False, severity="info", category="liquidity"),
        ]
        s = RuleEngine.summary(rules)
        assert s["failed"] == 1
        assert s["info_fired"] == 1


# ── Full integration style test ────────────────────────────────────────────


class TestFullRun:
    """End-to-end: run all rules with all reports."""

    def test_all_reports_all_rules(self):
        liquidity = {"available_7d": 200_000, "locked_pct": 0.10}
        concentration = {
            "currency_distribution": {"CNY": 0.70, "USD": 0.20, "HKD": 0.10},
            "issuer_distribution": {
                "工商银行": 0.15,
                "招商银行": 0.15,
                "蚂蚁基金": 0.20,
                "建设银行": 0.15,
                "农业银行": 0.15,
                "中国银行": 0.20,
            },
        }
        fx = {"non_base_exposure_pct": 0.25}
        targets = {
            "emergency_months": 6,
            "monthly_spending": 20_000,
            "fx_target_pct": 30,
        }

        rules = RuleEngine.run(
            liquidity_report=liquidity,
            concentration_report=concentration,
            fx_exposure_report=fx,
            base_currency="CNY",
            user_targets=targets,
        )

        # All 5 rules should run
        assert len(rules) == 5
        rule_ids = {r.rule_id for r in rules}
        assert rule_ids == {
            "liquidity_emergency_fund",
            "concentration_single_currency",
            "concentration_single_issuer",
            "fx_exposure",
            "locked_assets",
        }

        # All should pass with these inputs
        assert all(r.passed for r in rules)

        summary = RuleEngine.summary(rules)
        assert summary["overall_healthy"] is True
        assert summary["total_rules"] == 5
        assert summary["passed"] == 5
