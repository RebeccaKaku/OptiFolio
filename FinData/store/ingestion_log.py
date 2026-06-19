from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd

from findata.config import get_default_config


def _default_log_path() -> Path:
    return get_default_config().data_dir / "metadata" / "ingestion_runs.parquet"


@dataclass
class IngestionRun:
    run_id: str
    provider: str
    asset_id: str
    rows: int
    raw_path: str
    canonical_path: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    errors: Optional[str] = None

    @classmethod
    def create(cls, provider: str, asset_id: str) -> IngestionRun:
        return cls(
            run_id=str(uuid.uuid4()),
            provider=provider,
            asset_id=asset_id,
            rows=0,
            raw_path="",
            canonical_path="",
            status="started",
            started_at=datetime.now(),
        )


class IngestionLog:
    def __init__(self, log_path: Optional[Path] = None) -> None:
        self.log_path = log_path or _default_log_path()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_run(self, run: IngestionRun) -> None:
        df = pd.DataFrame([asdict(run)])

        if self.log_path.exists():
            existing_df = pd.read_parquet(self.log_path)
            # Remove existing run_id if it's an update
            existing_df = existing_df[existing_df["run_id"] != run.run_id]

            if existing_df.empty:
                pass  # df is already the new run
            elif df.empty:
                df = existing_df
            else:
                df = pd.concat([existing_df, df], ignore_index=True)

        df.to_parquet(self.log_path, index=False)

    def get_runs(self) -> List[IngestionRun]:
        if not self.log_path.exists():
            return []

        df = pd.read_parquet(self.log_path)
        runs = []
        for _, row in df.iterrows():
            # Convert row to dict and handle potential None/NaN for finished_at and errors
            data = row.to_dict()
            if pd.isna(data["finished_at"]):
                data["finished_at"] = None
            if pd.isna(data["errors"]):
                data["errors"] = None

            runs.append(IngestionRun(**data))
        return runs
