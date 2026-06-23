# OptiFolio Runnable Architecture Foundation

This is the runnable architecture. The goal is to keep the asset-allocation core
independent from data providers, storage engines, and research frameworks.

Last updated: 2026-06-23 (FinData → packages migration).

## Runtime Path

1. Provider data is fetched by `packages/findata/findata/adapters/` (akshare, yfinance, ccxt, BOC, BOSC, ICBC).
2. Every adapter returns `FetchResult` — never empty DataFrame without metadata.
3. `CanonicalStore.accept()` runs QualityGate (9 checks) → normalizes → saves via `MarketDataRepository`.
4. `packages/findata/findata/serving/DataProvider` exposes prices, ohlcv, returns, metrics, FX rates.
5. `findata` fd singleton is the ONLY public data API (`from findata import fd`).
6. `PortfolioServiceV2` consumes fd for date-aware valuation.
7. FastAPI exposes the service layer on port 8011.
8. `PortfolioBookDatabase` (v8 SQLite, `local/`) stores personal accounts, products, snapshots, cashflows — strictly separate from market data.
9. Analytics pipeline: `book_valuation → reconciliation → currency_aggregation → return_attribution` (all pure functions).

## Module Boundaries

- `packages/findata/`: **self-contained data department** — adapters, store, orchestration, serving. The fd singleton is the only public API.
- `packages/optifolio_contracts/`: **pure types** — identifiers, quality enums, market data columns, sources, datasets. stdlib only.
- `src/domain/`: framework-independent portfolio objects (products, positions, instruments, series).
- `src/analytics/`: risk analytics — alerts, exposure, concentration, FX, liquidity, returns, rules, screening.
- `src/research/`: backtesting engine and future research adapters.
- `src/services/`: application orchestration only; no quant math should live here.
- `src/core/portfolio_book_db.py`: Personal book — versioned SQLite for accounts, products, snapshots, cashflows. Strictly separate from findata.
- `src/core/book_valuation.py`: Valuation source priority engine (DS-012, pure function).
- `src/analytics/reconciliation.py`: Snapshot pair reconciliation (DS-011).
- `src/analytics/currency_aggregation.py`: Dual-currency aggregation (DS-013).
- `src/analytics/return_attribution.py`: Return + FX decomposition (DS-014).
- `src/api/`: FastAPI routes (port 8011); no business logic here.
- `app.py`: **FROZEN** legacy Streamlit dashboard — do not edit.

## Dependency Policy

```
optifolio_contracts (stdlib only)
    ↑
findata (pandas, numpy, duckdb, akshare, yfinance)
    ↑
src/ (FastAPI, services, analytics, core, domain)
```

**Never reverse.** `packages/` must NOT import from `src/`.

DuckDB, Pandera, vectorbt, and PyPortfolioOpt are project dependencies, but heavy
imports should stay behind service or repository boundaries. The API must still
be importable enough for health checks even if optional quant dependencies are
missing from a developer's Python environment.

## Deferred

- Qlib export remains a placeholder until factor or ML research becomes a core workflow.
- ArcticDB is deferred until data volume or versioning requirements justify it.
- Event-driven engines such as Backtrader/Zipline are deferred until execution
  simulation becomes more important than allocation research.
