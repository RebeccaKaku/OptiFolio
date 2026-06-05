# FinData Store — Canonical Storage with Quality Gate

## Components

### CanonicalStore (`repository.py`)
Wraps MarketDataRepository (DuckDB/Parquet) with QualityGate.
- `accept()` — quality check → normalize → save, or REJECT
- `get_prices()` / `get_returns()` — DuckDB-accelerated queries
- `list_assets()` / `missing_report()` — data health

### QualityGate (`quality.py`)
**8 checks** on every incoming DataFrame before storage:

| # | Check | Failure Mode |
|---|-------|-------------|
| 1 | Non-empty | REJECT — silent network failure |
| 2 | Has close/adj_close column | REJECT — wrong provider output |
| 3 | Row count reasonable | FLAG — suspiciously few rows |
| 4 | NaN proportion | REJECT — >50% missing close prices |
| 5 | Positive prices | REJECT — close ≤ 0 is corrupt data |
| 6 | Time reversal | REJECT — newer data already exists |
| 7 | Price spikes | FLAG — single-day change >50% |
| 8 | Duplicate data | REJECT — identical to stored data |

**Critical rule: EMPTY DATA NEVER OVERWRITES GOOD DATA.** When a fetcher returns
an empty DataFrame (network glitch), QualityGate rejects it and logs a warning.
The existing data on disk is preserved.

### Schemas (`schemas.py`)
Canonical column definitions imported from `src/data_foundation/schemas.py`.
All stored data conforms to:

```text
asset_id, date, open, high, low, close, adj_close, volume, currency, source, timezone
```

### Ingestion Log (`ingestion_log.py`)
Tracks every ingestion run:
- `run_id`, `provider`, `asset_id`, `status`, `rows`, `started_at`, `finished_at`, `errors`

### Portfolio Ledger (`portfolio_ledger.py`)
Structured daily holdings snapshot:
- `account_id`, `asset_id`, `quantity`, `cost_basis`, `currency`, `as_of`

## Data Lifecycle

```text
raw (bronze)        →  provider output, AS-IS, never modified
    │
processed (silver)  →  cleaned, normalized, validated (market_prices.parquet)
    │
metadata            →  ingestion_runs, data_quality_issues, provider_watermarks
```

## Usage

```python
from FinData.store.repository import CanonicalStore

store = CanonicalStore()
report = store.accept(df, asset_id="AAPL", source="yahoo", currency="USD")
if report.passed:
    print("Stored")
else:
    print(f"Rejected: {report.reject_reasons}")
```
