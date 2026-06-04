"""Metadata tracking for data ingestion runs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src.core.paths import PROJECT_ROOT


@dataclass
class IngestionRun:
    """Metadata for a single ingestion run."""

    provider: str
    asset_id: str
    rows: int
    raw_path: str
    canonical_path: str
    status: str
    started_at: datetime
    finished_at: datetime = field(default_factory=datetime.now)
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    errors: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "provider": self.provider,
            "asset_id": self.asset_id,
            "rows": self.rows,
            "raw_path": self.raw_path,
            "canonical_path": self.canonical_path,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "errors": self.errors,
        }


class IngestionLog:
    """Manages persistence of ingestion run metadata."""

    FILE_PATH = PROJECT_ROOT / "FinData" / "data" / "metadata" / "ingestion_runs.parquet"

    def log_run(self, run: IngestionRun) -> None:
        """Persist an ingestion run to the metadata parquet file."""
        self.FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

        new_df = pd.DataFrame([run.to_dict()])

        if self.FILE_PATH.exists():
            try:
                existing = pd.read_parquet(self.FILE_PATH)
                updated = pd.concat([existing, new_df], ignore_index=True)
            except Exception:
                updated = new_df
        else:
            updated = new_df

        updated.to_parquet(self.FILE_PATH, index=False)

    def get_runs(self, limit: int = 100) -> pd.DataFrame:
        """Retrieve recent ingestion runs."""
        if not self.FILE_PATH.exists():
            return pd.DataFrame(
                columns=[
                    "run_id",
                    "provider",
                    "asset_id",
                    "rows",
                    "raw_path",
                    "canonical_path",
                    "status",
                    "started_at",
                    "finished_at",
                    "errors",
                ]
            )

        df = pd.read_parquet(self.FILE_PATH)
        return df.sort_values("finished_at", ascending=False).head(limit)
