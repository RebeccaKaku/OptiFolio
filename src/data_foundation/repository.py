"""DuckDB-backed repository for canonical market data."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd

from src.core.paths import PROJECT_ROOT

from .schemas import CANONICAL_MARKET_COLUMNS, normalize_market_frame, validate_market_frame


class MarketDataRepository:
    """Store canonical market data in Parquet and query it through DuckDB."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir) if root_dir else PROJECT_ROOT / "data" / "foundation"
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.price_path = self.root_dir / "market_prices.parquet"

    def save_raw(
        self,
        frame: pd.DataFrame,
        asset_id: str | None = None,
        source: str = "manual",
        currency: str | None = None,
        timezone: str | None = None,
    ) -> pd.DataFrame:
        canonical = normalize_market_frame(frame, asset_id=asset_id, source=source, currency=currency, timezone=timezone)
        canonical = validate_market_frame(canonical)
        existing = self.load_canonical()
        combined = canonical if existing.empty else pd.concat([existing, canonical], ignore_index=True)
        combined = combined.drop_duplicates(["asset_id", "date", "source"], keep="last")
        combined = combined.sort_values(["asset_id", "date", "source"]).reset_index(drop=True)
        validate_market_frame(combined).to_parquet(self.price_path, compression="snappy", index=False)
        return canonical

    def load_canonical(self) -> pd.DataFrame:
        if not self.price_path.exists():
            return pd.DataFrame(columns=CANONICAL_MARKET_COLUMNS)
        return pd.read_parquet(self.price_path)

    def get_prices(
        self,
        assets: Sequence[str],
        start: str | None = None,
        end: str | None = None,
        fields: Sequence[str] = ("adj_close",),
    ) -> pd.DataFrame:
        if not assets or not self.price_path.exists():
            return pd.DataFrame()
        if len(fields) != 1:
            raise ValueError("get_prices currently returns one field at a time")

        field = fields[0]
        if field not in CANONICAL_MARKET_COLUMNS:
            raise ValueError(f"Unknown market data field: {field}")

        where_parts = ["asset_id IN $assets"]
        params: dict[str, object] = {"assets": list(assets), "path": str(self.price_path)}
        if start:
            where_parts.append("date >= $start")
            params["start"] = pd.Timestamp(start).to_pydatetime()
        if end:
            where_parts.append("date <= $end")
            params["end"] = pd.Timestamp(end).to_pydatetime()

        query = f"""
            SELECT date, asset_id, {field} AS value
            FROM read_parquet($path)
            WHERE {" AND ".join(where_parts)}
            ORDER BY date, asset_id
        """
        rows = self._query(query, params)
        if rows.empty:
            return pd.DataFrame()

        matrix = rows.pivot(index="date", columns="asset_id", values="value")
        matrix.index = pd.to_datetime(matrix.index)
        return matrix.reindex(columns=list(assets)).sort_index()

    def get_returns(
        self,
        assets: Sequence[str],
        start: str | None = None,
        end: str | None = None,
        frequency: str = "D",
    ) -> pd.DataFrame:
        prices = self.get_prices(assets, start=start, end=end)
        if prices.empty:
            return prices

        sampled = prices
        if frequency and frequency.upper() not in {"D", "1D"}:
            sampled = prices.resample(frequency).last()
        return sampled.pct_change().dropna(how="all")

    def missing_report(
        self,
        assets: Sequence[str],
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        prices = self.get_prices(assets, start=start, end=end)
        if prices.empty:
            return pd.DataFrame(columns=["asset_id", "observations", "missing", "missing_rate"])

        report = pd.DataFrame(
            {
                "asset_id": prices.columns,
                "observations": prices.notna().sum().values,
                "missing": prices.isna().sum().values,
                "missing_rate": prices.isna().mean().values,
            }
        )
        return report

    def list_assets(self) -> list[str]:
        if not self.price_path.exists():
            return []
        query = "SELECT DISTINCT asset_id FROM read_parquet($path) ORDER BY asset_id"
        rows = self._query(query, {"path": str(self.price_path)})
        return rows["asset_id"].tolist()

    def _query(self, query: str, params: dict[str, object]) -> pd.DataFrame:
        try:
            import duckdb
        except ImportError as exc:
            raise RuntimeError(
                "duckdb is required for market data queries. Install project dependencies "
                "or run with the configured OptiFolio Python environment."
            ) from exc

        with duckdb.connect(":memory:") as connection:
            return connection.execute(query, params).df()
