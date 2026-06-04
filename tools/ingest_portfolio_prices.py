#!/usr/bin/env python
"""Ingest portfolio prices via FinData pipeline.

Usage:
    python tools/ingest_portfolio_prices.py                  # all holdings
    python tools/ingest_portfolio_prices.py --symbols AAPL   # specific
    python tools/ingest_portfolio_prices.py --years 3        # more history
    python tools/ingest_portfolio_prices.py --dry-run        # plan only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from FinData.orchestrator.ingest import ingest_portfolio


def main():
    parser = argparse.ArgumentParser(description="Ingest portfolio prices via FinData")
    parser.add_argument("--symbols", help="Comma-separated symbols")
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None

    result = ingest_portfolio(symbols=symbols, years=args.years, dry_run=args.dry_run)

    if args.dry_run:
        print(f"Would ingest {len(result.get('plan', []))} assets:")
        for p in result.get("plan", []):
            print(f"  {p}")
        return

    print(f"Ingested: {len(result['ingested'])} — {result['ingested']}")
    print(f"No data:  {len(result['no_data'])} — {result['no_data']}")
    print(f"Failed:   {len(result['failed'])} — {result['failed']}")


if __name__ == "__main__":
    main()
