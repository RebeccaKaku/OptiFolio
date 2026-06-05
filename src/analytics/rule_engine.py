"""Risk rule engine — explainable, testable rules-based portfolio checks.

Rules are the first advice algorithm family. Each rule inspects one
dimension of portfolio risk (liquidity, concentration, currency, exposure)
and produces a pass/fail result with a Chinese-language recommendation.

The engine works with minimal inputs — if a report is None or empty,
rules that depend on it are skipped.

Two entry points:

* ``RuleEngine.run(...)`` — accepts plain dicts; ideal for unit tests.
* ``RuleEngine.run_from_reports(...)`` — accepts typed report objects
  (LiquidityReport, ConcentrationReport, FxExposureReport) and converts
  them to dicts internally; ideal for API integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.analytics.concentration import ConcentrationReport
    from src.analytics.fx_exposure import FxExposureReport
    from src.analytics.liquidity import LiquidityReport


# ── RiskRule dataclass ────────────────────────────────────────────────────


@dataclass(frozen=True)
class RiskRule:
    """A single risk-rule check result.

    Attributes:
        rule_id: Unique rule identifier (e.g. "liquidity_emergency_fund").
        category: Risk dimension (liquidity, concentration, currency, exposure, product_risk).
        severity: info, warning, or critical.
        title: Human-readable rule name (Chinese).
        description: What was detected.
        recommendation: Suggested action (Chinese).
        passed: True if the rule is satisfied, False if triggered.
    """

    rule_id: str
    category: str
    severity: str
    title: str
    description: str
    recommendation: str
    passed: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "recommendation": self.recommendation,
            "passed": self.passed,
        }


# ── Rule engine ───────────────────────────────────────────────────────────


# Default thresholds — can be overridden via user_targets
_DEFAULT_EMERGENCY_MONTHS = 6
_DEFAULT_FX_TARGET_PCT = 20
_CURRENCY_CONCENTRATION_THRESHOLD = 0.80
_ISSUER_CONCENTRATION_THRESHOLD = 0.30
_LOCKED_ASSETS_THRESHOLD = 0.30


class RuleEngine:
    """Stateless risk-rule runner.

    Each ``run()`` call produces a list of ``RiskRule`` results.  Rules that
    cannot be evaluated (because a required report is None or empty) are
    omitted from the output — the engine does not fabricate data.
    """

    @staticmethod
    def run(
        liquidity_report: Optional[Dict[str, Any]] = None,
        concentration_report: Optional[Dict[str, Any]] = None,
        fx_exposure_report: Optional[Dict[str, Any]] = None,
        portfolio_value: float = 0.0,
        base_currency: str = "CNY",
        user_targets: Optional[Dict[str, Any]] = None,
    ) -> List[RiskRule]:
        """Evaluate all risk rules and return a list of results.

        Args:
            liquidity_report: Dict with keys like ``available_7d``,
                ``available_30d``, ``locked_amount``, ``locked_pct``.
            concentration_report: Dict with keys ``currency_distribution``
                (``{currency: weight}``) and ``issuer_distribution``
                (``{issuer: weight}``).
            fx_exposure_report: Dict with key ``non_base_exposure_pct``.
            portfolio_value: Total portfolio value in base currency.
            base_currency: ISO 4217 code of the reporting currency.
            user_targets: User-configured thresholds.
                Supported keys: ``emergency_months``, ``monthly_spending``,
                ``fx_target_pct``.

        Returns:
            List of ``RiskRule`` results (may be empty if no reports are provided).
        """
        targets = user_targets or {}
        rules: List[RiskRule] = []

        # ── a) Liquidity — emergency fund ────────────────────────────────
        if liquidity_report is not None and liquidity_report:
            rules.append(
                RuleEngine._check_emergency_fund(liquidity_report, targets)
            )

        # ── b) Concentration — single currency ───────────────────────────
        if concentration_report is not None and concentration_report:
            rules.append(
                RuleEngine._check_currency_concentration(concentration_report, base_currency)
            )

        # ── c) Concentration — single issuer ─────────────────────────────
        if concentration_report is not None and concentration_report:
            rules.append(
                RuleEngine._check_issuer_concentration(concentration_report)
            )

        # ── d) FX exposure ───────────────────────────────────────────────
        if fx_exposure_report is not None and fx_exposure_report:
            rules.append(
                RuleEngine._check_fx_exposure(fx_exposure_report, targets)
            )

        # ── e) Locked assets ─────────────────────────────────────────────
        if liquidity_report is not None and liquidity_report:
            rules.append(
                RuleEngine._check_locked_assets(liquidity_report)
            )

        return rules

    # ── typed-report entry point ─────────────────────────────────────────

    @classmethod
    def run_from_reports(
        cls,
        liquidity_report: Optional["LiquidityReport"] = None,
        concentration_report: Optional["ConcentrationReport"] = None,
        fx_exposure_report: Optional["FxExposureReport"] = None,
        portfolio_value: float = 0.0,
        base_currency: str = "CNY",
        user_targets: Optional[Dict[str, Any]] = None,
    ) -> List[RiskRule]:
        """Run rules from typed report objects (API integration path).

        Converts each typed report to a plain dict, then delegates to
        ``run()``.  See ``run()`` for the dict shapes.
        """
        liq_dict: Optional[Dict[str, Any]] = None
        conc_dict: Optional[Dict[str, Any]] = None
        fx_dict: Optional[Dict[str, Any]] = None

        # ── LiquidityReport → dict ───────────────────────────────────
        if liquidity_report is not None:
            available_7d_abs = (
                portfolio_value * liquidity_report.available_7d_pct / 100.0
                if portfolio_value > 0
                else 0.0
            )
            liq_dict = {
                "available_7d": available_7d_abs,
                "locked_pct": liquidity_report.locked_pct / 100.0,
            }

        # ── ConcentrationReport → dict ────────────────────────────────
        if concentration_report is not None:
            currency_dist = {
                item.key: item.pct / 100.0
                for item in concentration_report.by_currency
            }
            issuer_dist = {
                item.key: item.pct / 100.0
                for item in concentration_report.by_issuer
            }
            conc_dict = {
                "currency_distribution": currency_dist,
                "issuer_distribution": issuer_dist,
            }

        # ── FxExposureReport → dict ───────────────────────────────────
        if fx_exposure_report is not None:
            fx_dict = {
                "non_base_exposure_pct": fx_exposure_report.net_non_base_pct / 100.0,
            }

        return cls.run(
            liquidity_report=liq_dict,
            concentration_report=conc_dict,
            fx_exposure_report=fx_dict,
            portfolio_value=portfolio_value,
            base_currency=base_currency,
            user_targets=user_targets,
        )

    # ── individual rule checks ───────────────────────────────────────────

    @staticmethod
    def _check_emergency_fund(
        liquidity_report: Dict[str, Any],
        targets: Dict[str, Any],
    ) -> RiskRule:
        available_7d = float(liquidity_report.get("available_7d", 0) or 0)
        emergency_months = float(targets.get("emergency_months", _DEFAULT_EMERGENCY_MONTHS))
        monthly_spending = float(targets.get("monthly_spending", 0) or 0)

        if monthly_spending <= 0:
            return RiskRule(
                rule_id="liquidity_emergency_fund",
                category="liquidity",
                severity="info",
                title="紧急备用金检查",
                description="未设置月度支出目标，无法计算紧急备用金覆盖率。跳过此规则。",
                recommendation="请在用户设置中配置 monthly_spending 以启用紧急备用金检查。",
                passed=True,
            )

        required = emergency_months * monthly_spending
        passed = available_7d >= required

        if passed:
            months_covered = available_7d / monthly_spending if monthly_spending > 0 else 0
            return RiskRule(
                rule_id="liquidity_emergency_fund",
                category="liquidity",
                severity="info",
                title="紧急备用金充足",
                description=(
                    f"7天内可变现金额 {available_7d:,.0f} 元，"
                    f"覆盖 {months_covered:.1f} 个月支出"
                    f"（目标 {emergency_months} 个月 × 每月 {monthly_spending:,.0f} 元）。"
                ),
                recommendation="当前流动性充足，无需调整。",
                passed=True,
            )
        else:
            shortfall = required - available_7d
            return RiskRule(
                rule_id="liquidity_emergency_fund",
                category="liquidity",
                severity="warning",
                title="紧急备用金不足",
                description=(
                    f"7天内可变现金额 {available_7d:,.0f} 元，"
                    f"不足目标 {required:,.0f} 元"
                    f"（{emergency_months} 个月 × 每月 {monthly_spending:,.0f} 元），"
                    f"缺口 {shortfall:,.0f} 元。"
                ),
                recommendation=(
                    f"建议增加流动性资产至少 {shortfall:,.0f} 元，"
                    f"或减少月度支出目标。"
                ),
                passed=False,
            )

    @staticmethod
    def _check_currency_concentration(
        concentration_report: Dict[str, Any],
        base_currency: str,
    ) -> RiskRule:
        currency_dist = concentration_report.get("currency_distribution", {}) or {}
        if not currency_dist:
            return RiskRule(
                rule_id="concentration_single_currency",
                category="concentration",
                severity="info",
                title="单一币种集中度检查",
                description="无币种分布数据，跳过此规则。",
                recommendation="请提供 currency_distribution 数据以启用币种集中度检查。",
                passed=True,
            )

        # Find the currency with the highest weight
        top_currency = max(currency_dist, key=currency_dist.get)  # type: ignore[arg-type]
        top_weight = float(currency_dist[top_currency])
        threshold_pct = int(_CURRENCY_CONCENTRATION_THRESHOLD * 100)

        if top_weight > _CURRENCY_CONCENTRATION_THRESHOLD:
            return RiskRule(
                rule_id="concentration_single_currency",
                category="concentration",
                severity="warning",
                title="单一币种集中度偏高",
                description=(
                    f"币种 {top_currency} 占比 {top_weight:.1%}，"
                    f"超过 {threshold_pct}% 阈值。"
                ),
                recommendation=(
                    f"建议将 {top_currency} 敞口降至 {threshold_pct}% 以下，"
                    f"增持其他币种资产以分散汇率风险。"
                ),
                passed=False,
            )

        return RiskRule(
            rule_id="concentration_single_currency",
            category="concentration",
            severity="info",
            title="币种集中度正常",
            description=(
                f"最高币种 {top_currency} 占比 {top_weight:.1%}，"
                f"在 {threshold_pct}% 阈值以内。"
            ),
            recommendation="当前币种分散度合理，无需调整。",
            passed=True,
        )

    @staticmethod
    def _check_issuer_concentration(
        concentration_report: Dict[str, Any],
    ) -> RiskRule:
        issuer_dist = concentration_report.get("issuer_distribution", {}) or {}
        if not issuer_dist:
            return RiskRule(
                rule_id="concentration_single_issuer",
                category="concentration",
                severity="info",
                title="单一发行方集中度检查",
                description="无发行方分布数据，跳过此规则。",
                recommendation="请提供 issuer_distribution 数据以启用发行方集中度检查。",
                passed=True,
            )

        top_issuer = max(issuer_dist, key=issuer_dist.get)  # type: ignore[arg-type]
        top_weight = float(issuer_dist[top_issuer])
        threshold_pct = int(_ISSUER_CONCENTRATION_THRESHOLD * 100)

        if top_weight > _ISSUER_CONCENTRATION_THRESHOLD:
            return RiskRule(
                rule_id="concentration_single_issuer",
                category="concentration",
                severity="warning",
                title="单一发行方集中度偏高",
                description=(
                    f"发行方「{top_issuer}」占比 {top_weight:.1%}，"
                    f"超过 {threshold_pct}% 阈值。"
                ),
                recommendation=(
                    f"建议将「{top_issuer}」的敞口降至 {threshold_pct}% 以下，"
                    f"分散到多个发行方以降低信用风险。"
                ),
                passed=False,
            )

        return RiskRule(
            rule_id="concentration_single_issuer",
            category="concentration",
            severity="info",
            title="发行方集中度正常",
            description=(
                f"最高发行方「{top_issuer}」占比 {top_weight:.1%}，"
                f"在 {threshold_pct}% 阈值以内。"
            ),
            recommendation="当前发行方分散度合理，无需调整。",
            passed=True,
        )

    @staticmethod
    def _check_fx_exposure(
        fx_exposure_report: Dict[str, Any],
        targets: Dict[str, Any],
    ) -> RiskRule:
        non_base_pct = float(fx_exposure_report.get("non_base_exposure_pct", 0) or 0)
        fx_target_pct = float(targets.get("fx_target_pct", _DEFAULT_FX_TARGET_PCT))

        if non_base_pct <= fx_target_pct / 100.0:
            return RiskRule(
                rule_id="fx_exposure",
                category="currency",
                severity="info",
                title="外汇敞口正常",
                description=(
                    f"非本币敞口 {non_base_pct:.1%}，"
                    f"在目标 {fx_target_pct:.0f}% 以内。"
                ),
                recommendation="当前外汇敞口在目标范围内，无需调整。",
                passed=True,
            )

        excess = non_base_pct - fx_target_pct / 100.0
        return RiskRule(
            rule_id="fx_exposure",
            category="currency",
            severity="warning",
            title="外汇敞口偏高",
            description=(
                f"非本币敞口 {non_base_pct:.1%}，"
                f"超出目标 {fx_target_pct:.0f}%，"
                f"超标 {excess:.1%}。"
            ),
            recommendation=(
                f"建议减少非本币资产敞口，"
                f"或增大 fx_target_pct 以匹配当前配置。"
            ),
            passed=False,
        )

    @staticmethod
    def _check_locked_assets(
        liquidity_report: Dict[str, Any],
    ) -> RiskRule:
        locked_pct = float(liquidity_report.get("locked_pct", 0) or 0)
        threshold_pct = int(_LOCKED_ASSETS_THRESHOLD * 100)

        if locked_pct > _LOCKED_ASSETS_THRESHOLD:
            return RiskRule(
                rule_id="locked_assets",
                category="liquidity",
                severity="critical",
                title="锁仓资产比例过高",
                description=(
                    f"锁仓资产占比 {locked_pct:.1%}，"
                    f"超过 {threshold_pct}% 阈值。"
                ),
                recommendation=(
                    f"锁仓资产过高可能导致流动性危机。"
                    f"建议在锁仓到期前保持充足的流动资金，"
                    f"未来避免增加锁仓敞口。"
                ),
                passed=False,
            )

        return RiskRule(
            rule_id="locked_assets",
            category="liquidity",
            severity="info",
            title="锁仓资产比例正常",
            description=(
                f"锁仓资产占比 {locked_pct:.1%}，"
                f"在 {threshold_pct}% 阈值以内。"
            ),
            recommendation="当前锁仓比例合理，无需调整。",
            passed=True,
        )

    # ── summary ───────────────────────────────────────────────────────────

    @staticmethod
    def summary(rules: List[RiskRule]) -> Dict[str, Any]:
        """Aggregate rule results into a summary dict.

        Returns:
            Dict with keys ``total_rules``, ``passed``, ``warning_count``,
            ``critical_count``, ``failed`` (any rule with passed=False),
            and ``by_category`` (dict of category → count).
        """
        total = len(rules)
        passed = sum(1 for r in rules if r.passed)
        failed = total - passed
        warning_count = sum(1 for r in rules if not r.passed and r.severity == "warning")
        critical_count = sum(1 for r in rules if not r.passed and r.severity == "critical")
        info_fired = sum(1 for r in rules if not r.passed and r.severity == "info")

        by_category: Dict[str, int] = {}
        for r in rules:
            by_category[r.category] = by_category.get(r.category, 0) + 1

        return {
            "total_rules": total,
            "passed": passed,
            "failed": failed,
            "warning_count": warning_count,
            "critical_count": critical_count,
            "info_fired": info_fired,
            "by_category": by_category,
            "overall_healthy": failed == 0,
        }
