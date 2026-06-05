#!/usr/bin/env python
"""Sync A-share adjustment factors (复权因子) into MarketDataRepository.

The adjustment factor captures all corporate actions (dividends, splits,
rights issues) in a single time series. When applied to historical prices,
it produces forward-adjusted (前复权) or backward-adjusted (后复权) data.

Usage:
    python tools/sync_adjustment_factors.py                    # sync all from portfolio
    python tools/sync_adjustment_factors.py --symbols 600519,000002  # specific symbols
    python tools/sync_adjustment_factors.py --source-file config/candidates.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_foundation.repository import MarketDataRepository


def fetch_factor(symbol: str, factor_type: str = "qfq") -> pd.DataFrame | None:
    """Fetch adjustment factor for a single A-share symbol.

    Args:
        symbol: 6-digit A-share code (e.g. '600519').
        factor_type: 'qfq' (前复权) or 'hfq' (后复权).

    Returns:
        DataFrame with columns [date, qfq_factor] or None on failure.
    """
    import akshare as ak

    # Determine exchange prefix
    if symbol.startswith("6") or symbol.startswith("9"):
        full_symbol = f"sh{symbol}"
    elif symbol.startswith("0") or symbol.startswith("3"):
        full_symbol = f"sz{symbol}"
    else:
        full_symbol = symbol

    try:
        df = ak.stock_zh_a_daily(
            symbol=full_symbol,
            start_date="19900101",
            end_date="20991231",
            adjust=f"{factor_type}-factor",
        )
        if df.empty:
            return None
        df["asset_id"] = symbol
        df["source"] = f"akshare-{factor_type}-factor"
        return df
    except Exception as exc:
        print(f"  [ERROR] {symbol}: {exc}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Sync A-share adjustment factors")
    parser.add_argument("--symbols", help="Comma-separated stock codes")
    parser.add_argument("--source-file", help="YAML file with asset list")
    parser.add_argument("--factor-type", default="qfq", choices=["qfq", "hfq"])
    args = parser.parse_args()

    # Resolve symbols
    symbols: list[str] = []
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
    elif args.source_file:
        import yaml
        with open(args.source_file, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        assets = data.get("assets", data.get("universe", {}).get("assets", []))
        for a in assets:
            sym = a.get("symbol", "") if isinstance(a, dict) else str(a)
            if sym and any(sym.startswith(p) for p in ("6", "0", "3", "sh", "sz")):
                symbols.append(sym)
    else:
        # Default: load from portfolio
        from src.core.paths import PROJECT_ROOT
        import yaml
        portfolio_path = PROJECT_ROOT / "local" / "portfolio.yaml"
        if not portfolio_path.exists():
            portfolio_path = PROJECT_ROOT / "config" / "portfolio.yaml"
        if portfolio_path.exists():
            with open(portfolio_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for sym in data.get("positions", {}):
                if any(sym.startswith(p) for p in ("6", "0", "3", "sh", "sz")):
                    symbols.append(sym)

    if not symbols:
        print("No A-share symbols found. Use --symbols or --source-file.")
        return

    # Remove duplicates and prefixes for API calls
    clean_symbols = [s.replace("sh", "").replace("sz", "") for s in symbols]
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
            )
            print(f"OK ({len(df)} rows)")
        except Exception as exc:
            print(f"save error: {exc}")


if __name__ == "__main__":
    main()
