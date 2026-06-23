# ADR-002: Asset Classification Taxonomy

**Status**: accepted  
**Date**: 2026-06-20

## Context

OptiFolio has three classification systems that disagree:

1. `ExposureAnalyzer.classify()` (exposure.py) classifies `asset_type` → asset class bucket (equity/fixed_income/cash/alternative)
2. `ConcentrationAnalyzer._map_asset_class()` (concentration.py) maps to different buckets — CN funds go to "fund" not "equity"
3. `AssetManager` has its own type grouping (cn_stock → [cn_stock_sh, cn_stock_sz])

The same asset (e.g., 510300 沪深300ETF) is "equity" in exposure but "fund" in concentration.

## Decision

**Create a single `AssetClassifier` (`src/core/classifier.py`)** as the authoritative source for all asset classification:

```python
class AssetClassifier:
    def to_exposure_bucket(asset_type: str, metadata: dict) -> str:
        """Map to exposure asset class: equity/fixed_income/cash/alternative"""
    
    def to_concentration_bucket(asset_type: str, metadata: dict) -> str:
        """Map to concentration class: equity/fund/bond/cash/alternative"""
```

**Classification rule**: All classification MUST use `fund_type_raw` from crawler metadata when available (for CN funds). No heuristic guessing based on code patterns.

**CN fund resolution**: Use crawler's `fund_type_raw` field:
- 货币型 → cash
- 债券型 → fixed_income  
- 指数型/股票型/混合型 → equity
- Default → equity

## Consequences

- `ExposureAnalyzer.classify()` and `ConcentrationAnalyzer._map_asset_class()` delegate to `AssetClassifier`.
- Adding a new asset type requires updating one file, not three.
- Classification decisions have a single audit trail.
