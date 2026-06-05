"""Alert engine — practical portfolio alerts for risk and event monitoring.

Alerts precede return prediction in the advice pipeline.  Each alert carries
a reason, supporting evidence, severity, and a suggested action so the user
can act on it without deep analysis.

Checks
------
* **drawdown** — portfolio dropped > X% from its all-time peak.
* **maturity / open date** — products approaching maturity or lockup expiry.
* **FX loss** — non-base-currency exposure high enough that an unfavourable
  FX move would cause a material loss.
* **concentration creep** — any concentration dimension increased by more
  than X percentage points since the last snapshot.
* **open windows** — fund subscription / redemption windows opening soon
  or currently closed (East Money ``fund_purchase_em`` data).

Usage::

    engine = AlertEngine()
    alerts = engine.run_all(context)
    for a in alerts:
        print(a.title, a.severity)
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from src.analytics.fx_exposure import FxExposureReport


# ── Alert dataclass ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Alert:
    """A single actionable portfolio alert.

    Attributes:
        alert_id: Unique, descriptive identifier (e.g. ``"drawdown_5pct"``).
        title: Human-readable one-line summary.
        reason: What triggered this alert.
        evidence: Data that proves it (e.g. current values, thresholds).
        severity: ``info``, ``warning``, or ``critical``.
        suggested_action: What the user should consider doing.
        created_at: ISO-8601 timestamp.
    """

    alert_id: str
    title: str
    reason: str
    evidence: Dict[str, Any]
    severity: str  # info | warning | critical
    suggested_action: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "title": self.title,
            "reason": self.reason,
            "evidence": copy.deepcopy(self.evidence),
            "severity": self.severity,
            "suggested_action": self.suggested_action,
            "created_at": self.created_at,
        }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_id(prefix: str, *parts: str) -> str:
    """Build a descriptive alert_id like ``drawdown_8pct`` or ``maturity_WMP1_15d``."""
    slug = "_".join(str(p).replace(" ", "_") for p in parts if p)
    return f"{prefix}_{slug}" if slug else prefix


# ── Alert Engine ─────────────────────────────────────────────────────────────


class AlertEngine:
    """Stateless alert runner.

    Each method inspects one risk or event dimension and returns zero or more
    ``Alert`` objects.  ``run_all()`` orchestrates all checks from a single
    context dictionary.
    """

    # ── Default thresholds ────────────────────────────────────────────────

    DEFAULT_DRAWDOWN_THRESHOLD_PCT: float = 5.0
    DEFAULT_MATURITY_WINDOW_DAYS: int = 30
    DEFAULT_FX_LOSS_THRESHOLD_PCT: float = 2.0
    DEFAULT_CONCENTRATION_CREEP_THRESHOLD: float = 5.0  # percentage points
    DEFAULT_OPEN_WINDOW_DAYS: int = 30
    DEFAULT_STALE_PRICE_THRESHOLD_PCT: float = 10.0  # % of tracked assets

    # ── Individual checks ─────────────────────────────────────────────────

    def check_drawdown(
        self,
        equity_curve: pd.DataFrame,
        threshold_pct: float = DEFAULT_DRAWDOWN_THRESHOLD_PCT,
    ) -> Optional[Alert]:
        """Alert if the portfolio has dropped more than *threshold_pct* from its peak.

        Args:
            equity_curve: DataFrame with at least a ``total_value`` column.
                An optional ``date`` column is used for evidence timestamps.
            threshold_pct: Drawdown percentage that triggers an alert (default 5.0).

        Returns:
            An ``Alert`` if the current drawdown exceeds the threshold, else ``None``.
        """
        if equity_curve.empty or "total_value" not in equity_curve.columns:
            return None

        values = equity_curve["total_value"].values
        peak = float(values.max())
        current = float(values[-1])

        if peak <= 0:
            return None

        drawdown_pct = round((peak - current) / peak * 100, 2)

        if drawdown_pct < threshold_pct:
            return None

        peak_idx = int(values.argmax())
        peak_date = None
        current_date = None
        if "date" in equity_curve.columns:
            peak_date = str(equity_curve["date"].iloc[peak_idx])
            current_date = str(equity_curve["date"].iloc[-1])

        severity = "critical" if drawdown_pct >= threshold_pct * 2 else "warning"

        return Alert(
            alert_id=_make_id("drawdown", f"{int(drawdown_pct)}pct"),
            title=f"投资组合回撤 {drawdown_pct:.1f}%",
            reason=(
                f"组合净值从峰值 ¥{peak:,.2f} 回落至 ¥{current:,.2f}，"
                f"回撤 {drawdown_pct:.1f}%，超过 {threshold_pct:.0f}% 阈值。"
            ),
            evidence={
                "peak_value": peak,
                "current_value": current,
                "drawdown_pct": drawdown_pct,
                "threshold_pct": threshold_pct,
                "peak_date": peak_date,
                "current_date": current_date,
            },
            severity=severity,
            suggested_action=(
                f"回撤已达 {drawdown_pct:.1f}%，建议检查持仓是否触发止损纪律。"
                f"若为市场系统性下跌，可评估是否有加仓机会；"
                f"若为单一资产拖累，考虑减仓或替换。"
            ),
            created_at=_now_iso(),
        )

    def check_maturity(
        self,
        products: List[Dict[str, Any]],
        as_of: date,
        within_days: int = DEFAULT_MATURITY_WINDOW_DAYS,
    ) -> List[Alert]:
        """Alert for products approaching maturity, lockup expiry, or open date.

        Each product dict may contain any of these date keys (date or ISO string):
        ``maturity_date``, ``lockup_end_date``, ``open_date``, ``next_open_date``.

        Args:
            products: List of product dicts.  Each must have at least a
                ``product_id`` or ``name`` key for identification.
            as_of: Reference date for computing days-until-maturity.
            within_days: Look-ahead window in days (default 30).

        Returns:
            List of ``Alert`` objects (one per approaching deadline).
        """
        alerts: List[Alert] = []

        date_keys = ("maturity_date", "lockup_end_date", "open_date", "next_open_date")

        for prod in products:
            prod_id = prod.get("product_id") or prod.get("name") or prod.get("fund_code", "unknown")

            for dk in date_keys:
                raw = prod.get(dk)
                if raw is None:
                    continue

                target = _parse_date(raw)
                if target is None:
                    continue

                days_left = (target - as_of).days

                if 0 <= days_left <= within_days:
                    label_map = {
                        "maturity_date": "到期",
                        "lockup_end_date": "锁仓到期",
                        "open_date": "开放",
                        "next_open_date": "下一开放日",
                    }
                    label = label_map.get(dk, dk)

                    if days_left == 0:
                        time_desc = "今天"
                    elif days_left == 1:
                        time_desc = "明天"
                    else:
                        time_desc = f"{days_left} 天后"

                    alerts.append(Alert(
                        alert_id=_make_id("maturity", str(prod_id), f"{days_left}d"),
                        title=f"产品「{prod_id}」{label}临近",
                        reason=(
                            f"产品「{prod_id}」的{label}日期为 {target.isoformat()}，"
                            f"距今仅 {time_desc}。"
                        ),
                        evidence={
                            "product_id": prod_id,
                            "date_type": dk,
                            "target_date": target.isoformat(),
                            "days_left": days_left,
                            "within_days": within_days,
                        },
                        severity="warning" if days_left <= 7 else "info",
                        suggested_action=(
                            f"建议提前准备资金安排，确认是否续投、赎回或调整配置。"
                            f"若为锁仓到期，可评估释放后的流动性用途。"
                        ),
                        created_at=_now_iso(),
                    ))
                    break  # one alert per product (first matching date)

        return alerts

    def check_fx_loss(
        self,
        fx_exposure_report: Any,
        loss_threshold_pct: float = DEFAULT_FX_LOSS_THRESHOLD_PCT,
    ) -> Optional[Alert]:
        """Alert if non-base-currency exposure is high enough that FX moves
        could cause a material loss.

        Accepts either an ``FxExposureReport`` dataclass or a plain dict with
        keys ``net_non_base_pct`` and ``exposures``.

        Args:
            fx_exposure_report: ``FxExposureReport`` or dict with
                ``net_non_base_pct`` (float, 0-100) and ``exposures`` (list of
                per-currency exposure items).
            loss_threshold_pct: Net non-base exposure percentage that triggers
                an alert (default 2.0).

        Returns:
            An ``Alert`` if non-base exposure exceeds the threshold, else ``None``.
        """
        # ── Normalise input ──────────────────────────────────────────────
        if fx_exposure_report is None:
            return None

        if hasattr(fx_exposure_report, "net_non_base_pct"):
            net_non_base = float(fx_exposure_report.net_non_base_pct)
            exposures = getattr(fx_exposure_report, "exposures", [])
            base_currency = getattr(fx_exposure_report, "base_currency", "CNY")
        elif isinstance(fx_exposure_report, dict):
            net_non_base = float(fx_exposure_report.get("net_non_base_pct", 0) or 0)
            exposures = fx_exposure_report.get("exposures", [])
            base_currency = fx_exposure_report.get("base_currency", "CNY")
        else:
            return None

        if net_non_base < loss_threshold_pct:
            return None

        # ── Gather evidence from per-currency exposures ──────────────────
        top_exposures: Dict[str, float] = {}
        for exp in exposures:
            if hasattr(exp, "currency"):
                cur = str(exp.currency)
                pct = float(getattr(exp, "pct", 0))
            elif isinstance(exp, dict):
                cur = str(exp.get("currency", "?"))
                pct = float(exp.get("pct", 0))
            else:
                continue
            if cur != base_currency and pct > 0:
                top_exposures[cur] = pct

        top_currency = max(top_exposures, key=top_exposures.get) if top_exposures else "N/A"
        top_pct = top_exposures.get(top_currency, 0.0)

        severity = "critical" if net_non_base >= loss_threshold_pct * 5 else (
            "warning" if net_non_base >= loss_threshold_pct * 2 else "info"
        )

        return Alert(
            alert_id=_make_id("fx_loss", f"{int(net_non_base)}pct"),
            title=f"外汇敞口 {net_non_base:.1f}% — 存在汇率损失风险",
            reason=(
                f"非{base_currency}资产敞口合计 {net_non_base:.1f}%，"
                f"超过 {loss_threshold_pct:.0f}% 警戒线。"
                f"最大单一外币敞口为 {top_currency}（{top_pct:.1f}%）。"
                f"若{top_currency}/{base_currency}贬值1%，组合净值将损失约 "
                f"{net_non_base * 0.01:.2f}%。"
            ),
            evidence={
                "net_non_base_pct": net_non_base,
                "loss_threshold_pct": loss_threshold_pct,
                "base_currency": base_currency,
                "top_currency": top_currency,
                "top_currency_pct": top_pct,
                "all_non_base_exposures": top_exposures,
            },
            severity=severity,
            suggested_action=(
                f"非本币敞口 {net_non_base:.1f}% 偏高。"
                f"建议：1) 减少{top_currency}资产敞口；"
                f"2) 使用外汇对冲工具（如远期、期权）锁定汇率；"
                f"3) 提高本币资产比例至目标区间。"
            ),
            created_at=_now_iso(),
        )

    def check_concentration_creep(
        self,
        current: Dict[str, Dict[str, float]],
        previous: Dict[str, Dict[str, float]],
        increase_threshold: float = DEFAULT_CONCENTRATION_CREEP_THRESHOLD,
    ) -> Optional[Alert]:
        """Alert if any concentration dimension increased by more than
        *increase_threshold* percentage points since the previous snapshot.

        Args:
            current: Current concentration breakdown, keyed by dimension name
                (e.g. ``"currency"``, ``"asset_class"``, ``"issuer"``), each
                mapping group keys to percentage values (0-100).
            previous: Previous concentration breakdown in the same shape.
            increase_threshold: Percentage-point increase that triggers an
                alert (default 5.0).

        Returns:
            An ``Alert`` if any group's concentration increased beyond the
            threshold, else ``None``.
        """
        if not current or not previous:
            return None

        creep_findings: List[Dict[str, Any]] = []

        for dimension in current:
            cur_dist = current.get(dimension, {})
            prev_dist = previous.get(dimension, {})

            for key, cur_pct in cur_dist.items():
                prev_pct = prev_dist.get(key, 0.0)
                delta = round(cur_pct - prev_pct, 2)

                if delta > increase_threshold:
                    creep_findings.append({
                        "dimension": dimension,
                        "key": key,
                        "previous_pct": prev_pct,
                        "current_pct": cur_pct,
                        "delta_pct": delta,
                    })

        if not creep_findings:
            return None

        # ── Build the alert from findings ────────────────────────────────
        creep_findings.sort(key=lambda x: x["delta_pct"], reverse=True)
        worst = creep_findings[0]

        dim_label = {
            "currency": "币种",
            "asset_class": "资产类别",
            "issuer": "发行方/管理人",
        }.get(worst["dimension"], worst["dimension"])

        severity = (
            "critical" if worst["delta_pct"] >= increase_threshold * 3
            else "warning"
        )

        # Summary of all findings
        summary_parts = []
        for f in creep_findings[:3]:  # top 3
            summary_parts.append(
                f"{f['dimension']}/{f['key']}: {f['previous_pct']:.1f}% → {f['current_pct']:.1f}% (+{f['delta_pct']:.1f}pp)"
            )

        return Alert(
            alert_id=_make_id(
                "concentration_creep",
                worst["dimension"],
                worst["key"].replace(" ", "_"),
                f"{int(worst['delta_pct'])}pp",
            ),
            title=f"{dim_label}集中度上升 — 「{worst['key']}」+{worst['delta_pct']:.1f}pp",
            reason=(
                f"{dim_label}「{worst['key']}」占比从 {worst['previous_pct']:.1f}% "
                f"升至 {worst['current_pct']:.1f}%（+{worst['delta_pct']:.1f} 个百分点），"
                f"超过 {increase_threshold:.0f}pp 警戒线。"
                f"变化明细：{'；'.join(summary_parts)}"
            ),
            evidence={
                "findings": creep_findings,
                "increase_threshold_pp": increase_threshold,
            },
            severity=severity,
            suggested_action=(
                f"「{worst['key']}」集中度快速上升 {worst['delta_pct']:.1f}pp。"
                f"建议：1) 检查是否因单一资产大涨导致被动超配；"
                f"2) 如需控制风险，可适当再平衡；"
                f"3) 评估该集中度是否在可接受范围内。"
            ),
            created_at=_now_iso(),
        )

    def check_stale_prices(
        self,
        quality_summary: Dict[str, Any],
        threshold_pct: float = DEFAULT_STALE_PRICE_THRESHOLD_PCT,
    ) -> Optional[Alert]:
        """Alert if a significant percentage of tracked assets have stale prices.

        Args:
            quality_summary: Dict from ``ResearchService.run_stale_price_check``
                (which wraps result in ``{"success": True, "data": {...}}``)
                or the unwrapped data dict directly.
            threshold_pct: Percentage of tracked assets that triggers an alert
                (default 10.0).

        Returns:
            An ``Alert`` if the stale percentage exceeds the threshold, else ``None``.
        """
        # Unwrap success() envelope if present (from ResearchService.run_stale_price_check)
        if "success" in quality_summary and "data" in quality_summary:
            quality_summary = quality_summary["data"]

        stale_pct = float(quality_summary.get("threshold_pct", 0.0))
        if stale_pct <= threshold_pct:
            return None

        stale_assets = quality_summary.get("stale_assets", [])
        n_days = quality_summary.get("n_days", 3)

        return Alert(
            alert_id="stale_price_threshold",
            title=f"Stale prices detected on {len(stale_assets)} asset(s)",
            reason=(
                f"{stale_pct:.1f}% of tracked assets have not been updated in the last "
                f"{n_days} day(s). This may indicate a broken data source or ingestion pipeline."
            ),
            evidence={
                "stale_assets": stale_assets[:20],  # cap for readability
                "stale_count": len(stale_assets),
                "threshold_pct": stale_pct,
                "n_days": n_days,
            },
            severity="warning" if stale_pct < 50.0 else "critical",
            suggested_action=(
                "Review data source health and re-run ingestion for the listed assets. "
                "If the source is permanently broken, consider switching to an alternative fetcher."
            ),
            created_at=_now_iso(),
        )

    def check_open_windows(
        self,
        fund_statuses: List[Dict[str, Any]],
        as_of: date,
        window_days: int = DEFAULT_OPEN_WINDOW_DAYS,
    ) -> List[Alert]:
        """Alert for fund subscription/redemption window events.

        Designed to work with East Money ``fund_purchase_em()`` data as
        returned by ``FundFrictionService.get_fund_status()``.  Each dict
        should have:

        * ``fund_code`` (str)
        * ``fund_name`` (str)
        * ``can_buy`` (bool) — whether subscription is currently open
        * ``can_sell`` (bool) — whether redemption is currently open
        * ``next_open_date`` (date | str | None) — next open day if not daily

        Args:
            fund_statuses: List of fund status dicts.
            as_of: Reference date for computing days-to-next-open.
            window_days: Look-ahead window for ``next_open_date`` (default 30).

        Returns:
            List of ``Alert`` objects.
        """
        alerts: List[Alert] = []

        for fs in fund_statuses:
            code = str(fs.get("fund_code", "?"))
            name = str(fs.get("fund_name", code))
            label = f"{name}（{code}）"

            can_buy = fs.get("can_buy", True)
            can_sell = fs.get("can_sell", True)

            # ── Currently closed ─────────────────────────────────────────
            if not can_buy:
                alerts.append(Alert(
                    alert_id=_make_id("window_closed", code, "buy"),
                    title=f"「{label}」当前暂停申购",
                    reason=(
                        f"基金「{label}」当前申购状态为关闭，"
                        f"无法进行买入操作。"
                    ),
                    evidence={
                        "fund_code": code,
                        "fund_name": name,
                        "can_buy": False,
                        "can_sell": can_sell,
                    },
                    severity="warning",
                    suggested_action=(
                        f"该基金暂停申购期间无法买入。"
                        f"建议：1) 关注下一开放日；"
                        f"2) 若有配置需求，可寻找替代产品；"
                        f"3) 确认是否为临时性暂停或长期关闭。"
                    ),
                    created_at=_now_iso(),
                ))

            if not can_sell:
                alerts.append(Alert(
                    alert_id=_make_id("window_closed", code, "sell"),
                    title=f"「{label}」当前暂停赎回",
                    reason=(
                        f"基金「{label}」当前赎回状态为关闭，"
                        f"无法进行卖出操作。"
                    ),
                    evidence={
                        "fund_code": code,
                        "fund_name": name,
                        "can_buy": can_buy,
                        "can_sell": False,
                    },
                    severity="critical",
                    suggested_action=(
                        f"该基金暂停赎回期间无法卖出，存在流动性风险。"
                        f"建议：1) 确认暂停原因及预计恢复时间；"
                        f"2) 评估对整体流动性安排的影响；"
                        f"3) 如有紧急资金需求，寻找其他可变现资产。"
                    ),
                    created_at=_now_iso(),
                ))

            # ── Next open date approaching ────────────────────────────────
            next_open_raw = fs.get("next_open_date")
            if next_open_raw is not None:
                next_open = _parse_date(next_open_raw)
                if next_open is not None:
                    days_left = (next_open - as_of).days
                    if 0 <= days_left <= window_days:
                        alerts.append(Alert(
                            alert_id=_make_id("open_window", code, f"{days_left}d"),
                            title=f"「{label}」下一开放日临近",
                            reason=(
                                f"基金「{label}」下一开放日为 {next_open.isoformat()}，"
                                f"距今 {days_left} 天。"
                            ),
                            evidence={
                                "fund_code": code,
                                "fund_name": name,
                                "next_open_date": next_open.isoformat(),
                                "days_left": days_left,
                                "window_days": window_days,
                            },
                            severity="info" if days_left > 7 else "warning",
                            suggested_action=(
                                f"下一开放日临近，建议提前确认申购/赎回计划。"
                                f"如为定期开放基金，需在开放窗口内完成操作。"
                            ),
                            created_at=_now_iso(),
                        ))

        return alerts

    # ── Orchestrator ─────────────────────────────────────────────────────

    def run_all(self, **context: Any) -> List[Alert]:
        """Run all applicable checks from a single context dictionary.

        Each check is skipped silently when its required data is missing from
        *context*.

        Args:
            **context: Dictionary that may contain any of:
                * ``equity_curve`` or ``returns_summary`` (pd.DataFrame)
                * ``products`` or ``maturity_dates`` (List[Dict])
                * ``fx_exposure_report``
                * ``current_concentration`` or ``concentration_report`` (Dict)
                * ``previous_concentration`` (Dict)
                * ``fund_statuses`` (List[Dict])
                * ``as_of`` (date)
                * ``drawdown_threshold_pct`` (float)
                * ``maturity_within_days`` (int)
                * ``fx_loss_threshold_pct`` (float)
                * ``concentration_creep_threshold`` (float)
                * ``open_window_days`` (int)

        Returns:
            List of all triggered ``Alert`` objects.
        """
        alerts: List[Alert] = []

        # ── Drawdown ─────────────────────────────────────────────────────
        equity_curve = context.get("equity_curve") or context.get("returns_summary")
        if equity_curve is not None:
            # Handle if equity_curve is list/dict from JSON
            if isinstance(equity_curve, (list, dict)):
                equity_curve = pd.DataFrame(equity_curve)

            result = self.check_drawdown(
                equity_curve,
                threshold_pct=float(
                    context.get("drawdown_threshold_pct", self.DEFAULT_DRAWDOWN_THRESHOLD_PCT)
                ),
            )
            if result is not None:
                alerts.append(result)

        # ── Maturity ─────────────────────────────────────────────────────
        as_of = context.get("as_of") or date.today()
        products = context.get("products") or context.get("maturity_dates")
        if products:
            alerts.extend(
                self.check_maturity(
                    products,
                    as_of=_parse_date(as_of),
                    within_days=int(
                        context.get("maturity_within_days", self.DEFAULT_MATURITY_WINDOW_DAYS)
                    ),
                )
            )

        # ── FX loss ──────────────────────────────────────────────────────
        fx_report = context.get("fx_exposure_report")
        if fx_report is not None:
            result = self.check_fx_loss(
                fx_report,
                loss_threshold_pct=float(
                    context.get("fx_loss_threshold_pct", self.DEFAULT_FX_LOSS_THRESHOLD_PCT)
                ),
            )
            if result is not None:
                alerts.append(result)

        # ── Concentration creep ──────────────────────────────────────────
        cur_conc = context.get("current_concentration") or context.get("concentration_report")
        prev_conc = context.get("previous_concentration")
        if cur_conc is not None and prev_conc is not None:
            result = self.check_concentration_creep(
                cur_conc,
                prev_conc,
                increase_threshold=float(
                    context.get(
                        "concentration_creep_threshold",
                        self.DEFAULT_CONCENTRATION_CREEP_THRESHOLD,
                    )
                ),
            )
            if result is not None:
                alerts.append(result)

        # ── Stale prices ─────────────────────────────────────────────────
        quality_summary = context.get("quality_summary")
        if quality_summary is not None:
            result = self.check_stale_prices(
                quality_summary,
                threshold_pct=float(
                    context.get(
                        "stale_price_threshold_pct",
                        self.DEFAULT_STALE_PRICE_THRESHOLD_PCT,
                    )
                ),
            )
            if result is not None:
                alerts.append(result)

        # ── Open windows ─────────────────────────────────────────────────
        fund_statuses = context.get("fund_statuses")
        if fund_statuses:
            alerts.extend(
                self.check_open_windows(
                    fund_statuses,
                    as_of=_parse_date(as_of),
                    window_days=int(
                        context.get("open_window_days", self.DEFAULT_OPEN_WINDOW_DAYS)
                    ),
                )
            )

        return alerts


# ── Free functions ───────────────────────────────────────────────────────────


def _parse_date(raw: Any) -> Optional[date]:
    """Parse a date-like value into a ``date`` object.

    Handles ``date``, ``datetime``, ``pd.Timestamp``, and ISO-8601 strings.
    """
    if raw is None:
        return None
    if isinstance(raw, date):
        if isinstance(raw, datetime):
            return raw.date()
        return raw
    if isinstance(raw, pd.Timestamp):
        return raw.date()
    if isinstance(raw, str):
        raw_str = raw.strip()
        if not raw_str:
            return None
        try:
            return date.fromisoformat(raw_str)
        except (ValueError, TypeError):
            pass
        # Try pandas parse as fallback
        try:
            return pd.Timestamp(raw_str).date()
        except (ValueError, TypeError):
            return None
    return None
