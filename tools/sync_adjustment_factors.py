#!/usr/bin/env python
"""Sync A-share adjustment factors (复权因子) into MarketDataRepository.

The adjustment factor captures all corporate actions (dividends, splits,
rights issues) in a single time series. When applied to historical prices,
it produces forward-adjusted (前复权) or backward-adjusted (后复权) data.

Usage:
    python tools/sync_adjustment_factors.py                    # sync CN stocks from SQLite book
    python tools/sync_adjustment_factors.py --symbols 600519,000002  # specific symbols
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from findata.store import MarketDataRepository


def fetch_factor(symbol: str, factor_type: str = "qfq") -> pd.DataFrame | None:
    """Fetch adjustment factor for a single A-share symbol — STUB (akshare import removed).

    Args:
        symbol: 6-digit A-share code (e.g. '600519').
        factor_type: 'qfq' (前复权) or 'hfq' (后复权).

    Returns:
        DataFrame with columns [date, qfq_factor] or None on failure.
    """
    # TODO: wire via findata adapter — akshare's stock_zh_a_daily qfq-factor
    # mode needs a dedicated findata adapter (e.g. AdjustmentFactorFetcher).
    # The cn_stock adapter currently only handles price data.
    return None


def _bare_cn_code(symbol: str) -> str:
    import re

    match = re.search(r"(\d{6})$", symbol)
    return match.group(1) if match else symbol.replace("sh", "").replace("sz", "")


def main():
    parser = argparse.ArgumentParser(description="Sync A-share adjustment factors")
    parser.add_argument("--symbols", help="Comma-separated stock codes")
    parser.add_argument("--factor-type", default="qfq", choices=["qfq", "hfq"])
    args = parser.parse_args()

    # Resolve symbols
    symbols: list[str] = []
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
    else:
        from findata.orchestration.ingest import load_portfolio

        holdings, _ = load_portfolio()
        for sym in holdings:
            lowered = sym.lower()
            if lowered.startswith("equity.cn.") or lowered.startswith(("sh", "sz")):
                symbols.append(sym)

    if not symbols:
        print("No A-share symbols found. Use --symbols or create a confirmed SQLite batch.")
        return

    # Remove duplicates and prefixes for API calls
    clean_symbols = [_bare_cn_code(s) for s in symbols]
    clean_symbols = list(dict.fromkeys(clean_symbols))  # dedup preserving order

    print(f"Syncing adjustment factors for {len(clean_symbols)} symbols: {clean_symbols}")

    repo = MarketDataRepository()
    factor_type = args.factor_type

    for symbol in clean_symbols:
        print(f"  {symbol}...", end=" ", flush=True)
        df = fetch_factor(symbol, factor_type)
        if df is None or df.empty:
            print("no data")
            continue

        # Store as canonical market data (the factor value goes into adj_close)
        df["close"] = df[f"{factor_type}_factor"]
        df["adj_close"] = df[f"{factor_type}_factor"]
        df["currency"] = "CNY"
        df.index.name = "date"
        df = df.reset_index()

        try:
            repo.save_canonical(
                df,
                asset_id=f"{symbol}_factor_{factor_type}",
                source=f"akshare-{factor_type}-factor",
                currency="CNY",
                timezone="Asia/Shanghai",
            )
            print(f"OK ({len(df)} rows)")
        except Exception as exc:
            print(f"save error: {exc}")


if __name__ == "__main__":
    main()
