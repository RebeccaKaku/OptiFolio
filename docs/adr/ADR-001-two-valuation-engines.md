# ADR-001: Two ValuationEngines Architecture

**Status**: accepted  
**Date**: 2026-06-20  
**Deciders**: Codebase audit

## Context

OptiFolio has two separate `ValuationEngine` classes:

1. `src/core/valuation.py` — Date-aware portfolio valuation using `MarketDataRepository` (DuckDB/Parquet). Reads market prices and FX rates, computes total portfolio value.
2. `src/core/book_valuation.py` — Priority-based valuation engine for single positions. Selects best `ValuationCandidate` (manual > public NAV > last known) for each position.

Both are named `ValuationEngine` and produce a type called `ValuationResult`, but with completely different structures.

## Decision

**Keep both engines separate** for the following reasons:

1. **Different data sources**: Engine 1 reads from market data (Parquet/DuckDB). Engine 2 selects from multiple self-reported valuation sources (manual entries, bank NAVs, carry-forward estimates). They are not mergeable without losing the priority-based selection logic.

2. **Different scope**: Engine 1 values the entire portfolio at once. Engine 2 values individual positions independently. Engine 1's output feeds `ExposureAnalyzer` and dashboard. Engine 2's output feeds `MyMoneyService` and `CurrencyAggregator`.

3. **Rename to disambiguate**:
   - `valuation.py::ValuationEngine` → `MarketValuationEngine`
   - `book_valuation.py::ValuationEngine` → `BookValuationEngine`
   - `valuation.py::ValuationResult` → `MarketValuationResult` (or keep as the canonical one in Phase 3)
   - `book_valuation.py::ValuationResult` → `BookValuationResult` (or merge into canonical in Phase 3)

## Consequences

- Two engines remain, but with distinct names to prevent import confusion.
- The unified `ValuationResult` (Phase 3.1) will serve both engines as a common output format, with quality metadata from the book path and market data from the market path.
- Documentation distinguishes them clearly: `MarketValuationEngine` for market-data-driven valuation, `BookValuationEngine` for priority-based self-reported valuation.

## Alternatives Considered

**Merge both into one engine**: Rejected. The book engine's priority-based candidate selection (manual > NAV > carry-forward) is fundamentally different logic from the market engine's direct price lookback. Merging would create a god-class with confusing branching.
