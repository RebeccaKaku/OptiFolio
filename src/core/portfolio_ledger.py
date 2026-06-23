from dataclasses import dataclass, asdict
from datetime import datetime
import os
from typing import List, Optional
import pandas as pd
from pathlib import Path

@dataclass
class PortfolioLedger:
    account_id: str
    asset_id: str
    quantity: float
    cost_basis: float
    currency: str
    as_of: datetime

class PortfolioLedgerStore:
    def __init__(self, storage_path: str = "data/gold/portfolio_ledger.parquet"):
        self.storage_path = Path(storage_path)

    def save_entries(self, entries: List[PortfolioLedger]):
        if not entries:
            return

        new_df = pd.DataFrame([asdict(e) for e in entries])

        if self.storage_path.exists():
            existing_df = pd.read_parquet(self.storage_path)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = new_df
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        combined_df.to_parquet(self.storage_path, index=False)

    def load_entries(self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> pd.DataFrame:
        if not self.storage_path.exists():
            return pd.DataFrame(columns=["account_id", "asset_id", "quantity", "cost_basis", "currency", "as_of"])

        df = pd.read_parquet(self.storage_path)

        if start_date:
            df = df[df['as_of'] >= start_date]
        if end_date:
            df = df[df['as_of'] <= end_date]

        return df
