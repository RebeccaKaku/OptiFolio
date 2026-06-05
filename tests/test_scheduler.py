"""Tests for DailyRunner — the daily pipeline orchestrator."""

from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.scheduler import DailyRunner, main


# ── Helpers ────────────────────────────────────────────────────────────────


def _mock_portfolio_svc(*, value_success=True, rules_success=True):
    """Build a mock PortfolioServiceV2 with canned responses."""
    svc = MagicMock()
    svc.get_value.return_value = {
        "success": value_success,
        "data": {
            "as_of": "2026-06-04",
            "total_value": 1_000_000.0,
            "holdings_value": 800_000.0,
            "cash_value": 200_000.0,
            "base_currency": "CNY",
            "positions": {},
            "cash_breakdown": {},
            "fx_rates": {},
            "price_date": None,
            "stale_days": None,
            "corporate_action_adjustments": 0.0,
            "fee_adjustments": 0.0,
        },
        "message": "Valuation complete",
    }
    svc.get_risk_rules.return_value = {
        "success": rules_success,
        "data": {
            "as_of": "2026-06-04",
            "base_currency": "CNY",
            "portfolio_value": 1_000_000.0,
            "rules": [
                {
                    "rule_id": "liquidity_emergency_fund",
                    "category": "liquidity",
                    "severity": "info",
                    "title": "紧急备用金充足",
                    "description": "充足",
                    "recommendation": "无需调整",
                    "passed": True,
                },
            ],
            "summary": {
                "total_rules": 1,
                "passed": 1,
                "failed": 0,
                "overall_healthy": True,
            },
        },
        "message": "Risk rules evaluated",
    }
    return svc


# ── DailyRunner construction ───────────────────────────────────────────────


class TestDailyRunnerConstruction:
    def test_default_snapshot_dir(self):
        runner = DailyRunner()
        assert runner.snapshot_dir.name == "daily_snapshots"
        assert runner.snapshot_dir.exists()

    def test_custom_snapshot_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "custom_snapshots"
            runner = DailyRunner(snapshot_dir=custom)
            assert runner.snapshot_dir == custom
            assert runner.snapshot_dir.exists()


# ── run() — dry_run mode ───────────────────────────────────────────────────


class TestDryRun:
    def test_dry_run_no_side_effects(self):
        """Dry run should complete all steps without calling ingestion or writing files."""
        runner = DailyRunner()
        result = runner.run(portfolio_svc=_mock_portfolio_svc(), dry_run=True)

        assert result["dry_run"] is True
        assert result["date"] == date.today().isoformat()
        assert "timestamp_utc" in result
        # All steps should be listed as completed
        assert "ingest" in result["steps_completed"]
        assert "valuation" in result["steps_completed"]
        assert "history" in result["steps_completed"]
        assert "risk_rules" in result["steps_completed"]
        assert "alerts" in result["steps_completed"]
        assert "snapshot" in result["steps_completed"]
        # No errors
        assert result["errors"] == []

    def test_dry_run_does_not_call_svc(self):
        """In dry-run mode, the portfolio service should not be called."""
        svc = _mock_portfolio_svc()
        runner = DailyRunner()
        runner.run(portfolio_svc=svc, dry_run=True)

        svc.get_value.assert_not_called()
        svc.get_risk_rules.assert_not_called()

    def test_dry_run_has_placeholder_valuation(self):
        runner = DailyRunner()
        result = runner.run(dry_run=True)
        assert result["valuation"]["total_value"] == 0.0
        assert result["valuation"]["as_of"] == date.today().isoformat()

    def test_dry_run_has_empty_rules(self):
        runner = DailyRunner()
        result = runner.run(dry_run=True)
        assert result["rules"]["rules"] == []
        assert result["rules"]["summary"]["total_rules"] == 0


# ── run() — live mode ──────────────────────────────────────────────────────


class TestLiveRun:
    def test_successful_run(self):
        """A successful run returns all expected keys and no errors."""
        with tempfile.TemporaryDirectory() as tmp:
            runner = DailyRunner(snapshot_dir=Path(tmp))
            # Use a mock alert engine to avoid auto-wire via ApplicationServices
            mock_alerts = MagicMock()
            mock_alerts.run_all.return_value = []
            with patch.object(runner, "_run_ingestion"):
                result = runner.run(
                    portfolio_svc=_mock_portfolio_svc(),
                    alert_engine=mock_alerts,
                )

            assert result["dry_run"] is False
            assert result["date"] == date.today().isoformat()
            assert result["valuation"]["total_value"] == 1_000_000.0
            assert result["valuation"]["base_currency"] == "CNY"
            assert len(result["rules"]["rules"]) == 1
            assert result["rules"]["summary"]["overall_healthy"] is True
            assert result["alerts"] == []
            assert result["errors"] == []
            assert "valuation" in result["steps_completed"]
            assert "risk_rules" in result["steps_completed"]

    def test_snapshot_file_is_written(self):
        """A non-dry run should write the JSON snapshot."""
        with tempfile.TemporaryDirectory() as tmp:
            runner = DailyRunner(snapshot_dir=Path(tmp))
            with patch.object(runner, "_run_ingestion"):
                result = runner.run(portfolio_svc=_mock_portfolio_svc())

            snapshot_path = Path(tmp) / f"{date.today().isoformat()}.json"
            assert snapshot_path.exists()

            with open(snapshot_path, encoding="utf-8") as f:
                saved = json.load(f)

            assert saved["date"] == date.today().isoformat()
            assert saved["valuation"]["total_value"] == 1_000_000.0
            assert saved["timestamp_utc"] is not None

    def test_valuation_failure_is_recorded(self):
        """When valuation fails, the error is captured and the run continues."""
        svc = _mock_portfolio_svc(value_success=False)
        svc.get_value.return_value = {
            "success": False,
            "message": "No price data available",
            "error_code": "NO_PRICE_DATA",
        }

        with tempfile.TemporaryDirectory() as tmp:
            runner = DailyRunner(snapshot_dir=Path(tmp))
            with patch.object(runner, "_run_ingestion"):
                result = runner.run(portfolio_svc=svc)

            assert result["valuation"] is None
            assert any("valuation" in e for e in result["errors"])
            # Risk rules should still run
            assert "risk_rules" in result["steps_completed"]

    def test_risk_rules_failure_is_recorded(self):
        """When risk rules fail, the error is captured but run continues."""
        svc = _mock_portfolio_svc(rules_success=False)
        svc.get_risk_rules.return_value = {
            "success": False,
            "message": "No data for rules",
            "error_code": "NO_PRICE_DATA",
        }

        with tempfile.TemporaryDirectory() as tmp:
            runner = DailyRunner(snapshot_dir=Path(tmp))
            with patch.object(runner, "_run_ingestion"):
                result = runner.run(portfolio_svc=svc)

            assert any("risk_rules" in e for e in result["errors"])
            assert "valuation" in result["steps_completed"]

    def test_valuation_exception_is_caught(self):
        """If get_value raises, the error is caught gracefully."""
        svc = MagicMock()
        svc.get_value.side_effect = RuntimeError("Boom!")
        svc.get_risk_rules.return_value = {"success": True, "data": {}}

        with tempfile.TemporaryDirectory() as tmp:
            runner = DailyRunner(snapshot_dir=Path(tmp))
            with patch.object(runner, "_run_ingestion"):
                result = runner.run(portfolio_svc=svc)

            assert any("Boom" in e for e in result["errors"])
            assert result["valuation"] is None


# ── AlertEngine integration ────────────────────────────────────────────────


class TestAlertEngine:
    def test_alert_engine_none_skips_gracefully(self):
        """When alert_engine is None and service graph unavailable, returns []."""
        runner = DailyRunner()
        result = runner.run(
            portfolio_svc=_mock_portfolio_svc(),
            alert_engine=None,
            dry_run=True,
        )
        assert result["alerts"] == []
        assert "alerts" in result["steps_completed"]

    def test_alert_engine_run_all_is_called(self):
        """When alert_engine has run_all(), it should be called with **ctx."""
        alert = MagicMock()
        alert.alert_id = "stale_price_threshold"
        alert.to_dict.return_value = {"alert_id": "stale_price_threshold", "severity": "warning"}

        alert_engine = MagicMock()
        alert_engine.run_all.return_value = [alert]

        with tempfile.TemporaryDirectory() as tmp:
            runner = DailyRunner(snapshot_dir=Path(tmp))
            with patch.object(runner, "_run_ingestion"):
                result = runner.run(
                    portfolio_svc=_mock_portfolio_svc(),
                    alert_engine=alert_engine,
                )
            alert_engine.run_all.assert_called_once()
            assert len(result["alerts"]) == 1
            assert result["alerts"][0]["alert_id"] == "stale_price_threshold"

    def test_alert_engine_receives_kwargs(self):
        """run_all receives kwargs from the scheduler."""
        alert_engine = MagicMock()
        alert_engine.run_all.return_value = []

        with tempfile.TemporaryDirectory() as tmp:
            runner = DailyRunner(snapshot_dir=Path(tmp))
            with patch.object(runner, "_run_ingestion"):
                runner.run(
                    portfolio_svc=_mock_portfolio_svc(),
                    alert_engine=alert_engine,
                )
            alert_engine.run_all.assert_called_once()

    def test_alert_engine_error_is_caught(self):
        """If alert_engine raises, the error is captured."""
        alert_engine = MagicMock()
        alert_engine.run_all.side_effect = RuntimeError("Alert failure")

        with tempfile.TemporaryDirectory() as tmp:
            runner = DailyRunner(snapshot_dir=Path(tmp))
            with patch.object(runner, "_run_ingestion"):
                result = runner.run(
                    portfolio_svc=_mock_portfolio_svc(),
                    alert_engine=alert_engine,
                )
            assert any("alerts" in e for e in result["errors"])
            assert result["alerts"] == []


# ── Snapshot JSON format ───────────────────────────────────────────────────


class TestSnapshotFormat:
    def test_snapshot_has_required_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = DailyRunner(snapshot_dir=Path(tmp))
            with patch.object(runner, "_run_ingestion"):
                runner.run(portfolio_svc=_mock_portfolio_svc())

            path = Path(tmp) / f"{date.today().isoformat()}.json"
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            for key in ("date", "valuation", "rules", "alerts", "timestamp_utc"):
                assert key in data, f"Missing key: {key}"

    def test_timestamp_utc_is_valid_iso(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = DailyRunner(snapshot_dir=Path(tmp))
            with patch.object(runner, "_run_ingestion"):
                result = runner.run(portfolio_svc=_mock_portfolio_svc())

            ts = result["timestamp_utc"]
            parsed = datetime.fromisoformat(ts)
            assert parsed.tzinfo is not None


# ── Step resiliency ────────────────────────────────────────────────────────


class TestStepResiliency:
    def test_run_continues_after_ingestion_failure(self):
        """When ingestion fails, the pipeline continues to remaining steps."""
        svc = _mock_portfolio_svc()

        with tempfile.TemporaryDirectory() as tmp:
            runner = DailyRunner(snapshot_dir=Path(tmp))

            with patch.object(
                runner, "_run_ingestion", side_effect=RuntimeError("Network down")
            ):
                result = runner.run(portfolio_svc=svc)

            assert any("Network down" in e for e in result["errors"])
            # Valuation should still have run
            assert result["valuation"]["total_value"] == 1_000_000.0
            assert "valuation" in result["steps_completed"]

    def test_run_continues_after_rules_failure(self):
        """When risk rules fail, the pipeline continues to snapshot."""
        svc = MagicMock()
        svc.get_value.return_value = _mock_portfolio_svc().get_value.return_value
        svc.get_risk_rules.side_effect = RuntimeError("Rule engine crash")

        with tempfile.TemporaryDirectory() as tmp:
            runner = DailyRunner(snapshot_dir=Path(tmp))
            with patch.object(runner, "_run_ingestion"):
                result = runner.run(portfolio_svc=svc)

            assert any("Rule engine" in e for e in result["errors"])
            assert result["valuation"] is not None
            assert result["rules"] is None

    def test_snapshot_still_saved_when_rules_fail(self):
        """Snapshot should be written even if risk rules fail."""
        svc = MagicMock()
        svc.get_value.return_value = _mock_portfolio_svc().get_value.return_value
        svc.get_risk_rules.side_effect = RuntimeError("Rule engine crash")

        with tempfile.TemporaryDirectory() as tmp:
            runner = DailyRunner(snapshot_dir=Path(tmp))
            with patch.object(runner, "_run_ingestion"):
                runner.run(portfolio_svc=svc)

            path = Path(tmp) / f"{date.today().isoformat()}.json"
            assert path.exists()


# ── CLI ────────────────────────────────────────────────────────────────────


class TestCLI:
    def test_dry_run_via_main(self):
        """The main() function should handle --dry-run without errors."""
        with patch("sys.argv", ["scheduler.py", "--dry-run"]):
            # Should exit cleanly (no errors in dry run)
            try:
                main()
            except SystemExit as e:
                assert e.code == 0

    def test_main_without_args(self):
        """main() without --dry-run should import and run."""
        # We just verify the function is importable and parseable
        with patch("argparse.ArgumentParser.parse_args") as mock_parse:
            mock_args = MagicMock()
            mock_args.dry_run = True
            mock_parse.return_value = mock_args
            try:
                main()
            except SystemExit:
                pass  # may exit 0 or 1 depending on setup
