# FinData Orchestration — Scheduling & Dispatch

## Components

### Orchestrator (`orchestrator.py`)
- `schedule(asset_ids)` — scan staleness → generate FetchTask list
- `dispatch(tasks)` — execute with rate limiting + fallback chains
- `full_scan()` — schedule + dispatch all known assets in one call

### Cadence (`cadence.py`)
Per-asset-type update schedules:

| Asset Type | Frequency | Trigger (UTC) | Max Stale |
|-----------|-----------|---------------|-----------|
| US equity | daily | 21:30 (after NY close) | 28h |
| CN stock | daily | 07:30 (after Shanghai close) | 28h |
| CN fund | daily T+1 | 01:00 | 36h |
| Forex | hourly | — | 4h |
| Bank WMP | daily | 12:00 | 28h |
| Crypto | hourly | — | 2h |

### Rate Limiter (`rate_limiter.py`)
Per-provider limits:
- akshare-sina: 10 req/s
- akshare-eastmoney: 3 req/s
- BOC/BOSC/ICBC APIs: 1 req/s
- yfinance: 2 req/s

### Fallback (`fallback.py`)
Ordered provider chains:
```text
cn_stock:  eastmoney → sina → tencent
us_equity: sina (only source behind GFW)
forex:     boc-sina
bank_wmp:  primary API → cached/snapshot
```

### Ingest (`ingest.py`)
Batch portfolio ingestion via FinData pipeline.
- `ingest_portfolio(symbols, years)` — fetch all holdings, route through QualityGate
- CLI: `python tools/ingest_portfolio_prices.py --years 2`

## Usage

```python
from FinData.orchestration import Orchestrator

orch = Orchestrator()
results = orch.full_scan()
# → {asset_id: FetchResult, ...}
```

## Design Note
The `ingest.py` module bypasses rate limiting and fallback chains.
It is suitable for CLI-driven batch ingestion. For scheduled/recurring
ingestion, use `Orchestrator.schedule()/dispatch()`.
