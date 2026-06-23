"""Fetch and cache FX rates as canonical market data.

Live FX history is pulled from yfinance via ``findata.adapters.forex.CurrencyFetcher``
and stored under the canonical asset id ``fx.<from>_<to>.spot`` so that
``findata.fx.FindataFxProvider`` can serve it without hardcoded fallbacks.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from findata.store import MarketDataRepository
from optifolio_contracts.identifiers import normalize_instrument_id

_log = logging.getLogger(__name__)


def fx_asset_id(from_currency: str, to_currency: str) -> str:
    """Canonical market-data asset id for a currency pair."""
    return normalize_instrument_id(f"{from_currency}{to_currency}", asset_type="forex")


def sync_fx_rate(
    from_currency: str,
    to_currency: str,
    repo: MarketDataRepository | None = None,
    *,
    lookback_days: int = 30,
) -> int:
    """Fetch FX history and persist it to canonical market data.

    Args:
        from_currency: Source currency code, e.g. ``USD``.
        to_currency: Target currency code, e.g. ``CNY``.
        repo: Repository to write to. If None, uses the default repository.
        lookback_days: How many days of history to fetch.

    Returns:
        Number of rows saved.

    Raises:
        RuntimeError: If the pair cannot be fetched (directly or via inverse).
    """
    if from_currency == to_currency:
        return 0

    from findata.adapters.forex import CurrencyFetcher

    fetcher = CurrencyFetcher()
    repo = repo or MarketDataRepository()

    pair = f"{from_currency}{to_currency}"
    end = date.today()
    start = end - timedelta(days=lookback_days)
    start_str = start.isoformat()
    end_str = end.isoformat()

    df = fetcher.fetch(pair, start_date=start_str, end_date=end_str)
    if df.empty:
        # Try the inverse pair and invert the rate.
        inverse = f"{to_currency}{from_currency}"
        df_inv = fetcher.fetch(inverse, start_date=start_str, end_date=end_str)
        if df_inv.empty:
            raise RuntimeError(
                f"Unable to fetch FX rate for {from_currency}/{to_currency}"
            )
        for col in ("Open", "High", "Low", "Close"):
            if col in df_inv.columns:
                df_inv[col] = 1.0 / pd.to_numeric(df_inv[col], errors="coerce")
        df = df_inv

    if df.empty:
        raise RuntimeError(
            f"Unable to fetch FX rate for {from_currency}/{to_currency}"
        )

    fx_id = fx_asset_id(from_currency, to_currency)
    df = df.reset_index(names="date").rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    df["date"] = (
        pd.to_datetime(df["date"], errors="coerce")
        .dt.tz_localize(None)
        .dt.normalize()
    )
    df["adj_close"] = pd.to_numeric(df["close"], errors="coerce")
    df["asset_id"] = fx_id
    df["currency"] = to_currency
    df["source"] = "yfinance"
    df["timezone"] = "UTC"

    rows_before = len(repo.load_canonical())
    repo.save_canonical(
        df,
        asset_id=fx_id,
        source="yfinance",
        currency=to_currency,
        timezone="UTC",
    )
    rows_after = len(repo.load_canonical())
    return int(rows_after - rows_before)
