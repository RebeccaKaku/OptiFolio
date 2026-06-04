#!/usr/bin/env python
"""Ingest portfolio asset prices into MarketDataRepository.

Fetches OHLCV data for every holding in portfolio.yaml and saves it
to the canonical Parquet store (data/foundation/market_prices.parquet).

The canonical store is then queried by ValuationEngine for date-aware
portfolio valuation.

Usage:
    python tools/ingest_portfolio_prices.py                  # all holdings
    python tools/ingest_portfolio_prices.py --symbols AAPL,QQQ  # specific
    python tools/ingest_portfolio_prices.py --years 3         # 3 years of history
    python tools/ingest_portfolio_prices.py --dry-run          # show plan only
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import yaml

from src.core.calendars import ASSET_CALENDAR_MAP, get_calendar
from src.core.paths import PROJECT_ROOT
from src.data_foundation.repository import MarketDataRepository


# ── Asset metadata resolution ─────────────────────────────────────────

def load_asset_registry() -> Dict[str, Dict[str, Any]]:
    """Load asset_registry.yaml into {symbol: {currency, type, ...}}."""
    path = PROJECT_ROOT / "config" / "asset_registry.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    registry: Dict[str, Dict[str, Any]] = {}
    for entry in data.get("assets", []):
        sym = entry.get("symbol", "")
        if sym:
            registry[sym] = {
                "currency": entry.get("currency", "USD"),
                # Field is "asset_type" not "type" in asset_registry.yaml
                "type": entry.get("asset_type", ""),
                "name": entry.get("name", sym),
            }
    return registry


def load_candidates() -> Dict[str, Dict[str, Any]]:
    """Load candidates.yaml as supplement for asset metadata."""
    path = PROJECT_ROOT / "config" / "candidates.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    result: Dict[str, Dict[str, Any]] = {}
    for entry in data.get("assets", []):
        sym = entry.get("symbol", "")
        if sym:
            result[sym] = {
                "currency": entry.get("currency", "USD"),
                "type": entry.get("asset_type", ""),
            }
    return result


def load_portfolio() -> tuple[Dict[str, float], Dict[str, float]]:
    """Load portfolio holdings and cash."""
    for loc in [
        PROJECT_ROOT / "local" / "portfolio.yaml",
        PROJECT_ROOT / "config" / "portfolio.yaml",
    ]:
        if loc.exists():
            with open(loc, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            holdings = {str(k): float(v) for k, v in data.get("positions", {}).items()}
            cash = {str(k): float(v) for k, v in data.get("cash", {}).items()}
            return holdings, cash
    return {}, {}


def resolve_asset_meta(
    symbol: str,
    registry: Dict[str, Dict[str, Any]],
    candidates: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Resolve currency and type for a symbol."""
    # 1. Asset registry
    if symbol in registry:
        return registry[symbol]

    # 2. Candidates
    if symbol in candidates:
        return candidates[symbol]

    # 3. Heuristic inference
    currency = "USD"
    asset_type = "unknown"
    if symbol.startswith(("sh", "sz")):
        currency = "CNY"
        asset_type = "cn_stock"
    elif symbol.isdigit() and len(symbol) == 6:
        currency = "CNY"
        # Fund codes often start with 00, 16, 50, 51 etc.
        if symbol.startswith(("00", "16", "15", "50", "51")):
            asset_type = "cn_fund"
        else:
            asset_type = "cn_stock"
    elif symbol.isalpha() and symbol.isupper() and len(symbol) <= 5:
        currency = "USD"
        asset_type = "us_equity"
    # Bank product codes: uppercase alphanumeric, 8+ chars
    elif symbol.isupper() and any(c.isdigit() for c in symbol) and len(symbol) >= 8:
        currency = "USD" if "USD" in symbol else "CNY"
        asset_type = "bank_wm_boc"

    return {"currency": currency, "type": asset_type, "name": symbol}


# ── Fetcher dispatch ───────────────────────────────────────────────────

async def fetch_cn_stock(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch A-share OHLCV via existing CnStockFetcher (EastMoney→Sina→Tencent fallback)."""
    from src.data_core.fetchers.cn_stock import CnStockFetcher

    fetcher = CnStockFetcher()
    try:
        df = fetcher.fetch(symbol, start, end)
        if df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        # CnStockFetcher returns [date, open, high, low, close, volume]
        col_map = {"date": "date", "Date": "date", "timestamp": "date"}
        df = df.rename(columns=col_map)
        if "date" not in df.columns and df.index.name:
            df = df.reset_index()
        return df
    except Exception as exc:
        print(f"    [cn_stock] {symbol}: {exc}")
        return pd.DataFrame()


async def fetch_cn_fund(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch China fund NAV via existing CnFundFetcher."""
    from fetchers.cn_fund import CnFundFetcher

    fetcher = CnFundFetcher()
    return await fetcher.fetch(symbol, start, end)


async def fetch_us_equity(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch US equity via akshare Sina source (works behind GFW)."""
    try:
        import akshare as ak
        df = ak.stock_us_daily(symbol=symbol, adjust="qfq")
        if df.empty:
            return pd.DataFrame()
        df["date"] = pd.to_datetime(df["date"])
        # Filter to date range
        mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
        return df[mask][["date", "open", "high", "low", "close", "volume"]]
    except Exception as exc:
        print(f"    [us_equity] {symbol}: {exc}")
        return pd.DataFrame()


async def fetch_boc_product(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch BOC wealth management product net value."""
    from fetchers.boc import BocFetcher

    fetcher = BocFetcher(save_raw=False)
    return await fetcher.fetch(symbol, start, end)


async def fetch_icbc_product(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch ICBC wealth management product net value."""
    from fetchers.icbc import IcbcFetcher

    fetcher = IcbcFetcher(save_raw=False)
    return await fetcher.fetch(symbol, start, end)


async def fetch_asset(
    symbol: str,
    asset_type: str,
    start: str,
    end: str,
) -> pd.DataFrame | None:
    """Dispatch to the correct fetcher based on asset type."""
    # Bank products
    # ICBC: 8-char alphanumeric starting with digits (e.g. 23GS8125)
    if asset_type == "bank_wm_icbc" or (
        len(symbol) == 8 and symbol[:2].isdigit()
    ):
        return await fetch_icbc_product(symbol, start, end)
    # BOC: 10+ char uppercase alphanumeric (e.g. AMHQLXTTUSD01B)
    if asset_type == "bank_wm_boc" or (
        symbol.isupper() and any(c.isalpha() for c in symbol) and any(c.isdigit() for c in symbol) and len(symbol) >= 10
    ):
        return await fetch_boc_product(symbol, start, end)

    if asset_type in ("cn_stock", "cn_stock_sh", "cn_stock_sz"):
        return await fetch_cn_stock(symbol, start, end)
    elif asset_type in ("cn_fund", "cn_fund_open", "cn_fund_etf", "cn_fund_money", "cn_money_market_fund"):
        return await fetch_cn_fund(symbol, start, end)
    elif asset_type in ("us_equity", "us_etf", "crypto"):
        return await fetch_us_equity(symbol, start, end)
    elif asset_type == "forex" or asset_type == "currency":
        # Skip forex for price ingestion
        return None
    else:
        # Unknown type — try yfinance as last resort
        print(f"    [unknown type] {symbol} ({asset_type}) — trying yfinance")
        return await fetch_us_equity(symbol, start, end)


# ── Main ───────────────────────────────────────────────────────────────

async def main_async(args):
    holdings, _cash = load_portfolio()
    if args.symbols:
        target_symbols = [s.strip() for s in args.symbols.split(",")]
        holdings = {s: holdings.get(s, 0) for s in target_symbols}

    if not holdings:
        print("No holdings found.")
        return

    registry = load_asset_registry()
    candidates = load_candidates()

    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=args.years * 365)).isoformat()

    repo = MarketDataRepository()

    print(f"Ingesting {len(holdings)} assets from {start_date} to {end_date}")
    if args.dry_run:
        for symbol in holdings:
            meta = resolve_asset_meta(symbol, registry, candidates)
            tz = get_calendar(meta["type"]).timezone
            print(f"  {symbol}: type={meta['type']}, currency={meta['currency']}, tz={tz}")
        return

    success = 0
    skipped = 0
    failed = 0

    for symbol in holdings:
        meta = resolve_asset_meta(symbol, registry, candidates)
        asset_type = meta["type"]
        currency = meta["currency"]
        cal = get_calendar(asset_type)

        print(f"  {symbol} ({asset_type})...", end=" ", flush=True)

        try:
            df = await fetch_asset(symbol, asset_type, start_date, end_date)
        except Exception as exc:
            print(f"fetch error: {exc}")
            failed += 1
            continue

        if df is None or df.empty:
            print("no data")
            skipped += 1
            continue

        try:
            repo.save_raw(
                df, asset_id=symbol, source="portfolio-ingest",
                currency=currency, timezone=cal.timezone,
            )
            print(f"OK ({len(df)} rows)")
            success += 1
        except Exception as exc:
            print(f"save error: {exc}")
            failed += 1

    print(f"\nDone: {success} ingested, {skipped} no-data, {failed} failed")
    assets = repo.list_assets()
    print(f"Repository now has {len(assets)} assets: {assets}")


def main():
    parser = argparse.ArgumentParser(description="Ingest portfolio prices into MarketDataRepository")
    parser.add_argument("--symbols", help="Comma-separated symbols (default: all portfolio holdings)")
    parser.add_argument("--years", type=int, default=2, help="Years of history to fetch (default: 2)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without fetching")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
