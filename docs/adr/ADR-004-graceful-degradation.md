# ADR-004: Graceful Degradation for Unpriced Assets

**Status**: accepted  
**Date**: 2026-06-20

## Context

When `ValuationEngine` encounters a position with no market price (e.g., bank WMP), it raises `NoPriceDataError`, causing the entire portfolio valuation to fail with HTTP 422. A single unpriceable asset blocks the entire dashboard.

This is semantically wrong: the portfolio HAS value, we just can't compute part of it. The dashboard should show what CAN be valued and flag what cannot.

## Decision

**Add `strict` mode to `ValuationEngine.value()`**:

- `strict=True` (default, current behavior): All assets must have prices. Missing price → `NoPriceDataError`.
- `strict=False` (dashboard mode): Skip unpriceable assets, value the rest. Return:
  - `unpriced: List[str]` — asset_ids that were skipped
  - Partial `ValuationResult` for the priceable subset

**Dashboard behavior**: 
- Show "¥X 可定价" for the valued portion
- Show "N 个资产暂无市价" with the list of skipped assets
- Never 422 due to missing prices

## Consequences

- `ValuationResult` gains `unpriced: List[str]` field
- All API endpoints default to `strict=False` for dashboard
- `strict=True` reserved for programmatic use (backtests, risk checks)
- Bank WMPs gracefully handled without requiring price data infrastructure
