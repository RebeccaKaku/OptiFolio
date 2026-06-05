# OptiFolio Current State

**Date**: 2026-06-05 (post comprehensive audit)
**Branch**: `master`
**Package version**: `0.2.0`
**Runtime**: Python 3.14.2 (conda env)
**Verified tests**: `592 passed, 30 skipped, 0 failures`
**FinData**: 32 Python files, self-contained data department
**Recent commits**: `9de41c0` (bug fixes from audit), `55426bf` (feature batch)

Use this document as the live project map until the next review pass.

---

## One-Line Status

FinData is self-contained and operational. 592 tests green. Comprehensive audit completed (2026-06-05): 4 critical bugs fixed, 29 issues catalogued across 3 severity tiers. **Top priority: wire the data foundation end-to-end — make quality checks, exposure analytics, and alerts actually reachable from the API, and replace dashboard random data with real data.**

---

## Verified Commands

Reliable local test command:

```powershell
python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider
```

Current result: **592 passed, 30 skipped, 2 warnings** (67s)

---

## Current Architecture

```
app.py                        # legacy Streamlit dashboard, FROZEN — do not add features
src/api/fastapi_app.py        # HTTP API entrypoint (FastAPI, port 8011)
src/api/ghostfolio_compat.py  # Ghostfolio-compatible API surface (NEW)
src/api/static_dashboard.py   # static HTML dashboard generator (NEW)
src/services/                 # business service facade (11 modules)
src/core/                     # asset, portfolio, valuation, fee, database, dashboard engine
src/analytics/                # alerts, exposure, concentration, fx, liquidity, returns, rules, screening
src/analytics/exposure.py     # exposure/concentration analyzer (NEW)
src/data_foundation/          # canonical market data schema + Parquet/DuckDB repository
src/research/                 # backtest engine, Qlib adapter placeholder
FinData/                      # self-contained data department (32 files)
  adapters/                   # 10 provider fetchers + protocol + registry
  store/                      # CanonicalStore, QualityGate (8 checks), ingestion log, portfolio ledger
  orchestration/              # scheduler, cadence, rate limiter, fallback chains
  serving/                    # DataProvider — fd.prices(), fd.panel(), fd.returns(), fd.metrics()
config/                       # YAML configs (asset_registry, candidates, settings, secrets templates)
tools/                        # CLI utilities (start_app, scheduler, export, privacy_scan, etc.)
tests/                        # 31 test files
```

**Direction**: keep new work in `src/api/`, `src/services/`, `src/analytics/`, `FinData/`; treat `app.py` as frozen legacy.

---

## What Changed This Round (commit 55426bf → 9de41c0)

### New Modules
| Module | Lines | Purpose |
|--------|-------|---------|
| `src/analytics/exposure.py` | 209 | Asset class, currency, issuer exposure/concentration analysis |
| `src/api/ghostfolio_compat.py` | 351 | Ghostfolio-compatible API endpoints (/api/v1/portfolio/*) |
| `src/api/static_dashboard.py` | 213 | Static HTML dashboard with JavaScript frontend |
| `FinData/store/quality.py` | +275 | QualityGate framework expansion |

### Bug Fixes (commit 9de41c0)
| Bug | Severity | Fix |
|-----|----------|-----|
| `orchestrator.py:127` — `from FinData.adapters.registry` (file nonexistent) | **CRASH** | Fixed to `from FinData.adapters` |
| `application.py:18` — `Dict[str, Any]` without import | **CRASH** | Added `from typing import Any, Dict` |
| `fastapi_app.py:592-611` — duplicate /api/market/* routes | **CRASH** | Removed duplicate definitions |
| `bank_wmp.py:21-23` — BOC regex too broad, BOSC greedy | **TEST FAIL** | Tightened BOC regex, reordered checks |

---

## Audit Findings Summary (2026-06-05)

### Critical / High — Should Fix Next

| # | File | Issue | Impact |
|---|------|-------|--------|
| H1 | `FinData/serving/provider.py:37` | `ohlcv()` returns only `adj_close`, not OHLCV | Misleading API |
| H2 | `FinData/store/quality.py:127` | QualityGate creates unshared second MarketDataRepository | Data isolation |
| H3 | `FinData/store/quality.py:437` | `_is_duplicate` never canonicalizes existing columns (Check 8 broken) | Silent duplicate writes |
| H4 | `FinData/serving/provider.py:205` | `_trigger_refresh` is dead stub — "live" mode does nothing | Stale data silently served |
| H5 | `src/analytics/alerts.py:452` | `check_stale_prices` reads from wrong dict level | Alerts never fire |
| H6 | `src/analytics/alerts.py` | `AlertEngine` fully implemented but never wired into any service | Dead code |
| H7 | `src/api/static_dashboard.py:127` | Hardcoded `as_of=2024-02-07` in JS API call | Frozen date bug |
| H8 | `src/core/dashboard_engine.py` | Nearly all analytics methods return `np.random` dummy data | Deceptive to users |
| H9 | `src/api/ghostfolio_compat.py` | Multiple stub endpoints return fixed/empty data silently | Misleading API |

### Medium — Address Within Next 2-3 Weeks

| # | File | Issue |
|---|------|-------|
| M1 | `FinData/__init__.py` | Inconsistent abstraction bypass for `list_assets()`/`missing_report()` |
| M2 | `FinData/adapters/interfaces.py` | Orphaned dead code (`AsyncBaseFetcher` never used) |
| M3 | `FinData/store/quality.py:378` | `stale_price_check` references nonexistent `fund_path`/`wealth_path` |
| M4 | `FinData/store/quality.py:24` | Imports private names across package boundary |
| M5 | `FinData/store/schemas.py` | Incomplete re-export layer |
| M6 | `FinData/orchestration/orchestrator.py` | No rate limiting on fallback providers |
| M7 | `FinData/orchestration/ingest.py` | Calendar/store errors outside try/except abort batch |
| M8 | `FinData/serving/provider.py` | `mode="tolerant"` documented but unimplemented |
| M9 | `src/analytics/exposure.py` | `ExposureItem.pct` (0-1) vs `ConcentrationItem.pct` (0-100) inconsistent |
| M10 | `src/api/ghostfolio_compat.py` | `_resolve_asset_info()` calls `get_application_services()` per-request uncached |
| M11 | `src/services/research_service.py` | Runtime imports of `FinData` and `portfolio.optimizer` |
| M12 | `src/api/static_dashboard.py:149` | Position values evenly split across asset_ids (approximate) |
| M13 | `src/services/dashboard_service.py` | `normalize_response()` can produce `{success: True, error: "..."}` |
| M14 | `src/services/portfolio_service_v2.py` | `_load_asset_meta()` and `_load_product_registry()` independently parse same YAML |

### Low / Documentation — Ongoing

| # | Issue |
|---|-------|
| L1 | No `CLAUDE.md` — AI assistants have no project-level instructions |
| L2 | 30 skipped tests (env-dependent + undecided feature placeholders) |
| L3 | `breakdiown` typo in `valuation.py` |
| L4 | Chinese docs (`代码审查与改进建议.md` etc.) still describe old Streamlit architecture |
| L5 | pandas `FutureWarning` in `ingestion_log.py:53` (concat with empty DataFrames) |
| L6 | `FinData/adapters/interfaces.py` — orphaned `AsyncBaseFetcher`, unused `import asyncio` |
| L7 | `FinData/store/repository.py:69` — `reject()` method is dead code |
| L8 | `FinData/store/schemas.py:16` — dead `store_version` constant |

---

## Near-Term Plan (Next 2-4 Weeks)

### Phase 1: Wire What's Already Built (THIS WEEK)

**This is the highest-impact, lowest-effort work.**

1. **Wire AlertEngine into the application** — `AlertEngine.run_all()` is fully implemented but never called. Add it to `tools/scheduler.py` daily pipeline, create a `/api/alerts` endpoint, and add alert actions (log, Bark notification).
2. **Fix `AlertEngine.check_stale_prices`** — the dict-level mismatch (H5) makes the stale-price alert always pass silently.
3. **Fix static_dashboard hardcoded date** (H7) — change `2024-02-07` to dynamic date in the JS.
4. **Fix QualityGate duplicate repository** (H2) — pass `repository=self.repo` from CanonicalStore.
5. **Fix QualityGate `_is_duplicate`** (H3) — the conditional never executes, Check 8 is broken.
6. **Fix `provider.ohlcv()`** — it returns only `adj_close`, misleading consumers.

### Phase 2: Replace Dummy Data With Real Data (NEXT WEEK)

7. **Rewrite `dashboard_engine.py`** — replace all `np.random` calls with real analytics from `src/analytics/` + `FinData` serving layer.
8. **Wire Ghostfolio compat endpoints** — replace stubs with real data from PortfolioServiceV2 + ExposureAnalyzer.
9. **Implement `mode="live"` and `mode="tolerant"`** in DataProvider — wire the orchestrator refresh.

### Phase 3: Financial Core Safety (WEEKS 3-4)

10. Calendar registry (from `TIME_ALIGNMENT_DESIGN.md`) — cutoff-aware valuation.
11. Per-position `price_date`/`price_source`/`fx_source` metadata.
12. Fix `get_value_history()` corporate-actions-per-date (currently applies end-date actions to all history).
13. Replace hardcoded FX with configured manual rates + dated local FX history.

---

## Long-Term Plan

### Product
- React + Vite frontend against FastAPI.
- Portfolio import/edit from local templates.
- Explainable NAV: price source, FX source, corporate actions, stale-data warnings in UI.

### Quant & Research
- Harden multi-calendar backtests against look-ahead bias.
- Decide Qlib role: implement `qlib_adapter.py` for factor/ML, or remove from roadmap.
- Benchmark comparison, risk attribution, transaction-cost-aware rebalancing.

### Data Platform
- Partition market data by asset/source/date (not single Parquet rewrite).
- Track provider provenance, request status, schema version, fetch timestamp.
- Migration scripts for schema changes.

### Operations
- `.pytest_tmp/` added to `.gitignore`.
- CI: tests, privacy scan, package metadata checks.
- Structured logging for fetchers, services, data writes.
- Decide: single-user local or multi-user auth.

---

## Definition of Ready

Before large new features:

- `python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider` passes.
- No private files in `git status --short`.
- New logic in FastAPI/services/core/FinData, not `app.py`.
- Financial outputs include metadata: price date, source, FX rate, staleness.
- `AlertEngine` is wired and functional — every new risk feature ships with at least one alert rule.
