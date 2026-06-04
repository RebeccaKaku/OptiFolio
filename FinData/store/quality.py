"""Data quality checks and reporting for market data."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from src.core.paths import PROJECT_ROOT
from src.data_foundation import MarketDataRepository


class QualityReport:
    """Handles persistence of data quality issues."""

    FILE_PATH = PROJECT_ROOT / "metadata" / "data_quality_issues.parquet"

    def __init__(self, issues: pd.DataFrame) -> None:
        self.issues = issues

    def save(self) -> None:
        """Persist the quality issues to the metadata parquet file."""
        if self.issues.empty:
            return

        self.FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

        if self.FILE_PATH.exists():
            try:
                existing = pd.read_parquet(self.FILE_PATH)
                updated = pd.concat([existing, self.issues], ignore_index=True)
            except Exception:
                # If file is corrupt or unreadable, overwrite with new issues
                updated = self.issues
        else:
            updated = self.issues

        updated.to_parquet(self.FILE_PATH, index=False)


class QualityGate:
    """Performs data quality checks on market data."""

    def __init__(self, repository: Optional[MarketDataRepository] = None) -> None:
        self.repository = repository or MarketDataRepository()

    def stale_price_check(self, n_days: int) -> QualityReport:
        """
        Flags assets that haven't been updated in the last N days.

        Args:
            n_days: Number of days threshold for staleness.

        Returns:
            A QualityReport containing the identified issues.
        """
        if not self.repository.price_path.exists():
            return QualityReport(
                pd.DataFrame(columns=["asset_id", "issue_type", "details", "timestamp"])
            )

        query = "SELECT asset_id, MAX(date) as last_date FROM read_parquet($path) GROUP BY asset_id"
        df = self.repository._query(query, {"path": str(self.repository.price_path)})

        if df.empty:
            return QualityReport(
                pd.DataFrame(columns=["asset_id", "issue_type", "details", "timestamp"])
            )

        now = datetime.now()
        threshold = now - timedelta(days=n_days)

        # Ensure last_date is datetime
        df["last_date"] = pd.to_datetime(df["last_date"])

        stale_df = df[df["last_date"] < threshold].copy()

        issues = pd.DataFrame(
            {
                "asset_id": stale_df["asset_id"],
                "issue_type": "stale_price",
                "details": stale_df["last_date"].apply(
                    lambda d: f"Last update: {d.strftime('%Y-%m-%d')}"
                ),
                "timestamp": now,
            }
        )

        return QualityReport(issues)
