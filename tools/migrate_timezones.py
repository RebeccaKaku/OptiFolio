#!/usr/bin/env python
"""One-shot migration script to patch timezones in market_prices.parquet."""

import sys
from pathlib import Path
import pandas as pd
import argparse

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_foundation.repository import MarketDataRepository
from src.data_foundation.schemas import infer_market_timezone, validate_market_frame

def migrate_timezones(dry_run=False):
    repo = MarketDataRepository()
    if not repo.price_path.exists():
        print(f"File not found: {repo.price_path}")
        return

    print(f"Loading {repo.price_path}...")
    df = pd.read_parquet(repo.price_path)

    total_rows = len(df)
    print(f"Processing {total_rows} rows...")

    # Identify unique assets and their inferred timezones
    assets = df['asset_id'].unique()
    asset_tz_map = {aid: infer_market_timezone(aid) for aid in assets}

    # Track changes
    changes = 0
    tz_counts = df['timezone'].value_counts().to_dict()
    print(f"Current timezone distribution: {tz_counts}")

    def update_tz(row):
        new_tz = asset_tz_map[row['asset_id']]
        if row['timezone'] != new_tz:
            return new_tz
        return row['timezone']

    # Apply changes
    new_timezones = df.apply(update_tz, axis=1)
    diff_mask = new_timezones != df['timezone']
    changes = diff_mask.sum()

    if changes == 0:
        print("No changes needed. All timezones already match inference.")
        return

    print(f"Proposed changes: {changes} rows will be updated.")

    # Show some examples of changes
    example_diffs = df[diff_mask].head(10)
    for idx, row in example_diffs.iterrows():
        new_tz = asset_tz_map[row['asset_id']]
        print(f"  {row['asset_id']}: {row['timezone']} -> {new_tz}")

    if dry_run:
        print("[DRY RUN] No changes saved.")
    else:
        df['timezone'] = new_timezones
        print("Validating patched data...")
        try:
            validate_market_frame(df)
        except Exception as e:
            print(f"Validation failed: {e}")
            return

        print(f"Saving patched data to {repo.price_path}...")
        df.to_parquet(repo.price_path, compression="snappy", index=False)
        print("Migration complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate market data timezones")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without saving")
    args = parser.parse_args()

    migrate_timezones(dry_run=args.dry_run)
