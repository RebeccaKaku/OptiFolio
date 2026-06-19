"""DuckDB-backed repository for canonical market data."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence

import pandas as pd

from src.core.paths import PROJECT_ROOT

from .schemas import (
    CANONICAL_MARKET_COLUMNS,
    CANONICAL_OBSERVATION_COLUMNS,
    STORE_VERSION,
    normalize_market_frame,
    normalize_observation_frame,
    validate_market_frame,
    validate_observation_frame,
)


class MarketDataRepository:
    """Store canonical market data in Parquet and query it through DuckDB."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir) if root_dir else PROJECT_ROOT / "data" / "foundation"
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.price_path = self.root_dir / "market_prices.parquet"
        self.observation_path = self.root_dir / "observations.parquet"
        self.check_version()

    def check_version(self) -> None:
        """Verify stored data is compatible with current schema version."""
        if not self.price_path.exists():
            return
        try:
            df = pd.read_parquet(self.price_path)
            required_cols = ["asset_id", "date", "close", "adj_close", "source"]
            missing = [c for c in required_cols if c not in df.columns]
            if missing:
                raise ValueError(
                    f"Stored data at {self.price_path} is missing required columns: {missing}. "
                    f"Schema migration needed. Current store version: {STORE_VERSION}."
                )
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Failed to read stored market data at {self.price_path}. "
                f"The file may be corrupted or from an incompatible version. "
                f"Current store version: {STORE_VERSION}."
            ) from exc

    def _acquire_lock(self):
        """Acquire an advisory lock for the price parquet file.

        Returns a (lock_file, unlock_fn) tuple. Caller must call unlock_fn
        or use the returned file as a context manager.
        """
        lock_path = str(self.price_path) + ".lock"
        lock_file = open(lock_path, "w")
        lock_file.write("L")  # ensure at least 1 byte for msvcrt locking
        lock_file.flush()

        try:
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            return lock_file, lambda: msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        except ImportError:
            pass

        try:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            return lock_file, lambda: fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except ImportError:
            pass

        # Fallback: no OS-level lock available — use a simple warning
        import warnings

        warnings.warn("No file locking available (msvcrt/fcntl not found). Concurrent writes may cause data loss.")
        return lock_file, lambda: None

    def save_bronze(
        self,
        frame: pd.DataFrame,
        provider: str,
        asset_id: str,
        entity: str = "market_price",
    ) -> Path:
        """Save provider output AS-IS to the bronze layer (no normalization).

        Bronze data is raw provider output, partitioned by provider/entity/date.
        It serves as an audit trail and reprocessing source.
        """
        ingest_date = pd.Timestamp.now().strftime("%Y-%m-%d")
        path = (
            PROJECT_ROOT
            / "FinData"
            / "data"
            / "bronze"
            / f"provider={provider}"
            / f"entity={entity}"
            / f"ingest_date={ingest_date}"
            / f"{asset_id}.parquet"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, compression="snappy", index=False)
        return path

    def save_canonical(
        self,
        frame: pd.DataFrame,
        asset_id: str | None = None,
        source: str = "manual",
        currency: str | None = None,
        timezone: str | None = None,
    ) -> pd.DataFrame:
        """Normalize, validate, and persist data to the canonical store.

        Canonical data is the single source of truth for downstream consumers.
        """
        canonical = normalize_market_frame(frame, asset_id=asset_id, source=source, currency=currency, timezone=timezone)
        canonical = validate_market_frame(canonical)
        lock_file, unlock = self._acquire_lock()
        try:
            existing = self.load_canonical()
            combined = canonical if existing.empty else pd.concat([existing, canonical], ignore_index=True)
            combined = combined.drop_duplicates(["asset_id", "date", "source"], keep="last")
            combined = combined.sort_values(["asset_id", "date", "source"]).reset_index(drop=True)
            validate_market_frame(combined).to_parquet(self.price_path, compression="snappy", index=False)
        finally:
            unlock()
            lock_file.close()
        return canonical

    def save_raw(self, *args, **kwargs) -> pd.DataFrame:
        """Deprecated — use save_canonical instead."""
        import warnings

        warnings.warn(
            "save_raw is deprecated, use save_canonical instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.save_canonical(*args, **kwargs)

    def load_canonical(self) -> pd.DataFrame:
        if not self.price_path.exists():
            return pd.DataFrame(columns=CANONICAL_MARKET_COLUMNS)
        return pd.read_parquet(self.price_path)

    def save_observations(
        self,
        frame: pd.DataFrame,
        series_id: str | None = None,
        source: str = "manual",
        unit: str | None = None,
        currency: str | None = None,
    ) -> pd.DataFrame:
        """Normalize, validate, and persist non-price observations.

        This is the canonical path for macro data, interest rates,
        index levels that are used as reference series, yield-curve nodes,
        and model signals. It deliberately lives outside the OHLCV price
        table so downstream algorithms can distinguish tradable prices
        from informational series.
        """
        observations = normalize_observation_frame(
            frame,
            series_id=series_id,
            source=source,
            unit=unit,
            currency=currency,
        )
        observations = validate_observation_frame(observations)

        self.observation_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.load_observations()
        combined = observations if existing.empty else pd.concat([existing, observations], ignore_index=True)
        combined = combined.drop_duplicates(
            ["series_id", "effective_date", "source", "revision"],
            keep="last",
        )
        combined = combined.sort_values(
            ["series_id", "effective_date", "source", "revision"]
        ).reset_index(drop=True)
        validate_observation_frame(combined).to_parquet(
            self.observation_path,
            compression="snappy",
            index=False,
        )
        return observations

    def load_observations(self) -> pd.DataFrame:
        if not self.observation_path.exists():
            return pd.DataFrame(columns=CANONICAL_OBSERVATION_COLUMNS)
        return pd.read_parquet(self.observation_path)

    def get_observations(
        self,
        series_ids: Sequence[str],
        start: str | None = None,
        end: str | None = None,
        known_at: str | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """Return canonical observations filtered by date and availability."""
        if not series_ids or not self.observation_path.exists():
            return pd.DataFrame(columns=CANONICAL_OBSERVATION_COLUMNS)

        df = self.load_observations()
        if df.empty:
            return df

        df["effective_date"] = pd.to_datetime(df["effective_date"])
        df["known_at"] = pd.to_datetime(df["known_at"], errors="coerce")
        mask = df["series_id"].isin(list(series_ids))
        if start:
            mask &= df["effective_date"] >= pd.Timestamp(start)
        if end:
            mask &= df["effective_date"] <= pd.Timestamp(end)
        if known_at is not None:
            known_ts = pd.Timestamp(known_at)
            mask &= df["known_at"].notna() & (df["known_at"] <= known_ts)
        return df.loc[mask].sort_values(
            ["series_id", "effective_date", "source", "revision"]
        ).reset_index(drop=True)

    def latest_observation(
        self,
        series_id: str,
        as_of: str | date | pd.Timestamp | None = None,
        known_at: str | pd.Timestamp | None = None,
    ) -> dict[str, object] | None:
        """Return the latest usable observation for one series."""
        end = pd.Timestamp(as_of).date().isoformat() if as_of is not None else None
        df = self.get_observations([series_id], end=end, known_at=known_at)
        if df.empty:
            return None

        df = df.sort_values(["effective_date", "revision"])
        row = df.iloc[-1].to_dict()
        return row

    def list_observation_series(self) -> pd.DataFrame:
        """Return one row per stored non-price series."""
        if not self.observation_path.exists():
            return pd.DataFrame(
                columns=[
                    "series_id",
                    "observations",
                    "first_date",
                    "last_date",
                    "last_known_at",
                    "source",
                    "unit",
                    "currency",
                ]
            )

        df = self.load_observations()
        if df.empty:
            return pd.DataFrame(
                columns=[
                    "series_id",
                    "observations",
                    "first_date",
                    "last_date",
                    "last_known_at",
                    "source",
                    "unit",
                    "currency",
                ]
            )

        df["effective_date"] = pd.to_datetime(df["effective_date"])
        df["known_at"] = pd.to_datetime(df["known_at"], errors="coerce")
        grouped = df.sort_values(["series_id", "effective_date", "revision"]).groupby("series_id")
        records = []
        for series_id, group in grouped:
            latest = group.iloc[-1]
            records.append(
                {
                    "series_id": series_id,
                    "observations": int(len(group)),
                    "first_date": group["effective_date"].min(),
                    "last_date": group["effective_date"].max(),
                    "last_known_at": group["known_at"].max(),
                    "source": latest.get("source"),
                    "unit": latest.get("unit"),
                    "currency": latest.get("currency"),
                }
            )
        return pd.DataFrame(records).sort_values("series_id").reset_index(drop=True)

    def observation_coverage(
        self,
        series_ids: Sequence[str] | None = None,
        expected_stale_days: int | None = None,
        as_of: str | date | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """Return coverage/staleness summary for non-price series."""
        summary = self.list_observation_series()
        columns = [
            "series_id",
            "observations",
            "first_date",
            "last_date",
            "last_known_at",
            "source",
            "unit",
            "currency",
            "stale_days",
            "is_stale",
            "missing",
        ]
        if series_ids is not None:
            requested = list(series_ids)
            if summary.empty:
                summary = pd.DataFrame({"series_id": requested})
            else:
                summary = summary[summary["series_id"].isin(requested)]
                missing = [sid for sid in requested if sid not in set(summary["series_id"])]
                if missing:
                    summary = pd.concat(
                        [summary, pd.DataFrame({"series_id": missing})],
                        ignore_index=True,
                    )

        if summary.empty:
            return pd.DataFrame(columns=columns)

        as_of_ts = pd.Timestamp(as_of or date.today()).normalize()
        summary["last_date"] = pd.to_datetime(summary.get("last_date"), errors="coerce")
        summary["first_date"] = pd.to_datetime(summary.get("first_date"), errors="coerce")
        summary["last_known_at"] = pd.to_datetime(summary.get("last_known_at"), errors="coerce")
        summary["observations"] = pd.to_numeric(
            summary.get("observations"),
            errors="coerce",
        ).fillna(0).astype(int)
        summary["missing"] = summary["last_date"].isna()
        summary["stale_days"] = (as_of_ts - summary["last_date"]).dt.days
        summary.loc[summary["missing"], "stale_days"] = pd.NA
        if expected_stale_days is None:
            summary["is_stale"] = False
        else:
            summary["is_stale"] = summary["missing"] | (summary["stale_days"] > expected_stale_days)
        for column in columns:
            if column not in summary.columns:
                summary[column] = pd.NA
        return summary[columns].sort_values("series_id").reset_index(drop=True)

    @staticmethod
    def _expand_asset_forms(asset_id: str) -> list[str]:
        """Return candidate forms for *asset_id* (bare + prefixed CN stock).

        CN stock symbols may be stored bare (600519) or prefixed (sh600519).
        Query both so lookups don't fail on format mismatches.
        """
        from src.core.symbols import normalize_cn_symbol

        return normalize_cn_symbol(asset_id)

    def get_prices(
        self,
        assets: Sequence[str],
        start: str | None = None,
        end: str | None = None,
        fields: Sequence[str] = ("adj_close",),
    ) -> pd.DataFrame:
        if not assets or not self.price_path.exists():
            return pd.DataFrame()

        for f in fields:
            if f not in CANONICAL_MARKET_COLUMNS:
                raise ValueError(f"Unknown market data field: {f}")

        # Build expanded asset list with normalized forms (bare + prefixed)
        expanded_assets: list[str] = []
        form_to_original: dict[str, str] = {}  # alternate form → original asset_id
        for a in assets:
            forms = self._expand_asset_forms(a)
            expanded_assets.extend(forms)
            for frm in forms:
                if frm != a:
                    form_to_original[frm] = a

        where_parts = ["asset_id IN $assets"]
        params: dict[str, object] = {"assets": expanded_assets, "path": str(self.price_path)}
        if start:
            where_parts.append("date >= $start")
            params["start"] = pd.Timestamp(start).to_pydatetime()
        if end:
            where_parts.append("date <= $end")
            params["end"] = pd.Timestamp(end).to_pydatetime()

        col_list = ", ".join(fields)
        query = f"""
            SELECT date, asset_id, {col_list}
            FROM read_parquet($path)
            WHERE {" AND ".join(where_parts)}
            ORDER BY date, asset_id
        """
        rows = self._query(query, params)
        if rows.empty:
            return pd.DataFrame()

        # Deduplicate: expanded forms may return same (date, normalized_id) twice
        rows["asset_id"] = rows["asset_id"].replace(form_to_original)
        rows = rows.drop_duplicates(subset=["date", "asset_id"])

        if len(fields) == 1:
            # Single field: return pivoted date × asset_id matrix (backwards compatible)
            matrix = rows.pivot(index="date", columns="asset_id", values=fields[0])
            matrix.index = pd.to_datetime(matrix.index)
            # Rename alternate forms back to original asset_ids
            rename = {k: v for k, v in form_to_original.items() if k in matrix.columns}
            if rename:
                matrix = matrix.rename(columns=rename)
            return matrix.reindex(columns=list(assets)).sort_index()
        else:
            # Multiple fields: return flat (date, asset_id, field1, field2, ...) DataFrame
            # Map alternate forms back to originals
            rows["asset_id"] = rows["asset_id"].replace(form_to_original)
            rows["date"] = pd.to_datetime(rows["date"])
            return rows.set_index("date").sort_index()

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
