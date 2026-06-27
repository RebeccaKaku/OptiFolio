# OptiFolio AI Context

> Current architecture source of truth. Last updated: 2026-06-28.
> Read `docs/PRODUCT_VISION_AND_EXECUTION_PLAN.md` before proposing product work.

## Project identity

- OptiFolio owns the private portfolio book, valuation, analytics, risk, and UI.
- The independent private repository `RebeccaKaku/FinDataProvider` owns external
  data fetching, canonical storage, quality checks, and ingestion scheduling.
- OptiFolio runs on Windows; the staged provider runs in WSL on port 8020.
- The FastAPI dashboard runs on port 8011.

## Hard architecture boundary

```text
FinDataProvider (WSL/Linux)
  adapters -> canonical store -> quality -> worker -> authenticated HTTP v1
                                      |
                                      v
OptiFolio (Windows)
  HttpMarketDataClient -> valuation/services -> FastAPI/dashboard
  portfolio_book.sqlite ----------------------^
```

Rules:

1. Application code accesses market/reference data only through
   `src.infrastructure.MarketDataGateway`.
2. The production implementation is `HttpMarketDataClient`.
3. Never recreate `packages/findata`, import `findata`, read provider Parquet
   files, or run provider adapters from this repository.
4. There is no local market-data fallback. Provider outages become
   `DATA_SERVICE_UNAVAILABLE`.
5. Only public asset IDs and asset types may be sent to FinDataProvider. Never
   send accounts, quantities, market values, balances, transactions, or notes.
6. `local/portfolio_book.sqlite` is authoritative private runtime state.
7. `local/findata_client.json` may hold the provider URL/token and is ignored by
   Git. Environment variables are `FINDATA_BASE_URL` and `FINDATA_API_TOKEN`.

## Current repository map

```text
packages/
  optifolio_contracts/   shared identifier, quality, FX, and schema contracts
src/
  infrastructure/       FinDataProvider HTTP gateway
  domain/               pure financial domain types
  core/                 valuation and private-book infrastructure
  analytics/            exposure, risk, returns, reconciliation, allocation
  services/             application orchestration
  api/                  FastAPI and dashboard routes
  research/             research adapters and backtests
tools/
  scheduler.py          valuation/risk/quality workflow; never ingests data
tests/
local/
  portfolio_book.sqlite private durable state
```

Dependency direction:

```text
optifolio_contracts <- infrastructure/core/domain <- services <- api
```

`packages/` must not import `src/`. `optifolio_contracts` remains free of
application and provider runtime dependencies.

## FinDataProvider HTTP contract

The client consumes authenticated `/v1` endpoints for:

- asset catalog and asynchronous asset registration;
- prices, returns, FX, observations, metadata, fees, and dividends;
- quality issues, stale checks, missing-data reports, and ingestion job status.

Price requests are batch-first. Sparse matrices use JSON `null`, never `NaN`.
A missing asset is registered for asynchronous ingestion; requests do not
perform synchronous web scraping.

## Private book and valuation

- `src/core/portfolio_book_db.py` owns the versioned SQLite private book.
- `src/core/valuation.py` performs date-aware portfolio valuation from a batch
  price matrix and dated FX.
- `src/services/book_valuation_service.py` combines manual values, public
  prices/NAVs, and historical carry-forward candidates.
- `src/services/my_money_service.py` powers the trusted home summary.
- Currency values crossing service boundaries must be valid three-letter codes.

## Service and API rules

- Build the singleton service graph through
  `src/services/application.py::get_application_services`.
- Services return `success()` / `failure()` payloads.
- FastAPI handlers translate provider outages to HTTP 503.
- Keep provider calls out of application startup.
- Use logging, not `print`, in application code.

## Validation

```powershell
python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider
python tools/privacy_scan.py --strict --with-detect-secrets
```

Boundary checks must prove:

- `packages/findata` does not exist;
- application modules do not import `findata`;
- production market-data code does not read `local/findata`;
- provider secrets and private runtime data are not tracked.

## Migration traps

- Historical documents may mention the former embedded FinData package. Treat
  those sections as historical unless this document explicitly adopts them.
- Do not restore deleted `sync_*`, ingestion, timezone migration, or bank health
  tools here; those responsibilities belong in FinDataProvider.
- `tools/scheduler.py` may inspect provider health/quality but must not fetch or
  write market data.
- Do not add compatibility fallbacks that silently revive the old architecture.
