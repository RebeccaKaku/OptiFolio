# OptiFolio runnable architecture

Last updated: 2026-06-27.

## Deployment topology

```text
FinDataProvider (WSL/Linux, port 8020)
  adapters -> ingestion jobs -> quality gate -> Parquet/control.sqlite -> v1 HTTP API
                                      |
                                      v
OptiFolio (port 8011)
  HttpMarketDataClient -> services -> valuation/analytics -> API/UI
  PortfolioBookDatabase (private local SQLite)
```

FinDataProvider is developed and deployed from the private `RebeccaKaku/FinDataProvider` repository. Its storage and scheduler are authoritative for prices, FX, observations, metadata, fees, dividends, freshness, and ingestion status.

OptiFolio owns portfolio identity, positions, cash, valuation policy, risk, decisions, and presentation. It neither embeds provider code nor mounts the provider data directory.

## Request behavior

- Existing data is read through `/v1/*` endpoints.
- A missing asset is explicitly registered through `/v1/assets/ensure`; the first application response remains pending/missing rather than blocking or inventing a price.
- Service/network failure becomes `DATA_SERVICE_UNAVAILABLE`.
- There is no local market-data fallback.

## Security boundary

Only canonical asset ID and optional asset type cross the service boundary. Portfolio quantities, accounts, cash, snapshots, and reporting totals never leave OptiFolio. Both services use a Bearer token over localhost in WSL and an encrypted private network on the eventual Linux host.

## Scheduling

- FinDataProvider worker: fetching, macro/FX refresh, quality checks, ingestion jobs.
- OptiFolio scheduler: provider readiness check, valuation, history, risk rules, alerts, and private snapshots.
