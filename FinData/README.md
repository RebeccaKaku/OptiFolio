# FinData — Self-Contained Financial Data Department

## Architecture

```text
adapters/          → "Go get data from this provider, fast."
store/             → "Validate this data, reject bad data, store it."
orchestration/     → "Decide WHAT to fetch and WHEN."
serving/           → "Give me prices, returns, metrics for this asset."
```

## Quick Use

```python
from FinData import fd

# Raw data
prices = fd.prices("AAPL", start="2024-01-01")    # → pd.Series
panel  = fd.panel(["AAPL", "QQQ"], start="2024-01-01")  # → pd.DataFrame

# Transforms
returns = fd.returns("AAPL", start="2024-01-01")   # → pd.Series (pct_change)
metrics = fd.metrics("AAPL", "all")                 # → dict of 8 metrics

# Rates
rate = fd.rate("1y_cn")           # → dict {value, source, warning}
fx   = fd.fx_rate("USD", "CNY")   # → float

# Export
csv = fd.export("AAPL", format="csv")  # → CSV string
```

## Data Flow

```text
orchestrator.schedule()
    │
    ▼
adapters.fetch(FetchRequest)
    │
    ▼
store.QualityGate.inspect()
    │  REJECT → log, do NOT overwrite
    ▼  PASS
store.CanonicalStore.accept()
    │
    ▼
data/processed/market/market_prices.parquet
    │
    ▼
serving.DataProvider.prices() / metrics() / export()
```

## Key Conventions

1. **Every adapter returns FetchResult** — never an empty DataFrame without metadata.
2. **QualityGate runs 8 checks on every write** — empty data is ALWAYS rejected.
3. **Fetchers do NOT validate, do NOT store, do NOT retry** — that's storage and orchestration's job.
4. **All data paths are under FinData/data/** — organized by lifecycle: raw → processed → metadata.
5. **The fd singleton is the ONLY public API** — algorithms never import adapters directly.

## Adding a New Data Source

1. Create `FinData/adapters/new_source.py` implementing `FetcherProtocol`
2. Register in `FinData/adapters/__init__.py` → `FETCHER_REGISTRY`
3. Add update cadence to `FinData/orchestration/cadence.py`
4. Run tests

See `FinData/adapters/README.md` for the full guide.

## Current Coverage

| Asset Class | Adapter | Discovery | OHLCV/NAV | Metadata |
|-------------|---------|:---------:|:---------:|:--------:|
| US Equities | us_equity.py | ✅ Sina | ✅ full history | partial |
| CN Stocks | cn_stock.py | ✅ multi-source | ✅ full history | ✅ |
| CN Funds | cn_fund.py | ✅ fund list cache | ✅ (NAV forced to OHLCV) | ✅ |
| BOC Wealth Mgmt | boc_wm.py | ✅ JSON API | ✅ single-request full | ✅ |
| BOC Structured | boc_structured.py | ✅ HTML scrape | N/A (prospectus) | ✅ 16 fields |
| BOSC Wealth Mgmt | bosc.py | ✅ GET API + snapshot | ✅ paginated | ✅ 100+ fields |
| ICBC Wealth Mgmt | icbc.py | ❌ hardcoded list | ✅ paginated | partial |
| Forex | forex.py | ✅ PBOC daily | ✅ daily | ✅ |
| Crypto | — | ❌ not yet adapted | — | — |

## Tests

```bash
C:\Users\Z\miniconda3\envs\optifolio313\python.exe -m pytest tests/test_findata_*.py -v
```
