"""Canonical market data schemas and normalization helpers.

Adapted from src/data_foundation/schemas.py for the FinData storage department.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


CANONICAL_COLUMNS = [
    "asset_id",
    "date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "currency",
    "source",
    "timezone",
]

store_version: str = "1.0"


_COLUMN_ALIASES = {
    "asset": "asset_id",
    "symbol": "asset_id",
    "ticker": "asset_id",
    "datetime": "date",
    "time": "date",
    "timestamp": "date",
    "adj close": "adj_close",
    "adjusted_close": "adj_close",
    "adjusted close": "adj_close",
}


def _canonical_column_name(name: object) -> str:
    normalized = str(name).strip().replace("_", " ").lower()
    return _COLUMN_ALIASES.get(normalized, normalized.replace(" ", "_"))


def normalize_market_frame(
    frame: pd.DataFrame,
    asset_id: Optional[str] = None,
    source: str = "manual",
    currency: Optional[str] = None,
    timezone: Optional[str] = None,
) -> pd.DataFrame:
    """Convert provider output into the canonical market-data schema.

    Args:
        frame: Raw provider DataFrame.
        asset_id: Asset identifier (e.g. 'AAPL').
        source: Data source label (e.g. 'yahoo', 'akshare').
        currency: ISO 4217 currency code.
        timezone: IANA timezone for the exchange (e.g. 'America/New_York').
                  Used to convert timestamps to exchange-local calendar dates.
                  When None, dates are kept as-is (backward compatibility).

    Date normalization:
        All timestamps are converted to the exchange's local calendar date
        (date-only, no time component). This ensures "Monday's close" is
        always tagged as Monday in the exchange's timezone, regardless of
        the UTC equivalent.
    """
    if frame is None or frame.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    df = frame.copy()
    if isinstance(df.index, pd.DatetimeIndex) and "date" not in df.columns:
        df = df.reset_index(names="date")
    else:
        df = df.reset_index() if "date" not in df.columns and df.index.name else df

    df.columns = [_canonical_column_name(column) for column in df.columns]

    if "asset_id" not in df.columns:
        if not asset_id:
            raise ValueError("asset_id is required when the frame has no asset column")
        df["asset_id"] = asset_id
    if "source" not in df.columns:
        df["source"] = source
    if "currency" not in df.columns:
        df["currency"] = currency
    if "adj_close" not in df.columns:
        if "close" not in df.columns:
            raise ValueError("market data requires either close or adj_close")
        df["adj_close"] = df["close"]

    for column in ("open", "high", "low", "volume", "timezone"):
        if column not in df.columns:
            df[column] = pd.NA

    if "date" not in df.columns:
        raise ValueError("market data requires a date column or DatetimeIndex")
    if "close" not in df.columns:
        df["close"] = df["adj_close"]

    df = df[CANONICAL_COLUMNS].copy()
    df["asset_id"] = df["asset_id"].astype(str).str.strip()

    # ── Date normalization: exchange-local calendar date ──────────────
    dates = pd.to_datetime(df["date"], errors="raise")
    if timezone is not None:
        # Convert to exchange-local calendar date
        if dates.dt.tz is None:
            # Naive → assume the data is already in exchange-local time
            # (common for akshare and bank APIs that return date-only strings)
            pass
        else:
            # Tz-aware → convert to exchange timezone
            dates = dates.dt.tz_convert(timezone)
        # Store as date-only (no time component)
        df["date"] = dates.dt.normalize()
    else:
        # Backward compatibility: strip timezone, keep as-is
        df["date"] = dates.dt.tz_localize(None)

    df["source"] = df["source"].fillna(source).astype(str)
    df["timezone"] = df["timezone"].fillna(timezone or "UTC")
    if currency is not None:
        df["currency"] = df["currency"].fillna(currency)

    numeric_columns = ["open", "high", "low", "close", "adj_close", "volume"]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    return df.sort_values(["asset_id", "date", "source"]).reset_index(drop=True)


def validate_market_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate canonical market data and return a typed DataFrame."""
    try:
        import pandera.pandas as pa
        from pandera import Check
    except ImportError:
        return _validate_market_frame_without_pandera(frame)

    schema = pa.DataFrameSchema(
        {
            "asset_id": pa.Column(str, nullable=False),
            "date": pa.Column(pa.DateTime, nullable=False),
            "open": pa.Column(float, Check.ge(0), nullable=True, coerce=True),
            "high": pa.Column(float, Check.ge(0), nullable=True, coerce=True),
            "low": pa.Column(float, Check.ge(0), nullable=True, coerce=True),
            "close": pa.Column(float, Check.gt(0), nullable=False, coerce=True),
            "adj_close": pa.Column(float, Check.gt(0), nullable=False, coerce=True),
            "volume": pa.Column(float, Check.ge(0), nullable=True, coerce=True),
            "currency": pa.Column(str, nullable=True),
            "source": pa.Column(str, nullable=False),
            "timezone": pa.Column(str, nullable=True),
        },
        checks=[
            Check(lambda df: ~df[["asset_id", "date", "source"]].duplicated().any()),
        ],
        coerce=True,
        strict=True,
    )
    return schema.validate(frame, lazy=True)


def _validate_market_frame_without_pandera(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in CANONICAL_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing canonical market data columns: {missing}")

    df = frame[CANONICAL_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"], errors="raise")
    for column in ["open", "high", "low", "close", "adj_close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if df[["asset_id", "date", "source"]].duplicated().any():
        raise ValueError("Duplicate asset_id/date/source rows are not allowed")
    if df["asset_id"].isna().any() or df["source"].isna().any():
        raise ValueError("asset_id and source are required")
    if (df["close"] <= 0).any() or (df["adj_close"] <= 0).any():
        raise ValueError("close and adj_close must be positive")
    for column in ["open", "high", "low", "volume"]:
        if (df[column].dropna() < 0).any():
            raise ValueError(f"{column} cannot be negative")
    return df
