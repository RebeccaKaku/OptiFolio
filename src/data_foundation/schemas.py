"""Canonical market data schemas and normalization helpers."""

from __future__ import annotations

from typing import Optional

import pandas as pd


STORE_VERSION: str = "1.0"


CANONICAL_MARKET_COLUMNS = [
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


CANONICAL_OBSERVATION_COLUMNS = [
    "series_id",
    "effective_date",
    "value",
    "known_at",
    "released_at",
    "observed_at",
    "source",
    "revision",
    "quality_flags",
    "unit",
    "currency",
]


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
        return pd.DataFrame(columns=CANONICAL_MARKET_COLUMNS)

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

    df = df[CANONICAL_MARKET_COLUMNS].copy()
    df["asset_id"] = df["asset_id"].astype(str).str.strip()
    # Normalize CN stock IDs: strip sh/sz prefix → bare 6-digit code (see naming conventions)
    df["asset_id"] = df["asset_id"].str.replace(r"^(?:sh|sz)(\d{6})$", r"\1", regex=True)

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
    missing = [column for column in CANONICAL_MARKET_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing canonical market data columns: {missing}")

    df = frame[CANONICAL_MARKET_COLUMNS].copy()
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


def normalize_observation_frame(
    frame: pd.DataFrame,
    series_id: Optional[str] = None,
    source: str = "manual",
    unit: Optional[str] = None,
    currency: Optional[str] = None,
) -> pd.DataFrame:
    """Convert generic time-series observations into canonical form.

    Use this for macro indicators, interest rates, yield-curve nodes,
    index levels, factor signals, and other data that is not a tradable
    OHLCV/NAV price series.
    """
    if frame is None or frame.empty:
        return pd.DataFrame(columns=CANONICAL_OBSERVATION_COLUMNS)

    df = frame.copy()
    if isinstance(df.index, pd.DatetimeIndex) and "effective_date" not in df.columns:
        df = df.reset_index(names="effective_date")
    elif "effective_date" not in df.columns and "date" not in df.columns and df.index.name:
        df = df.reset_index()

    df.columns = [_canonical_column_name(column) for column in df.columns]
    if "date" in df.columns and "effective_date" not in df.columns:
        df = df.rename(columns={"date": "effective_date"})

    if "series_id" not in df.columns:
        if not series_id:
            raise ValueError("series_id is required when the frame has no series_id column")
        df["series_id"] = series_id
    if "source" not in df.columns:
        df["source"] = source
    if "unit" not in df.columns:
        df["unit"] = unit
    if "currency" not in df.columns:
        df["currency"] = currency
    if "revision" not in df.columns:
        df["revision"] = 0
    if "quality_flags" not in df.columns:
        df["quality_flags"] = ""

    if "effective_date" not in df.columns:
        raise ValueError("observation data requires effective_date or date")
    if "value" not in df.columns:
        raise ValueError("observation data requires a value column")

    effective = pd.to_datetime(df["effective_date"], errors="raise").dt.normalize()
    df["effective_date"] = effective

    for column in ("known_at", "released_at", "observed_at"):
        if column not in df.columns:
            df[column] = pd.NaT
        df[column] = pd.to_datetime(df[column], errors="coerce")

    missing_known = df["known_at"].isna()
    if missing_known.any():
        df.loc[missing_known, "known_at"] = (
            df.loc[missing_known, "effective_date"] + pd.Timedelta(days=1)
        )

    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["series_id"] = df["series_id"].astype(str).str.strip()
    df["source"] = df["source"].fillna(source).astype(str)
    df["revision"] = pd.to_numeric(df["revision"], errors="coerce").fillna(0).astype(int)
    df["quality_flags"] = df["quality_flags"].apply(_stringify_quality_flags)

    df = df[CANONICAL_OBSERVATION_COLUMNS].copy()
    return df.sort_values(["series_id", "effective_date", "source", "revision"]).reset_index(drop=True)


def validate_observation_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate canonical non-price observations."""
    missing = [column for column in CANONICAL_OBSERVATION_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing canonical observation columns: {missing}")

    df = frame[CANONICAL_OBSERVATION_COLUMNS].copy()
    df["effective_date"] = pd.to_datetime(df["effective_date"], errors="raise").dt.normalize()
    for column in ("known_at", "released_at", "observed_at"):
        df[column] = pd.to_datetime(df[column], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["revision"] = pd.to_numeric(df["revision"], errors="raise").astype(int)

    if df["series_id"].isna().any() or (df["series_id"].astype(str).str.strip() == "").any():
        raise ValueError("series_id is required")
    if df["source"].isna().any() or (df["source"].astype(str).str.strip() == "").any():
        raise ValueError("source is required")
    if df["value"].isna().any():
        raise ValueError("observation value cannot be NaN")
    if (df["revision"] < 0).any():
        raise ValueError("revision cannot be negative")

    known = df["known_at"].dropna()
    if not known.empty:
        comparable = df.loc[known.index, "effective_date"]
        if (known.dt.normalize() < comparable).any():
            raise ValueError("known_at cannot be before effective_date")

    if df[["series_id", "effective_date", "source", "revision"]].duplicated().any():
        raise ValueError("Duplicate series_id/effective_date/source/revision rows are not allowed")

    return df


def _stringify_quality_flags(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, (list, tuple, set)):
        return "|".join(str(v) for v in value)
    return str(value)
