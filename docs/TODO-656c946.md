# TODO — Remaining Issues

**Date**: 2026-06-24 | **Tests**: 983 passed | **Previous session**: FinData → packages refactoring + Jules cleanup

---

## P0 — Data Integrity

### 20. Remove YAML fallback from portfolio loading
**Files**: `src/services/portfolio_service_v2.py`, `src/core/paths.py`, `src/runtime/bootstrap.py`, `src/services/boc_pdf_pipeline.py`

`_load_portfolio()` currently has a SQLite → YAML fallback chain. The YAML path is migration-era crutch. The SQLite book (`local/portfolio_book.sqlite`, 192KB) is the canonical source.

- Delete `_load_holdings_from_yaml()`, `_load_cash_from_yaml()`, `_resolve_config_path()`
- `_load_portfolio()` raises if no confirmed batch exists — no silent degradation
- Remove `get_portfolio_config_path()` from `paths.py`; remove `ensure_local_portfolio()` from `bootstrap.py`
- Remove `portfolio.yaml` loading from `boc_pdf_pipeline.py`

### 21. Remove hardcoded fallback data
**Files**: `src/asset_importer.py`, `src/core/valuation.py`

- `OFFLINE_ASSET_FALLBACKS` (lines 8-14): hardcoded metadata for 6 assets. These exist in `config/asset_registry.yaml`. Delete.
- `DEFAULT_FALLBACK_RATES` (valuation.py:38): hardcoded FX rates. Audit C2 found `5y_cn` off by 2.2pp. Replace with stored-observation lookup or raise `FxRateError`.

---

## P1 — Structure Cleanup

### 19. Remove `_v2` naming suffix
**Files**: `src/services/portfolio_service_v2.py`, `src/api/fastapi_app.py`, `src/services/application.py`, all tests

- `PortfolioServiceV2` → `PortfolioService` (v1 was deleted)
- API routes: `/api/portfolio/v2/` → `/api/portfolio/`
- `EnhancedAssetManager` → `AssetManager` (`AssetManager` was deleted in Batch 1)

### 22. Simplify asset import chain (3 layers → 1)
**Files**: `src/asset_importer.py`, `src/core/enhanced_asset_manager.py`, `src/services/asset_service.py`

Current chain: `AssetImporter` → `EnhancedAssetManager` → `AssetService`. `AssetService` is a thin passthrough. `EnhancedAssetManager` delegates to `AssetImporter` + `findata.fd`. Collapse to direct `findata.fd` calls.

### 23. Wire or remove `IngestionService` stub
**Files**: `src/services/application.py`

`IngestionService` returns `{"records": [], "message": "Ingestion pipeline not yet wired"}`. Either wire to the actual orchestrator or delete the service.

---

## P2 — Duplicate Modules

### 24. Consolidate duplicate ValuationEngine and ValuationResult
**Files**: `src/core/valuation.py`, `src/core/book_valuation.py`, `src/domain/models.py`

Two `ValuationEngine` classes: `valuation.py:270` (portfolio-level) and `book_valuation.py:55` (single-asset). Two `ValuationResult` dataclasses: `domain/models.py:156` (portfolio-level) and `book_valuation.py:53` (single-asset). The CONTRACTS.md doc says "Phase 3 will merge." Phase 3 is now.

### 26. Decide fate of portfolio_history.parquet
**Files**: `src/core/portfolio_history.py`

`PortfolioHistoryTracker` writes valuation snapshots to `local/portfolio_history.parquet`. This is a separate Parquet file alongside the SQLite book. Either merge into SQLite or keep as append-only log with clear rationale.

---

## P3 — Test Hygiene

### 25. Clean up 54 test files
**Scope**: All of `tests/`

- Old identifier formats still present: bare `510300`, `000198`, `sh600519` — migrate to `fund.cn.etf.sh.510300`, `fund.cn.money.000198`, `equity.cn.sh.600519`
- Some tests reference deleted modules (`src/data_foundation`, `src/core/symbols`, `FinData`)
- `test_ghostfolio_compat.py` + `test_ghostfolio_export.py` — consolidate
- `test_findata_storage.py` + `test_findata_serving.py` — duplicate `TestFdPrices` classes (audit M4)

---

## Known Bugs (from audit, not yet verified)

| # | File | Issue |
|---|------|-------|
| B1 | `EnhancedAssetManager` → `AssetImporter` | `OFFLINE_ASSET_FALLBACKS` used as live data |
| B2 | `valuation.py:177` | Hardcoded FX fallback used before stored rates |
| B3 | `identifiers.py` + `findata/store/schemas.py` | `CANONICAL_MARKET_COLUMNS` defined in two places |
| B4 | `identifiers.py` + `findata/store/schemas.py` | `STORE_VERSION` defined in two places |

## Identifier Convention (finalized 2026-06-24)

```
equity.us.<ticker>              equity.us.aapl
equity.cn.<sh|sz|bj>.<code>    equity.cn.sh.600519
fund.cn.<subtype>.<code>        fund.cn.money.000198   (subtype from akshare 基金类型)
fund.cn.etf.<sh|sz>.<code>     fund.cn.etf.sh.510300
wmp.cn.<bank>.<code>            wmp.cn.boc.amhqlxttusd01b
fx.<base>_<quote>.spot          fx.usd_cny.spot
rate.<country>.<index>.<tenor>  rate.cn.shibor.1y
```

Subtypes: `money`, `mixed`, `bond`, `stock`, `index`, `qdii`, `fof`. No `open` — nearly all CN mutual funds are open-end; use the real type from akshare.
