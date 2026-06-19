# ADR-003: Portfolio Data Source Priority

**Status**: accepted  
**Date**: 2026-06-20

## Context

Portfolio holdings can come from two sources:

1. `PortfolioBookDatabase` (SQLite) — confirmed snapshot batches from the book wizard
2. `config/portfolio.yaml` — static configuration file

The dashboard and book wizard were disconnected: the wizard wrote to SQLite, the dashboard read from YAML.

## Decision

**Priority chain**: Book DB → YAML → empty

```
_load_portfolio():
  1. Query latest confirmed batch from PortfolioBookDatabase
  2. If found AND >50% of holdings have price data → use book data
  3. Else → fall back to config/portfolio.yaml
  4. If neither exists → empty portfolio
```

**Viability gate**: Before adopting book data, check that a majority (>50%) of holdings have market prices available. This prevents the "all bank WMPs → 422" scenario.

**Cash handling**: Cash always comes from `config/portfolio.yaml` (book DB tracks cashflows but doesn't compute current balance).

## Consequences

- Book wizard data is authoritative (canonical source)
- YAML serves as demo/fallback portfolio
- Graceful degradation when book contains unpriceable products
- Future: compute cash balance from `cashflow_events` ledger in book DB
