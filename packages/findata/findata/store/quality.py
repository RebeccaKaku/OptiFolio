"""QualityGate — the data quality guardian for the FinData storage department.

Every incoming DataFrame is inspected against 8 quality checks before
it is allowed into canonical storage. Rejections are fatal; flags warn
but do not block.

Additionally, the module provides ``QualityIssueStore`` for persisting
data-quality issues (e.g. stale prices) to a canonical parquet file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional

import pandas as pd

_log = logging.getLogger(__name__)

from .schemas import _COLUMN_ALIASES, _canonical_column_name


def _default_quality_path() -> Path:
    """Default path for quality issues — under findata data dir."""
    from findata.config import get_default_config
    return get_default_config().data_dir / "metadata" / "data_quality_issues.parquet"


# ── Ingestion quality report (per-batch, in-memory) ──────────────────────────


@dataclass
class QualityReport:
    """Result of a QualityGate inspection.

    Attributes:
        passed: True if all fatal checks passed.
        checks: List of individual check results with name, passed, and detail.
        reject_reasons: Human-readable reasons for rejection (fatal).
        flags: Human-readable warnings (non-fatal).
    """

    passed: bool
    checks: List[dict] = field(default_factory=list)
    reject_reasons: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)


# ── Persistent issue store (cross-run, parquet-backed) ───────────────────────


class QualityIssueStore:
    """Handles persistence of data-quality issues to a canonical parquet file.

    Typical workflow::

        issues = gate.stale_price_check(n_days=3)
        store = QualityIssueStore()
        store.append(issues)
        df = store.load()          # read back for API / alerting
    """

    def __init__(self, file_path: Optional[Path] = None) -> None:
        self.file_path = file_path or _default_quality_path()

    def append(self, issues: pd.DataFrame) -> None:
        """Merge *issues* into the existing store, deduplicating by
        ``(asset_id, issue_type, date)``.
        """
        if issues.empty:
            return

        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        existing = self.load()
        combined = pd.concat([existing, issues], ignore_index=True)

        # Deduplicate: keep the latest record per (asset_id, issue_type, date)
        if "timestamp" in combined.columns:
            combined["timestamp"] = pd.to_datetime(combined["timestamp"], errors="coerce")
            combined = combined.sort_values("timestamp")

        dedup_cols = [c for c in ("asset_id", "issue_type", "date") if c in combined.columns]
        if dedup_cols:
            combined = combined.drop_duplicates(subset=dedup_cols, keep="last")

        combined.to_parquet(self.file_path, compression="snappy", index=False)
        _log.info("QualityIssueStore: persisted %d issue(s) to %s", len(combined), self.file_path)

    def load(self) -> pd.DataFrame:
        """Read all persisted issues."""
        if not self.file_path.exists():
            return pd.DataFrame(
                columns=["asset_id", "issue_type", "details", "timestamp", "date"]
            )
        return pd.read_parquet(self.file_path)

    def clear(self) -> None:
        """Remove the store file (useful in tests)."""
        if self.file_path.exists():
            self.file_path.unlink()


# ── Quality gate (inspection + stale-price monitoring) ───────────────────────


class QualityGate:
    """Multi-check data quality inspector.

    The gate runs nine checks on every incoming DataFrame:
    1. Non-empty          → REJECT on empty
    2. Price column       → REJECT if no close/adj_close column
    3. Row count          → FLAG if long date span but very few rows
    4. NaN proportion     → REJECT if close column is >50% NaN
    5. Positive prices    → REJECT if close <= 0 found
    6. Time reversal      → REJECT if new data is older than existing
    7. Price spikes       → FLAG if any daily change exceeds 50%
    8. Flat trading days  → FLAG if O=H=L=C and volume=0 (suspicious non-trading day)
    9. Duplicate data     → REJECT if identical to already-stored data

    Additionally, ``stale_price_check`` monitors the repository for
    assets whose latest price is older than a given threshold.

    All rejections are FATAL — data will NOT be stored.
    Flags are warnings — data is stored but flagged.
    """

    def __init__(self, repository: Optional[Any] = None) -> None:
        """
        Args:
            repository: A ``MarketDataRepository`` instance (or compatible
                object with ``price_path``, ``fund_path``, ``wealth_path``
                and a ``_query`` method).  When ``None``, a default
                repository is created.
        """
        if repository is None:
            from findata.store import MarketDataRepository

            repository = MarketDataRepository()
        self.repository = repository

    # ── Ingestion checks ──────────────────────────────────────────────────

    def inspect(
        self,
        df: pd.DataFrame,
        existing_data: Optional[pd.DataFrame] = None,
    ) -> QualityReport:
        """Run all quality checks against the incoming DataFrame.

        Args:
            df: Raw incoming DataFrame from a data fetcher.
            existing_data: Previously stored data for the same asset
                           (used for time-reversal and duplicate checks).

        Returns:
            QualityReport with pass/fail status, per-check details,
            rejection reasons, and warning flags.
        """
        checks: list[dict] = []
        reject_reasons: list[str] = []
        flags: list[str] = []

        # Map column names to canonical form for consistent checking
        mapped = self._map_columns(df)

        # ── Check 1: Non-empty ────────────────────────────────────────
        if df.empty:
            reject_reasons.append("Empty DataFrame — likely network error")
            checks.append({"name": "non_empty", "passed": False, "detail": "DataFrame is empty"})
            return QualityReport(
                passed=False,
                checks=checks,
                reject_reasons=reject_reasons,
                flags=flags,
            )
        checks.append({"name": "non_empty", "passed": True, "detail": ""})

        # ── Check 2: Price column ─────────────────────────────────────
        has_close = "close" in mapped or "adj_close" in mapped
        if not has_close:
            reject_reasons.append("Missing price column — need 'close' or 'adj_close'")
            checks.append(
                {
                    "name": "price_column",
                    "passed": False,
                    "detail": str(list(df.columns)),
                }
            )
            return QualityReport(
                passed=False,
                checks=checks,
                reject_reasons=reject_reasons,
                flags=flags,
            )
        checks.append({"name": "price_column", "passed": True, "detail": ""})

        # Determine which price column to use
        price_col = "close" if "close" in mapped else "adj_close"

        # ── Check 3: Row count vs date span ───────────────────────────
        if "date" in mapped:
            dates = pd.to_datetime(mapped["date"], errors="coerce")
            valid_dates = dates.dropna()
            if len(valid_dates) >= 2:
                date_span = (valid_dates.max() - valid_dates.min()).days
                if date_span > 200 and len(df) < 5:
                    flags.append(
                        f"Suspiciously few rows: {len(df)} rows spanning {date_span} days"
                    )
                    checks.append(
                        {
                            "name": "row_count",
                            "passed": True,
                            "detail": f"FLAG: {len(df)} rows over {date_span} days",
                        }
                    )
                else:
                    checks.append({"name": "row_count", "passed": True, "detail": ""})
            else:
                checks.append(
                    {"name": "row_count", "passed": True, "detail": "insufficient date data"}
                )
        else:
            checks.append({"name": "row_count", "passed": True, "detail": "no date column"})

        # ── Check 4: NaN proportion in price column ───────────────────
        price_series = pd.to_numeric(mapped[price_col], errors="coerce")
        nan_rate = price_series.isna().mean()
        if nan_rate > 0.5:
            reject_reasons.append(f"Majority NaN values: {nan_rate:.1%} NaN in {price_col}")
            checks.append(
                {"name": "nan_check", "passed": False, "detail": f"{nan_rate:.1%} NaN"}
            )
        else:
            checks.append(
                {"name": "nan_check", "passed": True, "detail": f"{nan_rate:.1%} NaN"}
            )

        # ── Check 5: Positive prices ──────────────────────────────────
        valid_prices = price_series.dropna()
        if len(valid_prices) > 0 and (valid_prices <= 0).any():
            reject_reasons.append("Non-positive prices found — data is corrupt or invalid")
            checks.append(
                {"name": "positive_prices", "passed": False, "detail": "REJECT: close <= 0"}
            )
        else:
            checks.append({"name": "positive_prices", "passed": True, "detail": ""})

        # ── Check 6: Time reversal ────────────────────────────────────
        if existing_data is not None and not existing_data.empty and "date" in mapped:
            new_dates = pd.to_datetime(mapped["date"], errors="coerce").dropna()
            if len(new_dates) > 0:
                new_max = new_dates.max()
                if "date" in existing_data.columns:
                    existing_max = pd.to_datetime(existing_data["date"], errors="coerce").max()
                    if pd.notna(existing_max) and new_max < existing_max:
                        reject_reasons.append(
                            f"Newer data already exists: new max date {new_max.date()} "
                            f"< existing max date {existing_max.date()}"
                        )
                        checks.append(
                            {
                                "name": "time_reversal",
                                "passed": False,
                                "detail": f"new max {new_max.date()} < existing max {existing_max.date()}",
                            }
                        )
                    else:
                        checks.append({"name": "time_reversal", "passed": True, "detail": ""})
                else:
                    checks.append(
                        {"name": "time_reversal", "passed": True, "detail": "no date in existing"}
                    )
            else:
                checks.append(
                    {"name": "time_reversal", "passed": True, "detail": "no valid dates"}
                )
        else:
            checks.append(
                {
                    "name": "time_reversal",
                    "passed": True,
                    "detail": "no existing data to compare",
                }
            )

        # ── Check 7: Price spikes (daily change > 50%) ────────────────
        if "date" in mapped and len(mapped) >= 2:
            ts = mapped[["date", price_col]].copy()
            ts["date"] = pd.to_datetime(ts["date"], errors="coerce")
            ts[price_col] = pd.to_numeric(ts[price_col], errors="coerce")
            ts = ts.dropna(subset=["date", price_col]).sort_values("date")
            if len(ts) >= 2:
                ts["pct_change"] = ts[price_col].pct_change().abs()
                spike_mask = ts["pct_change"] > 0.5
                if spike_mask.any():
                    spike_count = spike_mask.sum()
                    flags.append(
                        f"Extreme price movements detected: {spike_count} day(s) with >50% daily change"
                    )
                    checks.append(
                        {
                            "name": "price_spikes",
                            "passed": True,
                            "detail": f"FLAG: {spike_count} spikes >50%",
                        }
                    )
                else:
                    checks.append({"name": "price_spikes", "passed": True, "detail": ""})
            else:
                checks.append(
                    {
                        "name": "price_spikes",
                        "passed": True,
                        "detail": "insufficient data after cleaning",
                    }
                )
        else:
            checks.append(
                {
                    "name": "price_spikes",
                    "passed": True,
                    "detail": "no date column or single row",
                }
            )

        # ── Check 8: Flat trading days (O=H=L=C and volume=0) ──────
        if "open" in mapped and "high" in mapped and "low" in mapped and "volume" in mapped:
            price_for_flat = mapped[price_col]
            flat_mask = (
                (mapped["open"] == mapped["high"])
                & (mapped["high"] == mapped["low"])
                & (mapped["low"] == price_for_flat)
                & (mapped.get("volume", pd.Series(1, index=mapped.index)) == 0)
            )
            flat_count = flat_mask.sum()
            if flat_count > 0:
                flags.append(
                    f"Suspicious flat trading days: {flat_count} row(s) with "
                    "O=H=L=C and volume=0 — likely non-trading day stored as trading day"
                )
                checks.append(
                    {
                        "name": "flat_trading_days",
                        "passed": True,
                        "detail": f"FLAG: {flat_count} flat OHLVC rows",
                    }
                )
            else:
                checks.append({"name": "flat_trading_days", "passed": True, "detail": ""})
        else:
            checks.append(
                {"name": "flat_trading_days", "passed": True, "detail": "insufficient OHLCV columns"}
            )

        # ── Check 9: Duplicate data ───────────────────────────────────
        if existing_data is not None and not existing_data.empty:
            if self._is_duplicate(mapped, existing_data):
                reject_reasons.append("Duplicate data — identical to already-stored records")
                checks.append(
                    {"name": "duplicate_check", "passed": False, "detail": "data already exists"}
                )
            else:
                checks.append({"name": "duplicate_check", "passed": True, "detail": ""})
        else:
            checks.append(
                {
                    "name": "duplicate_check",
                    "passed": True,
                    "detail": "no existing data to compare",
                }
            )

        # ── Final report ──────────────────────────────────────────────
        passed = len(reject_reasons) == 0
        return QualityReport(
            passed=passed,
            checks=checks,
            reject_reasons=reject_reasons,
            flags=flags,
        )

    # ── Stale-price monitoring ────────────────────────────────────────────

    def stale_price_check(self, n_days: int = 3) -> pd.DataFrame:
        """Flag assets that haven't been updated in the last *n_days*.

        Returns a DataFrame with columns
        ``asset_id, issue_type, details, timestamp, date``.
        """
        now = datetime.now()
        threshold = now - timedelta(days=n_days)

        all_assets: list[str] = []
        try:
            all_assets = self.repository.list_assets()
        except Exception as exc:
            _log.warning("QualityGate: list_assets failed: %s", exc)
            return pd.DataFrame(columns=["asset_id", "issue_type", "details", "timestamp", "date"])

        if not all_assets:
            return pd.DataFrame(columns=["asset_id", "issue_type", "details", "timestamp", "date"])

        # Query last date per asset — aggregate across all available tables
        rows: list[dict] = []
        tables = [
            (getattr(self.repository, "price_path", None), "adj_close"),
            (getattr(self.repository, "fund_path", None), "unit_nav"),
            (getattr(self.repository, "wealth_path", None), "unit_nav"),
        ]
        for path, _col in tables:
            if path is None or not path.exists():
                continue
            query = """
                SELECT asset_id, MAX(date) as last_date
                FROM read_parquet($path)
                GROUP BY asset_id
            """
            try:
                df = self.repository._query(query, {"path": str(path)})
                if not df.empty:
                    rows.append(df)
            except Exception as exc:
                _log.warning("QualityGate: stale check query failed for %s: %s", path, exc)

        if not rows:
            return pd.DataFrame(columns=["asset_id", "issue_type", "details", "timestamp", "date"])

        combined = pd.concat(rows, ignore_index=True)
        combined["last_date"] = pd.to_datetime(combined["last_date"], errors="coerce")
        combined = combined.dropna(subset=["last_date"])
        # Keep the most recent date per asset across all tables
        combined = combined.sort_values("last_date").drop_duplicates(subset=["asset_id"], keep="last")

        stale = combined[combined["last_date"] < threshold].copy()
        if stale.empty:
            return pd.DataFrame(columns=["asset_id", "issue_type", "details", "timestamp", "date"])

        issues = pd.DataFrame(
            {
                "asset_id": stale["asset_id"],
                "issue_type": "stale_price",
                "details": stale["last_date"].apply(
                    lambda d: f"Last update: {d.strftime('%Y-%m-%d')}"
                ),
                "timestamp": now,
                "date": now.date().isoformat(),
            }
        )
        return issues

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Return a DataFrame with column names mapped to canonical form."""
        mapped = df.copy()
        mapped.columns = [_canonical_column_name(c) for c in df.columns]
        return mapped

    @staticmethod
    def _is_duplicate(new_df: pd.DataFrame, existing: pd.DataFrame) -> bool:
        """Check whether the incoming data is already fully present in storage."""
        # Normalize columns on both sides for comparison
        new_mapped = new_df.copy()
        new_mapped.columns = [_canonical_column_name(c) for c in new_df.columns]
        existing_mapped = existing.copy()
        existing_mapped.columns = [_canonical_column_name(c) for c in existing.columns]

        # Compare on common columns
        common_cols = [c for c in new_mapped.columns if c in existing_mapped.columns]
        if not common_cols:
            return False

        new_subset = new_mapped[common_cols].reset_index(drop=True)
        existing_subset = existing_mapped[common_cols].reset_index(drop=True)

        if new_subset.empty or existing_subset.empty:
            return False

        # Check if every row in new_df has a matching row in existing
        try:
            merged = new_subset.merge(existing_subset, on=common_cols, how="left", indicator=True)
            return (merged["_merge"] == "both").all()
        except Exception:
            return False
