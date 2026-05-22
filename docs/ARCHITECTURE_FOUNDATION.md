# OptiFolio Runnable Architecture Foundation

This is the first runnable version of the long-term architecture. The goal is to
keep the asset-allocation core independent from data providers, storage engines,
and research frameworks.

## Runtime Path

1. Raw provider data is normalized into the canonical market schema.
2. Canonical market data is stored as Parquet under `data/foundation/`.
3. `MarketDataRepository` queries Parquet with DuckDB and returns price/return matrices.
4. `ResearchService` orchestrates optimization and backtesting.
5. FastAPI exposes the service layer through `/api/market/*` and `/api/research/*`.

## Module Boundaries

- `src/data_foundation/`: schema normalization, Pandera validation, Parquet storage, DuckDB queries.
- `src/domain/`: framework-independent portfolio objects.
- `src/research/`: backtesting engine and future research adapters.
- `src/services/`: application orchestration only; no quant math should live here.
- `portfolio/`: existing optimization algorithms.

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
