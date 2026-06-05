# OptiFolio Runnable Architecture Foundation

This is the runnable architecture. The goal is to keep the asset-allocation core
independent from data providers, storage engines, and research frameworks.

Last updated: 2026-06-05 (added FinData, reflected current state).

## Runtime Path

1. Provider data is fetched by `FinData/adapters/` (akshare, yfinance, ccxt, BOC, BOSC, ICBC).
2. Every adapter returns `FetchResult` — never empty DataFrame without metadata.
3. `CanonicalStore.accept()` runs QualityGate (8 checks) → normalizes → saves via `MarketDataRepository`.
4. `FinData/serving/DataProvider` exposes prices, ohlcv, returns, metrics, FX rates.
5. `FinData` fd singleton is the ONLY public data API (`from FinData import fd`).
6. `PortfolioServiceV2` consumes fd for date-aware valuation.
7. FastAPI exposes the service layer on port 8011.

## Module Boundaries

- `FinData/`: **self-contained data department** — adapters, store, orchestration, serving. The fd singleton is the only public API.
- `src/data_foundation/`: canonical schema, Pandera validation, MarketDataRepository (DuckDB + Parquet). Used BY FinData, not instead of it.
- `src/domain/`: framework-independent portfolio objects (products, positions, instruments, series).
- `src/analytics/`: risk analytics — alerts, exposure, concentration, FX, liquidity, returns, rules, screening.
- `src/research/`: backtesting engine and future research adapters.
- `src/services/`: application orchestration only; no quant math should live here.
- `src/api/`: FastAPI routes (port 8011); no business logic here.
- `portfolio/`: existing optimization algorithms (PyPortfolioOpt, cvxpy).
- `app.py`: **FROZEN** legacy Streamlit dashboard — do not edit.

## Dependency Policy

DuckDB, Pandera, vectorbt, and PyPortfolioOpt are project dependencies, but heavy
imports should stay behind service or repository boundaries. The API must still
be importable enough for health checks even if optional quant dependencies are
missing from a developer's Python environment.

## Deferred

- Qlib export remains a placeholder until factor or ML research becomes a core workflow.
- ArcticDB is deferred until data volume or versioning requirements justify it.
- Event-driven engines such as Backtrader/Zipline are deferred until execution
  simulation becomes more important than allocation research.
