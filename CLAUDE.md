# OptiFolio contributor rules

## Non-negotiable boundaries

1. `local/portfolio_book.sqlite` is the only portfolio source of truth. Do not recreate YAML holdings fallbacks.
2. FinDataProvider is an independent service. Application code must use `src.infrastructure.HttpMarketDataClient` or `MarketDataGateway`; never import `findata`, provider adapters, DuckDB, or remote storage files.
3. Reads do not silently become zero. Missing data, pending ingestion, and service outages must remain distinct states.
4. Never send account names, quantities, market values, cash balances, or other portfolio information to FinDataProvider. Only asset IDs/types may be registered.
5. `src/api` contains transport code, `src/services` orchestration, and `src/core`/`src/analytics` financial logic.
6. Add tests at the boundary: HTTP client decoding, error mapping, and fake-gateway business tests.
7. Keep secrets and data out of Git. Supported configuration is environment variables or git-ignored `local/findata_client.json`.

## Runtime configuration

- `FINDATA_BASE_URL` defaults to `http://127.0.0.1:8020`.
- `FINDATA_API_TOKEN` is required for market-data operations.
- A remote outage maps to `DATA_SERVICE_UNAVAILABLE` and HTTP 503.

## Repository map

- `packages/optifolio_contracts/`: lightweight app-side contracts and valuation enums.
- `src/infrastructure/market_data_client.py`: sole FinDataProvider adapter.
- `src/core/portfolio_book_db.py`: private SQLite portfolio book.
- `src/core/valuation.py`: date-aware valuation through `MarketDataGateway`.
- `src/services/application.py`: dependency injection graph.
- `tools/scheduler.py`: portfolio valuation/risk/snapshot scheduler; no ingestion.

## Validation

```bash
python -m compileall -q src tools
python -m pytest tests/test_market_data_client.py tests/test_fastapi_app.py -q -p no:cacheprovider
python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider
```

Do not reintroduce `packages/findata/`, `tools/sync_*`, or direct provider dependencies after extraction.
