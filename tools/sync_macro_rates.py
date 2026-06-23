#!/usr/bin/env python
"""Sync interbank and policy-rate macro series into canonical observations.

Examples:
    python tools/sync_macro_rates.py --dry-run
    python tools/sync_macro_rates.py --series RATE_SHIBOR_CNY_3M,RATE_LIBOR_USD_3M
    python tools/sync_macro_rates.py --groups interbank,policy --start 20240101

All rates are stored as decimals, not percentage points:
    2.35% -> 0.0235

This tool is now a thin CLI wrapper around ``findata.rates``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from findata.rates import (  # noqa: F401
    FRED_REPLACEMENT_SPECS,
    INTERBANK_SPECS,
    POLICY_RATE_SPECS,
    _SPEC_BY_ID_CANONICAL,
    _canonical_series_id,
    FredRateSpec,
    InterbankSpec,
    PolicyRateSpec,
    _filter_dates,
    fetch_fred_rate,
    fetch_interbank,
    fetch_policy_rate,
    macro_series_catalog,
    normalize_fred_rate_frame,
    normalize_interbank_frame,
    normalize_policy_rate_frame,
    sync_rate_series,
    sync_rates,
)
from findata.store import MarketDataRepository


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync SHIBOR/LIBOR/EURIBOR/HIBOR, policy rates, and LIBOR replacement rates"
    )
    parser.add_argument(
        "--groups",
        default="interbank,policy,replacements",
        help="Comma-separated groups: interbank,policy,replacements. Default: all.",
    )
    parser.add_argument(
        "--series",
        help="Comma-separated series IDs to sync. Default: all selected groups.",
    )
    parser.add_argument("--start", help="Start date YYYYMMDD.")
    parser.add_argument("--end", help="End date YYYYMMDD.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and preview without saving.")
    args = parser.parse_args()

    groups = {g.strip().lower() for g in args.groups.split(",") if g.strip()}
    invalid_groups = groups - {"interbank", "policy", "replacements"}
    if invalid_groups:
        raise SystemExit(f"Unknown group(s): {sorted(invalid_groups)}")

    requested = {s.strip() for s in args.series.split(",")} if args.series else None

    all_known_legacy = {spec.series_id for spec in (*INTERBANK_SPECS, *POLICY_RATE_SPECS, *FRED_REPLACEMENT_SPECS)}
    all_known_canonical = set(_SPEC_BY_ID_CANONICAL.keys())
    all_known = all_known_legacy | all_known_canonical
    if requested:
        missing = requested - all_known
        if missing:
            raise SystemExit(f"Unknown series ID(s): {sorted(missing)}")

    print(f"Sync macro rates: groups={sorted(groups)}, series={sorted(requested) if requested else 'all'}")
    if args.start or args.end:
        print(f"Date filter: {args.start or '-inf'} .. {args.end or '+inf'}")
    if args.dry_run:
        print("[DRY RUN — no data will be saved]")

    results = sync_rates(
        series_ids=requested,
        groups=groups,
        repo=MarketDataRepository(),
        start=args.start,
        end=args.end,
        dry_run=args.dry_run,
    )

    ok_count = sum(1 for rows, _ in results.values() if rows > 0)
    total_rows = sum(rows for rows, _ in results.values())
    print(f"Done: {ok_count}/{len(results)} series, {total_rows} rows")


if __name__ == "__main__":
    main()
