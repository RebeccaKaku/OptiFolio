"""Canonical market data schemas and normalization helpers."""

from __future__ import annotations

from typing import Optional

import pandas as pd


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
]

FUND_NAV_COLUMNS = [
    "asset_id",
    "date",
    "unit_nav",
    "acc_nav",
    "daily_return",
    "currency",
    "source",
]

WEALTH_NAV_COLUMNS = [
    "asset_id",
    "date",
    "unit_nav",
    "acc_nav",
    "currency",
    "risk_level",
    "source",
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


def _normalize_common(
    frame: pd.DataFrame,
    asset_id: Optional[str] = None,
    source: str = "manual",
    currency: Optional[str] = None,
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()

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

    if "date" not in df.columns:
        raise ValueError("data requires a date column or DatetimeIndex")

    df["asset_id"] = df["asset_id"].astype(str).str.strip()
    df["date"] = pd.to_datetime(df["date"], errors="raise").dt.tz_localize(None)
    df["source"] = df["source"].fillna(source).astype(str)
    if currency is not None:
        df["currency"] = df["currency"].fillna(currency)

    return df


def normalize_market_frame(
    frame: pd.DataFrame,
    asset_id: Optional[str] = None,
    source: str = "manual",
    currency: Optional[str] = None,
) -> pd.DataFrame:
    """Convert provider output into the canonical market-data schema."""
    df = _normalize_common(frame, asset_id, source, currency)
    if df.empty:
        return pd.DataFrame(columns=CANONICAL_MARKET_COLUMNS)

    if "adj_close" not in df.columns:
        if "close" not in df.columns:
            raise ValueError("market data requires either close or adj_close")
        df["adj_close"] = df["close"]

    for column in ("open", "high", "low", "volume"):
        if column not in df.columns:
            df[column] = pd.NA

    if "close" not in df.columns:
        df["close"] = df["adj_close"]

    df = df[CANONICAL_MARKET_COLUMNS].copy()
    numeric_columns = ["open", "high", "low", "close", "adj_close", "volume"]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    return df.sort_values(["asset_id", "date", "source"]).reset_index(drop=True)


def normalize_fund_nav_frame(
    frame: pd.DataFrame,
    asset_id: Optional[str] = None,
    source: str = "manual",
    currency: Optional[str] = None,
) -> pd.DataFrame:
    """Convert provider output into the fund NAV schema."""
    df = _normalize_common(frame, asset_id, source, currency)
    if df.empty:
        return pd.DataFrame(columns=FUND_NAV_COLUMNS)

    for column in ("acc_nav", "daily_return"):
        if column not in df.columns:
            df[column] = pd.NA

    if "unit_nav" not in df.columns:
        if "close" in df.columns:
            df["unit_nav"] = df["close"]
        else:
            raise ValueError("fund NAV data requires unit_nav")

    df = df[FUND_NAV_COLUMNS].copy()
    numeric_columns = ["unit_nav", "acc_nav", "daily_return"]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    return df.sort_values(["asset_id", "date", "source"]).reset_index(drop=True)


def normalize_wealth_nav_frame(
    frame: pd.DataFrame,
    asset_id: Optional[str] = None,
    source: str = "manual",
    currency: Optional[str] = None,
) -> pd.DataFrame:
    """Convert provider output into the wealth management NAV schema."""
    df = _normalize_common(frame, asset_id, source, currency)
    if df.empty:
        return pd.DataFrame(columns=WEALTH_NAV_COLUMNS)

    for column in ("acc_nav", "risk_level"):
        if column not in df.columns:
            df[column] = pd.NA

    if "unit_nav" not in df.columns:
        if "close" in df.columns:
            df["unit_nav"] = df["close"]
        else:
            raise ValueError("wealth NAV data requires unit_nav")

    df = df[WEALTH_NAV_COLUMNS].copy()
    numeric_columns = ["unit_nav", "acc_nav"]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    return df.sort_values(["asset_id", "date", "source"]).reset_index(drop=True)


def validate_market_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate canonical market data and return a typed DataFrame."""
    try:
        import pandera.pandas as pa
        from pandera import Check
    except ImportError:
        return _validate_frame_without_pandera(frame, CANONICAL_MARKET_COLUMNS)

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
        },
        checks=[
            Check(lambda df: ~df[["asset_id", "date", "source"]].duplicated().any()),
        ],
        coerce=True,
        strict=True,
    )
    return schema.validate(frame, lazy=True)


def validate_fund_nav_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate fund NAV data."""
    try:
        import pandera.pandas as pa
        from pandera import Check
    except ImportError:
        return _validate_frame_without_pandera(frame, FUND_NAV_COLUMNS)

    schema = pa.DataFrameSchema(
        {
            "asset_id": pa.Column(str, nullable=False),
            "date": pa.Column(pa.DateTime, nullable=False),
            "unit_nav": pa.Column(float, Check.gt(0), nullable=False, coerce=True),
            "acc_nav": pa.Column(float, Check.gt(0), nullable=True, coerce=True),
            "daily_return": pa.Column(float, nullable=True, coerce=True),
            "currency": pa.Column(str, nullable=True),
            "source": pa.Column(str, nullable=False),
        },
        checks=[
            Check(lambda df: ~df[["asset_id", "date", "source"]].duplicated().any()),
        ],
        coerce=True,
        strict=True,
    )
    return schema.validate(frame, lazy=True)


def validate_wealth_nav_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate wealth management NAV data."""
    try:
        import pandera.pandas as pa
        from pandera import Check
    except ImportError:
        return _validate_frame_without_pandera(frame, WEALTH_NAV_COLUMNS)

    schema = pa.DataFrameSchema(
        {
            "asset_id": pa.Column(str, nullable=False),
            "date": pa.Column(pa.DateTime, nullable=False),
            "unit_nav": pa.Column(float, Check.gt(0), nullable=False, coerce=True),
            "acc_nav": pa.Column(float, Check.gt(0), nullable=True, coerce=True),
            "currency": pa.Column(str, nullable=True),
            "risk_level": pa.Column(pa.Object, nullable=True),
            "source": pa.Column(str, nullable=False),
        },
        checks=[
            Check(lambda df: ~df[["asset_id", "date", "source"]].duplicated().any()),
        ],
        coerce=True,
        strict=True,
    )
    return schema.validate(frame, lazy=True)


def _validate_frame_without_pandera(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = frame[columns].copy()
    df["date"] = pd.to_datetime(df["date"], errors="raise")

    if df[["asset_id", "date", "source"]].duplicated().any():
        raise ValueError("Duplicate asset_id/date/source rows are not allowed")
    if df["asset_id"].isna().any() or df["source"].isna().any():
        raise ValueError("asset_id and source are required")

    # Positive checks for common columns
    for col in ["close", "adj_close", "unit_nav", "acc_nav"]:
        if col in df.columns:
            if (df[col].dropna() <= 0).any():
                raise ValueError(f"{col} must be positive")

    for col in ["open", "high", "low", "volume"]:
        if col in df.columns:
            if (df[col].dropna() < 0).any():
                raise ValueError(f"{col} cannot be negative")

    return df
