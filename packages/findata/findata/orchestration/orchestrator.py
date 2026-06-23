"""Orchestrator — the COMMAND department.

Decides WHAT to fetch and WHEN, then dispatches tasks to the fetcher
department and submits results to the storage department.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .cadence import get_cadence, is_update_due
from .fallback import get_fallback_chain
from .rate_limiter import PROVIDER_LIMITS
from optifolio_contracts.identifiers import normalize_instrument_id

_log = logging.getLogger(__name__)


@dataclass(order=True)
class FetchTask:
    """A single fetch job produced by the scheduler.

    Attributes:
        asset_id: Asset identifier (e.g. ``"AAPL"``, ``"000001"``).
        asset_type: Registry key for the fetcher (e.g. ``"us_equity"``).
        provider: Preferred data source label.
        start_date: ISO-format start date for the fetch window.
        end_date: ISO-format end date for the fetch window.
        priority: Higher values are dispatched first.
    """

    asset_id: str
    asset_type: str
    provider: str
    start_date: str
    end_date: str
    priority: int = 0


class Orchestrator:
    """Scheduler + dispatcher for all known asset types.

    Usage::

        orch = Orchestrator()
        tasks = orch.schedule()           # all assets due for refresh
        results = orch.dispatch(tasks)    # fetch → quality-gate → store
        # or one-liner:
        results = orch.full_scan()
    """

    def __init__(self, store=None) -> None:
        # Lazy import — avoids circular dependency at module level
        from findata.store import CanonicalStore

        self._store = store or CanonicalStore()
        self._task_log: list[dict] = []

    # ── Public API ──────────────────────────────────────────────────────

    def schedule(
        self,
        asset_ids: Optional[List[str]] = None,
        asset_types: Optional[Dict[str, str]] = None,
    ) -> List[FetchTask]:
        """Generate fetch tasks for assets that are due for refresh.

        Args:
            asset_ids: Specific assets to check.  ``None`` means *all*
                known assets in storage.
            asset_types: Mapping of ``asset_id → asset_type``.  Assets
                not in this dict default to ``"unknown"``.

        Returns:
            Tasks sorted by descending priority.
        """
        tasks: list[FetchTask] = []
        now = datetime.now(timezone.utc)

        if asset_ids is None:
            asset_ids = self._store.list_assets()

        if asset_types is None:
            asset_types = self._load_asset_types()

        for aid in asset_ids:
            atype = asset_types.get(aid, "unknown")

            # Skip if not due
            if not is_update_due(atype, self._last_update(aid), now):
                continue

            # Get provider from fallback chain (primary = first entry)
            providers = get_fallback_chain(atype)
            if not providers:
                continue

            # Filter out "cached" — that is not a real provider
            real_providers = [p for p in providers if p != "cached"]
            if not real_providers:
                continue  # No real providers → nothing to fetch

            primary = real_providers[0]

            tasks.append(
                FetchTask(
                    asset_id=aid,
                    asset_type=atype,
                    provider=primary,
                    start_date=self._determine_start_date(aid),
                    end_date=now.strftime("%Y-%m-%d"),
                    priority=self._priority(atype),
                )
            )

        return sorted(tasks, key=lambda t: -t.priority)

    def dispatch(self, tasks: List[FetchTask]) -> Dict[str, object]:
        """Execute *tasks* with rate limiting and fallback chains.

        Each task is tried against its fallback chain.  The first
        provider that returns a successful, quality-passing result wins.

        Returns:
            ``{asset_id: FetchResult}`` for every asset that was
            successfully fetched and stored.
        """
        from findata.adapters import get_fetcher
        from findata.calendars import get_timezone

        results: dict[str, object] = {}

        for task in tasks:
            # Rate limit before each task
            limiter = PROVIDER_LIMITS.get(task.provider)
            if limiter is not None:
                limiter.wait()

            fetcher = get_fetcher(task.asset_type)
            if fetcher is None:
                self._log(task, "no_fetcher")
                continue

            # Try each provider in the fallback chain
            chain = get_fallback_chain(task.asset_type)
            succeeded = False
            for provider in chain:
                if provider == "cached":
                    # Fallback: accept whatever is already in storage
                    self._log(task, "cached_fallback")
                    succeeded = True
                    break

                result = fetcher.fetch(
                    task.asset_id, task.start_date, task.end_date
                )
                if not result.success or result.data is None:
                    # Provider failed — try next in chain
                    continue

                # Submit to storage department through quality gate
                tz = get_timezone(task.asset_type)
                report = self._store.accept(
                    result.data,
                    asset_id=task.asset_id,
                    source=result.provider,
                    timezone=tz,
                )
                if report.passed:
                    results[task.asset_id] = result
                    succeeded = True
                    break
                # Quality rejection — try next provider
                self._log(task, f"quality_rejected_by_{provider}")

            if not succeeded:
                self._log(task, "all_failed")

        return results

    def full_scan(self) -> Dict[str, object]:
        """Schedule and dispatch all known assets in one call."""
        tasks = self.schedule()
        return self.dispatch(tasks)

    # ── Task log ────────────────────────────────────────────────────────

    def task_log(self) -> list[dict]:
        """Return a copy of the internal task log."""
        return list(self._task_log)

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _load_asset_types() -> Dict[str, str]:
        """Load ``symbol → asset_type`` mapping from the asset registry."""
        import yaml
        registry_path = Path("config/asset_registry.yaml")
        asset_types: dict[str, str] = {}
        try:
            if registry_path.exists():
                with open(registry_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                if config and "assets" in config:
                    for entry in config["assets"]:
                        symbol = entry.get("symbol")
                        atype = entry.get("asset_type")
                        if symbol and atype:
                            asset_types[str(symbol)] = str(atype)
        except Exception:
            _log.warning("Failed to load asset registry for type mapping", exc_info=True)
        return asset_types

    def _last_update(self, asset_id: str) -> Optional[datetime]:
        """Return the timestamp of the most recent stored observation for
        *asset_id*, or ``None`` if unknown."""
        try:
            canonical = normalize_instrument_id(asset_id)
            report = self._store.missing_report([canonical])
            if report is not None and not report.empty:
                # If any observations exist the asset has been updated
                if report["observations"].sum() > 0:
                    # Use the missing report to estimate last update:
                    # the most recent date in get_prices is the last update
                    prices = self._store.get_prices([canonical])
                    if prices is not None and not prices.empty and canonical in prices.columns:
                        valid = prices[canonical].dropna()
                        if not valid.empty:
                            return valid.index[-1].to_pydatetime()
        except Exception:
            pass
        return None

    def _determine_start_date(self, asset_id: str) -> str:
        """Compute the start date for an incremental fetch.

        If the asset already has stored data, the fetch window starts
        from the last stored date.  Otherwise a full-history window is
        used.
        """
        try:
            canonical = normalize_instrument_id(asset_id)
            existing = self._store.get_prices([canonical])
            if existing is not None and not existing.empty and canonical in existing.columns:
                last_date = existing.index[-1]
                return last_date.strftime("%Y-%m-%d")
        except Exception:
            pass
        return "2020-01-01"

    @staticmethod
    def _priority(asset_type: str) -> int:
        """Return a dispatch priority for *asset_type* (higher = sooner)."""
        return {
            "forex": 10,
            "currency": 10,
            "crypto": 9,
            "us_equity": 5,
            "cn_stock": 5,
            "cn_stock_sh": 5,
            "cn_stock_sz": 5,
            "cn_fund": 3,
            "cn_fund_open": 3,
            "cn_fund_etf": 3,
            "cn_fund_money": 3,
            "bank_wm_boc": 1,
            "bank_wm_bosc": 1,
            "bank_wm_icbc": 1,
        }.get(asset_type, 0)

    def _log(self, task: FetchTask, status: str) -> None:
        """Append an entry to the internal task log."""
        self._task_log.append(
            {
                "asset_id": task.asset_id,
                "asset_type": task.asset_type,
                "status": status,
                "time": datetime.now(timezone.utc).isoformat(),
            }
        )
