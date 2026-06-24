#!/usr/bin/env python
"""Sync daily FX rates into MarketDataRepository via akshare (Sina BOC source).

Fetches historical CNY central parity rates for major currency pairs from
the Bank of China via Sina Finance (GFW-accessible), normalises them into
the canonical market-data schema, and stores each pair as a separate
asset_id (e.g. "fx.usd_cny.spot").

Usage:
    python tools/sync_fx_rates.py                          # sync all pairs, last 180 days
    python tools/sync_fx_rates.py --start 20240101          # custom start
    python tools/sync_fx_rates.py --pairs USDCNY,EURCNY     # specific pairs only
    python tools/sync_fx_rates.py --dry-run                 # preview without saving
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from findata.store import MarketDataRepository
from findata.store.schemas import CANONICAL_MARKET_COLUMNS
from optifolio_contracts.identifiers import normalize_instrument_id

# ── FX pair registry ─────────────────────────────────────────────────────
# (akshare_boc_symbol, from_currency, to_currency)
FX_PAIRS: dict[str, tuple[str, str, str]] = {
    "USDCNY": ("美元", "USD", "CNY"),
    "EURCNY": ("欧元", "EUR", "CNY"),
    "HKDCNY": ("港币", "HKD", "CNY"),
    "JPYCNY": ("日元", "JPY", "CNY"),
    "GBPCNY": ("英镑", "GBP", "CNY"),
}

# BOC convention: all rates are quoted as "CNY per 100 units of foreign currency"
BOC_UNITS_DENOMINATOR = 100.0

# The preferred column for the benchmark rate (PBOC central parity).
# Falls back to BOC converted price when central parity is NaN.
_RATE_COLUMN_PRIMARY = "央行中间价"
_RATE_COLUMN_FALLBACK = "中行折算价"


# TODO: wire via findata adapter — the CurrencyFetcher in findata.adapters.forex
# provides FX history via yfinance.  For BOC central parity specifically, we
# need an akshare-backed adapter inside findata.  Until then, the sync_pair()
# function below delegates to fd.fx_rate(mode="live") which syncs via yfinance.
def fetch_boc_sina_rate(
    symbol: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame | None:
    """Fetch daily BOC benchmark rate — STUB (akshare import removed).

    Use fd.fx_rate(mode="live") to sync live FX rates through findata instead.
    """
    return None


def sync_pair(
    pair_id: str,
    boc_symbol: str,
    from_curr: str,
    to_curr: str,
    start_date: str,
    end_date: str,
    repo: MarketDataRepository,
    *,
    dry_run: bool = False,
) -> int:
    """Sync a single FX pair into the repository via findata.

    Returns the number of pairs synced (1 on success, 0 on failure).
    """
    from findata import fd

    asset_id = normalize_instrument_id(
        f"{from_curr}{to_curr}", asset_type="forex"
    )

    if dry_run:
        print(f"  {pair_id} ({asset_id}): would sync via findata (dry-run)")
        return 1

    try:
        fd.fx_rate(from_curr, to_curr, mode="live")
        print(f"  {pair_id} ({asset_id}): synced via findata")
        return 1
    except Exception as exc:
        print(f"  {pair_id} ({asset_id}): error: {exc}")
        return 0


def default_start_date(lookback_days: int = 180) -> str:
    """Return YYYYMMDD for `lookback_days` ago."""
    return (date.today() - timedelta(days=lookback_days)).strftime("%Y%m%d")


def default_end_date() -> str:
    """Return today as YYYYMMDD."""
    return date.today().strftime("%Y%m%d")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync daily FX rates (BOC central parity) into MarketDataRepository"
    )
    parser.add_argument(
        "--pairs",
        help="Comma-separated pair IDs (e.g. USDCNY,EURCNY). Default: all.",
    )
    parser.add_argument(
        "--start",
        help="Start date YYYYMMDD (default: 180 days ago).",
    )
    parser.add_argument(
        "--end",
        help="End date YYYYMMDD (default: today).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without saving.",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=180,
        help="Lookback days when --start is omitted (default: 180).",
    )
    args = parser.parse_args()

    # Resolve pairs
    if args.pairs:
        requested = [p.strip().upper() for p in args.pairs.split(",")]
        invalid = [p for p in requested if p not in FX_PAIRS]
        if invalid:
            print(f"Unknown pair(s): {invalid}")
            print(f"Available: {list(FX_PAIRS.keys())}")
            sys.exit(1)
        pairs = {k: FX_PAIRS[k] for k in requested}
    else:
        pairs = FX_PAIRS

    start_date = args.start or default_start_date(args.lookback)
    end_date = args.end or default_end_date()

    print(f"Sync FX rates {start_date} .. {end_date}")
    if args.dry_run:
        print("[DRY RUN — no data will be saved]")

    repo = MarketDataRepository()
    total_rows = 0
    ok_count = 0

    for pair_id, (boc_symbol, from_curr, to_curr) in pairs.items():
        print(f"  {pair_id} ({from_curr}/{to_curr})...", end=" ", flush=True)
        rows = sync_pair(
            pair_id, boc_symbol, from_curr, to_curr,
            start_date, end_date, repo,
            dry_run=args.dry_run,
        )
        if rows > 0:
            total_rows += rows
            ok_count += 1

    print(f"Done: {ok_count}/{len(pairs)} pairs, {total_rows} total rows")


if __name__ == "__main__":
    main()
