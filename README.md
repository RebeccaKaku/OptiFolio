# OptiFolio — Personal Asset Risk & Allocation Engine

Multi-asset portfolio management with date-aware valuation, risk analytics, and a FastAPI application layer.

**Direction**: risk engine first, allocation advice second.

## Runtime services

OptiFolio owns the private portfolio book and analytics. Market-data ingestion and storage are provided by the independent private repository [`RebeccaKaku/FinDataProvider`](https://github.com/RebeccaKaku/FinDataProvider).

```text
FinDataProvider (remote)       OptiFolio (this repository)
fetch -> quality -> store  ->  HTTP client -> valuation -> risk -> UI
                               local/portfolio_book.sqlite
```

No OptiFolio process reads remote Parquet files or imports provider adapters. The only boundary is the versioned HTTP API.

## Quick start

```bash
conda activate optifolio313
pip install -r requirements.txt

# Required; alternatively use git-ignored local/findata_client.json
set FINDATA_BASE_URL=http://127.0.0.1:8020
set FINDATA_API_TOKEN=<provider-token>

python tools/start_app.py          # FastAPI on port 8011
python tools/scheduler.py          # valuation/risk/snapshot only
```

`tools/scheduler.py` checks FinDataProvider availability but never performs ingestion. Data scheduling belongs to FinDataProvider's worker.

## Architecture

```text
packages/optifolio_contracts/  pure valuation and identifier contracts
src/domain/                    portfolio dataclasses
src/core/                      valuation, calendars, fees, corporate actions
src/analytics/                 exposure, concentration, liquidity, attribution
src/infrastructure/            FinDataProvider HTTP gateway
src/services/                  business orchestration
src/api/                       FastAPI routes and static UI
```

Dependency direction: `contracts <- domain/core/analytics <- services <- api`; infrastructure implements service-facing protocols.

## Important API routes

- `GET /health`
- `GET /api/book/summary`
- `GET /api/portfolio/v2/value?as_of=YYYY-MM-DD`
- `GET /api/market/prices?assets=AAPL,QQQ`
- `GET /api/market/returns`
- `GET /api/data/quality`

When FinDataProvider is unavailable, market-dependent routes return `503 DATA_SERVICE_UNAVAILABLE`; they never substitute zero or an embedded local cache.

## Development

```bash
python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider
python tools/privacy_scan.py --strict --with-detect-secrets
```

Real portfolio data, API tokens, and local state live in git-ignored `local/`. Market data does not live in this repository.
