# Local private workspace

This directory contains OptiFolio-owned private state only:

- `portfolio_book.sqlite`: accounts, products, confirmed snapshot batches, positions, and cash
- local exports and private application configuration
- optional `findata_client.json` containing `base_url` and `api_token`

Portfolio holdings are loaded exclusively from the latest confirmed SQLite batch. YAML holdings are unsupported.

Market data does **not** belong here. Prices, observations, provider caches, ingestion logs, and quality reports are owned by the independent FinDataProvider service.

Example git-ignored client configuration:

```json
{
  "base_url": "http://127.0.0.1:8020",
  "api_token": "replace-with-provider-token"
}
```

Prefer environment variables `FINDATA_BASE_URL` and `FINDATA_API_TOKEN` for deployed processes.
