#!/usr/bin/env python
"""Daily scheduler for OptiFolio — chains ingestion, valuation, risk checks, and snapshot.

Usage::

    python tools/scheduler.py              # run once
    python tools/scheduler.py --dry-run    # show what would happen

The ``DailyRunner`` class can also be used programmatically::

    from tools.scheduler import DailyRunner
    from src.services.portfolio_service_v2 import PortfolioServiceV2

    svc = PortfolioServiceV2()
    result = DailyRunner().run(svc)
    print(result["valuation"]["total_value"])
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import sys
from argparse import Namespace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.paths import PROJECT_ROOT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("scheduler")


# ── DailyRunner ───────────────────────────────────────────────────────────────


class DailyRunner:
    """Orchestrates the daily portfolio pipeline.

    Chains price ingestion, portfolio valuation, history recording,
    risk rule evaluation, alert checks, and snapshot storage into a
    single daily workflow.

    Parameters:
        snapshot_dir: Directory for daily snapshot JSON files.
            Defaults to ``local/daily_snapshots/``.
    """

    def __init__(self, snapshot_dir: Optional[Path] = None):
        self.snapshot_dir = snapshot_dir or (PROJECT_ROOT / "local" / "daily_snapshots")
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        portfolio_svc: Any = None,
        history_tracker: Any = None,
        rule_engine: Any = None,
        alert_engine: Any = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Execute the full daily pipeline.

        Parameters:
            portfolio_svc:
                A ``PortfolioServiceV2`` instance.  Created automatically
                when ``None``.
            history_tracker:
                Reserved.  History recording is handled inside
                ``portfolio_svc.get_value()``.
            rule_engine:
                Reserved.  Risk rules are evaluated via
                ``portfolio_svc.get_risk_rules()``.
            alert_engine:
                Optional alert engine instance.  When ``None``, the alert
                step logs an informational message and returns an empty
                alerts list.
            dry_run:
                When ``True``, logs each step without executing side
                effects (no ingestion, no file writes).

        Returns:
            A summary dict with keys:

            * ``date`` — ISO-format date string
            * ``valuation`` — valuation result dict (or ``None`` on failure)
            * ``rules`` — risk rules result dict (or ``None`` on failure)
            * ``alerts`` — list of triggered alert dicts
            * ``timestamp_utc`` — ISO-format UTC timestamp
            * ``steps_completed`` — list of step names that ran
            * ``errors`` — list of error messages (empty on success)
            * ``dry_run`` — whether this was a dry run
        """
        today = date.today()
        now_utc = datetime.now(timezone.utc).isoformat()
        steps_completed: List[str] = []
        errors: List[str] = []

        logger.info("=" * 60)
        logger.info("OptiFolio Daily Run — %s", today.isoformat())
        if dry_run:
            logger.info("DRY RUN — no side effects will be performed")
        logger.info("=" * 60)

        # ── Step 1: Ingest latest prices ──────────────────────────────
        logger.info("[Step 1/5] Ingesting latest prices …")
        if dry_run:
            logger.info("  Would call ingest_portfolio_prices.main_async() for all holdings")
            steps_completed.append("ingest")
        else:
            try:
                self._run_ingestion()
                steps_completed.append("ingest")
            except Exception as exc:
                logger.warning("  Price ingestion failed (continuing): %s", exc)
                errors.append(f"ingest: {exc}")

        # ── Step 2: Value portfolio ────────────────────────────────────
        logger.info("[Step 2/5] Valuing portfolio as of %s …", today.isoformat())
        valuation_data: Optional[Dict[str, Any]] = None

        if portfolio_svc is None:
            from src.services.application import get_application_services
            portfolio_svc = get_application_services().portfolio_v2

        if dry_run:
            logger.info("  Would call portfolio_svc.get_value(as_of=%s)", today.isoformat())
            valuation_data = {
                "as_of": today.isoformat(),
                "total_value": 0.0,
                "holdings_value": 0.0,
                "cash_value": 0.0,
                "base_currency": "CNY",
                "positions": {},
                "cash_breakdown": {},
                "fx_rates": {},
                "price_date": None,
                "stale_days": None,
                "corporate_action_adjustments": 0.0,
                "fee_adjustments": 0.0,
            }
            steps_completed.append("valuation")
        else:
            try:
                val_result = portfolio_svc.get_value(as_of=today)
                if val_result.get("success"):
                    valuation_data = val_result["data"]
                    logger.info(
                        "  Portfolio value: %s %,.2f",
                        valuation_data.get("base_currency", ""),
                        valuation_data.get("total_value", 0.0),
                    )
                else:
                    logger.error("  Valuation failed: %s", val_result.get("message"))
                    errors.append(f"valuation: {val_result.get('message')}")
                steps_completed.append("valuation")
            except Exception as exc:
                logger.error("  Valuation error: %s", exc)
                errors.append(f"valuation: {exc}")

        # ── Step 3: Record history ─────────────────────────────────────
        # portfolio_svc.get_value() calls history.record() internally,
        # so this step is already done.
        logger.info("[Step 3/5] History recorded (handled by get_value)")
        steps_completed.append("history")

        # ── Step 4: Run risk rules ─────────────────────────────────────
        logger.info("[Step 4/6] Running risk rules …")
        rules_data: Optional[Dict[str, Any]] = None

        if dry_run:
            logger.info("  Would call portfolio_svc.get_risk_rules()")
            rules_data = {
                "as_of": today.isoformat(),
                "base_currency": "CNY",
                "portfolio_value": 0.0,
                "rules": [],
                "summary": {"total_rules": 0, "passed": 0, "failed": 0, "overall_healthy": True},
            }
            steps_completed.append("risk_rules")
        else:
            try:
                risk_result = portfolio_svc.get_risk_rules(as_of=today)
                if risk_result.get("success"):
                    rules_data = risk_result["data"]
                    summary = rules_data.get("summary", {})
                    logger.info(
                        "  Rules: %s passed, %s failed (total %s)",
                        summary.get("passed", 0),
                        summary.get("failed", 0),
                        summary.get("total_rules", 0),
                    )
                    if not summary.get("overall_healthy", True):
                        logger.warning(
                            "  Risk violations: %s warning(s), %s critical",
                            summary.get("warning_count", 0),
                            summary.get("critical_count", 0),
                        )
                else:
                    logger.warning("  Risk rules failed: %s", risk_result.get("message"))
                    errors.append(f"risk_rules: {risk_result.get('message')}")
                steps_completed.append("risk_rules")
            except Exception as exc:
                logger.warning("  Risk rule error (continuing): %s", exc)
                errors.append(f"risk_rules: {exc}")

        # ── Step 5: Data quality checks ────────────────────────────────
        logger.info("[Step 5/6] Running data quality checks …")
        quality_data: Optional[Dict[str, Any]] = None

        if dry_run:
            logger.info("  Would run stale-price check (n_days=3)")
            quality_data = {"issues_found": 0, "stale_assets": [], "threshold_pct": 0.0}
            steps_completed.append("data_quality")
        else:
            try:
                from src.services.application import get_application_services

                dq_result = get_application_services().research.run_stale_price_check(n_days=3)
                if dq_result.get("success"):
                    quality_data = dq_result["data"]
                    stale = quality_data.get("issues_found", 0)
                    pct = quality_data.get("threshold_pct", 0.0)
                    logger.info("  Data quality: %s stale asset(s) (%.1f%%)", stale, pct)
                    if pct > 10.0:
                        logger.warning(
                            "  >10%% of tracked assets are stale — consider reviewing data sources"
                        )
                else:
                    logger.warning("  Data quality check failed: %s", dq_result.get("message"))
                    errors.append(f"data_quality: {dq_result.get('message')}")
                steps_completed.append("data_quality")
            except Exception as exc:
                logger.warning("  Data quality error (continuing): %s", exc)
                errors.append(f"data_quality: {exc}")

        # ── Step 6: Check alerts ───────────────────────────────────────
        logger.info("[Step 6/6] Checking alerts …")
        alerts_data: List[Dict[str, Any]] = []

        if alert_engine is None:
            from src.services.application import get_application_services
            alert_engine = get_application_services().alerts

        if alert_engine is not None:
            if dry_run:
                logger.info("  Would run alert_engine checks")
            else:
                try:
                    # Build context for AlertEngine.run_all()
                    alert_ctx: Dict[str, Any] = {}
                    if quality_data is not None:
                        alert_ctx["quality_summary"] = quality_data

                    # Priority: run() (legacy / mock) > run_all() (AlertEngine) > check_all()
                    if hasattr(alert_engine, "run") and callable(getattr(alert_engine, "run", None)):
                        alerts_data = alert_engine.run()
                    elif hasattr(alert_engine, "run_all") and callable(getattr(alert_engine, "run_all", None)):
                        from src.analytics.alerts import AlertEngine
                        if isinstance(alert_engine, AlertEngine):
                            raw_alerts = alert_engine.run_all(**alert_ctx)
                            alerts_data = [a.to_dict() for a in raw_alerts]
                        else:
                            alerts_data = alert_engine.run_all(alert_ctx)
                    elif hasattr(alert_engine, "check_all") and callable(getattr(alert_engine, "check_all", None)):
                        alerts_data = alert_engine.check_all()
                    else:
                        logger.info(
                            "  AlertEngine has no run()/run_all()/check_all() method — skipped"
                        )
                except Exception as exc:
                    logger.warning("  Alert check error (continuing): %s", exc)
                    errors.append(f"alerts: {exc}")
        else:
            logger.info("  AlertEngine not available — skipping alert checks")
        steps_completed.append("alerts")

        # ── Step 6: Save daily snapshot ────────────────────────────────
        logger.info("[Snapshot] Saving daily snapshot …")
        snapshot = {
            "date": today.isoformat(),
            "valuation": valuation_data,
            "rules": rules_data,
            "alerts": alerts_data,
            "timestamp_utc": now_utc,
        }

        if not dry_run:
            try:
                self._save_snapshot(today, snapshot)
                steps_completed.append("snapshot")
            except Exception as exc:
                logger.error("  Snapshot save failed: %s", exc)
                errors.append(f"snapshot: {exc}")
        else:
            logger.info("  Would save to %s", self._snapshot_path(today))
            steps_completed.append("snapshot")

        # ── Summary ────────────────────────────────────────────────────
        logger.info("=" * 60)
        logger.info(
            "Daily run complete — %d step(s): %s",
            len(steps_completed),
            ", ".join(steps_completed),
        )
        if errors:
            logger.warning("  %d error(s): %s", len(errors), errors)

        # Step 7: Save portfolio ledger
        try:
            from FinData.store.portfolio_ledger import PortfolioLedger, PortfolioLedgerStore
            store = PortfolioLedgerStore()
            entries = []
            for symbol, pos in (valuation_data or {}).get("positions", {}).items():
                entries.append(PortfolioLedger(
                    account_id="default",
                    asset_id=symbol,
                    quantity=pos.get("quantity", 0),
                    cost_basis=0,
                    currency=pos.get("currency", "CNY"),
                    as_of=today,
                ))
            if entries:
                store.save_entries(entries)
                steps_completed.append("ledger")
                logger.info(f"Portfolio ledger saved: {today}")
        except Exception as exc:
            errors.append(f"ledger: {exc}")
            logger.warning(f"Portfolio ledger skipped: {exc}")

        return {
            "date": today.isoformat(),
            "valuation": valuation_data,
            "rules": rules_data,
            "alerts": alerts_data,
            "timestamp_utc": now_utc,
            "steps_completed": steps_completed,
            "errors": errors,
            "dry_run": dry_run,
        }

    # ── internal helpers ────────────────────────────────────────────────────

    def _run_ingestion(self) -> None:
        """Import and call ``ingest_portfolio_prices.main_async()``.

        Uses ``importlib`` so we can load the sibling module even though
        the ``tools/`` directory is not a package (no ``__init__.py``).
        """
        ingest_path = Path(__file__).resolve().parent / "ingest_portfolio_prices.py"
        spec = importlib.util.spec_from_file_location(
            "ingest_portfolio_prices", ingest_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {ingest_path}")

        mod = importlib.util.module_from_spec(spec)
        sys.modules["ingest_portfolio_prices"] = mod
        spec.loader.exec_module(mod)

        # For daily updates one year of history catches gaps without
        # re-downloading the full multi-year archive every day.
        ingest_args = Namespace(symbols=None, years=1, dry_run=False)
        asyncio.run(mod.main_async(ingest_args))

    def _snapshot_path(self, snapshot_date: date) -> Path:
        """Return the JSON file path for a given date."""
        return self.snapshot_dir / f"{snapshot_date.isoformat()}.json"

    def _save_snapshot(self, snapshot_date: date, data: Dict[str, Any]) -> None:
        """Write the daily snapshot as pretty-printed JSON."""
        path = self._snapshot_path(snapshot_date)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.info("  Snapshot saved: %s", path)


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OptiFolio Daily Scheduler — run the daily portfolio pipeline"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without executing any side effects",
    )
    args = parser.parse_args()

    runner = DailyRunner()
    result = runner.run(dry_run=args.dry_run)

    if result.get("errors"):
        logger.warning("Completed with %d error(s)", len(result["errors"]))
        sys.exit(1)

    logger.info("Daily run successful")


if __name__ == "__main__":
    main()
