# OptiFolio Current State

**Date**: 2026-06-19  
**Branch**: `main`  
**Runtime**: Python 3.14.2 (Windows)  
**Verified tests**: `905 passed` (use `python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider`)  
**FinData**: 32 Python files, self-contained, lazy fd singleton  
**Personal Book**: v8 SQLite schema, 29 public methods  

---

## One-Line Status

**905 tests green. DS-001~014 complete. M1 API+UI live, M2 analytics engine built, M3 risk penetration unblocked. PortfolioBookDatabase v8 serving 29 methods. `portfolio_core` gutted (935→232 lines), `data_core` removed, all `print()` migrated to `logging`. Jules + Codex parallel pipeline operational.**

---

## Architecture

```
FinData/                       Self-contained data dept — lazy fd singleton
  ├─ adapters/                10 fetchers + FETCHER_REGISTRY (duck typing)
  ├─ store/                   CanonicalStore + QualityGate (9 checks)
  ├─ orchestration/           Orchestrator + cadence + rate limiter
  └─ serving/                 DataProvider (delegated by fd)

src/
  ├─ analytics/               12 modules:
  │   ├─ alerts, concentration, exposure, fx_exposure, liquidity, returns, rule_engine, screening
  │   ├─ reconciliation (DS-011), return_attribution (DS-014), currency_aggregation (DS-013)
  ├─ api/                     8 files:
  │   └─ fastapi_app.py (:8011), portfolio_book_api, dashboard_api, ghostfolio_compat, static_dashboard
  ├─ core/                    21 files:
  │   ├─ portfolio_book_db.py (v8, 29 methods, accounts→products→snapshots→cashflows→backup)
  │   ├─ valuation.py (ValuationEngine + FxRateProvider)
  │   ├─ book_valuation.py (DS-012, valuation source priority)
  │   ├─ portfolio_core.py (232 lines, gutted to delegation shim)
  │   └─ enhanced_asset_manager.py (241 lines, gutted delegation)
  ├─ services/                17 files:
  │   ├─ portfolio_book_service, book_valuation_service, import_draft_service
  │   ├─ portfolio_service_v2, research_service, application (service graph)
  ├─ domain/                   products, positions, instruments, import_drafts, cashflows...
  └─ data_foundation/          MarketDataRepository (DuckDB + Parquet)

app.py                        FROZEN — Streamlit legacy, do NOT edit
tools/                        bank_health_check, sync_macro_rates, privacy_scan, scheduler...
tests/                        35+ test files
plans/deepseek/               27 DS task specs (DS-001~027)
```

---

## DS Task Progress

| Batch | Tasks | Status |
|-------|-------|--------|
| 1 — Foundation | DS-001~006C | ✅ Complete |
| 2 — API + UI | DS-007~010 | ✅ Complete |
| 3 — Trusted Home | DS-011~015 | ✅ 011~014 done, 015 retrying |
| 4 — Risk Penetration | DS-016~019 | ⛔ Blocked by 015 |
| 5 — Decision Tools | DS-020~023 | ⛔ Blocked by 019 |
| 6 — Judgment Lab | DS-024~027 | ⛔ Blocked by 023 |

**14/27 complete.**

---

## Refactoring Progress

| Item | Before | After | Status |
|------|--------|-------|--------|
| fd singleton | eager init | lazy `__getattr__` | ✅ |
| print() calls | 147 across 14 files | 0 | ✅ |
| data_core/ | 3 files | deleted | ✅ |
| enhanced_asset_manager | 948 lines | 241 lines (-75%) | ✅ |
| portfolio_core | 935 lines | 232 lines (-75%) | ✅ |
| asset_importer | 1058 lines | 168 lines (-84%) | ✅ |
| portfolio_manager.py | 329 lines | deleted | ✅ |
| fm_database.db brand | 4 files | all renamed | ✅ |
| sh/sz prefixes | 5 entries | stripped | ✅ |
| src/core/__init__.py | eager 6 imports | lazy `__getattr__` | ✅ |

---

## Verified Commands

```powershell
python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider
python tools/privacy_scan.py --strict --with-detect-secrets
python tools/bank_health_check.py
```

---

## Known Issues (pre-existing, not blocking)

- 8 asset_registry tests fail (SQLite fixture files not in git)
- 2 ds008_api tests fail (v8 schema environment mismatch)
- Numba/vectorbt requires `NUMBA_DISABLE_JIT=1` on this Windows workspace
