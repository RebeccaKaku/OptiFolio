# OptiFolio Current State

**Date**: 2026-06-24
**Branch**: `main`
**Package version**: `0.2.0`
**Runtime**: Python 3.14.2 (Windows)
**Verified tests**: `983 passed, 0 failures`

---

## One-Line Status

Major refactoring complete: `FinData/` monolith → `packages/findata/` + `packages/optifolio_contracts/`. All 27 DeepSeek tasks implemented. 3 Jules PRs merged (dead code removal, DB naming, YAML fallback removal — partially reverted). Fund identifiers now carry akshare-derived subtype (`fund.cn.money.000198`). **Next: complete TODO.md P0 tasks — remove YAML fallback and hardcoded data.**

---

## Architecture (2026-06-23)

```
packages/
  optifolio_contracts/  ← pure types (stdlib only): identifiers, quality, sources, datasets, fx protocols
  findata/              ← data department: adapters → store → serving + orchestration
src/
  domain/       ← pure dataclasses (products, positions, exposures, cashflows, instruments, …)
  core/         ← valuation, calendars, portfolio_book_db, fees, corporate_actions, asset_manager
  analytics/    ← alerts, exposure, concentration, liquidity, returns, attribution, screening, …
  services/     ← business orchestration (no quant math)
  api/          ← FastAPI routes (no business logic)
  research/     ← backtest, model_registry, qlib_adapter
  runtime/      ← local state bootstrap
```

**Dependency direction**: `contracts ← findata ← src` (never reverse).

### What Changed (2026-06-22 → 2026-06-23)

```
FinData/                     → DELETED (36 files)
src/data_foundation/         → DELETED (3 files)
src/core/symbols.py          → DELETED
tests/test_fetchers.py       → DELETED

packages/findata/findata/adapters/       ← NEW (11 files, from FinData/adapters/)
packages/findata/findata/orchestration/  ← NEW (6 files, from FinData/orchestration/)
packages/findata/findata/serving/        ← NEW (2 files, from FinData/serving/)
packages/findata/findata/store/          ← EXTENDED (+3 files: ingestion_log, quality, repository)
packages/findata/findata/fx_sync.py      ← NEW
packages/findata/findata/rates.py        ← NEW
packages/optifolio_contracts/.../identifiers.py  ← NEW (346 lines)
packages/optifolio_contracts/.../datasets.py     ← NEW
packages/optifolio_contracts/.../sources.py      ← NEW
tests/test_findata_boundary.py   ← NEW
tests/test_fx_integration.py     ← NEW
tests/test_identifiers.py        ← NEW
```

**11 commits** on 2026-06-23: `0b17a30` through `f4f367b`.

---

## Milestone Status

| Milestone | DS Tasks | Implementation | Integration |
|-----------|----------|---------------|-------------|
| M0: 停止打转 | — | ✅ Complete | ✅ |
| M1: 可中断建账 | DS-001~010 | ✅ | ⚠️ Needs e2e verification |
| M2: 可信"我的钱" | DS-011~015 | ✅ | ⚠️ Real data wiring pending |
| M3: 看穿产品外壳 | DS-016~019 | ✅ | ⚠️ Exposure data needed |
| M4: 决策工具 | DS-020~023 | ✅ | ⚠️ Integration pending |
| M5: 判断实验室 | DS-024~027 | ✅ | ⚠️ Research data needed |

All 27 DS tasks are implemented at the code level. The remaining work is integration:
wiring analytics to real market data, replacing stub/dummy data, and verifying
that the user-visible outcomes described in `PRODUCT_VISION` §7 actually work end-to-end.

---

## Known Bugs (2026-06-23)

### Confirmed — Fix Required

| # | File | Issue | Severity |
|---|------|-------|----------|
| B1 | `src/core/asset_manager.py:359` | `from src.data_core.fetchers.factory import get_factory` — module deleted, **will crash at runtime** | **CRASH** |
| B2 | `findata/store/schemas.py` + `optifolio_contracts/market_data.py` | `CANONICAL_MARKET_COLUMNS` defined in two places — dual source of truth | **DATA** |
| B3 | `findata/store/schemas.py` + `optifolio_contracts/market_data.py` | `STORE_VERSION = "2.0"` defined in two places | **DATA** |

### Audit Issues — Status Unknown

These were reported in the 2026-06-05 audit. Some may have been fixed in subsequent commits; verification needed:

| # | Issue | Suspected Status |
|---|-------|-----------------|
| H2 | QualityGate creates unshared second MarketDataRepository | May be fixed (5e1371c) |
| H3 | `_is_duplicate` never canonicalizes existing columns (Check 8 broken) | May be fixed (5e1371c) |
| H4 | `_trigger_refresh` is dead stub | May be fixed (22f3d8a) |
| H8 | `dashboard_engine.py` returns `np.random` dummy data | Likely still present |

### Audit Issues — Confirmed Fixed

| # | Issue | Fix Commit |
|---|-------|-----------|
| H1 | `ohlcv()` returns only `adj_close` | 560d3a4 (pre-refactor) |
| H5 | `check_stale_prices` reads from wrong dict level | 7c6a55f (pre-refactor) |
| H6 | AlertEngine never wired | 673cbe4 (pre-refactor) |
| H7 | static_dashboard hardcoded date | 7f744b6 (pre-refactor) |
| H9 | Ghostfolio compat stubs | 22f3d8a (pre-refactor) |

---

## Architecture Questions Pending

See `docs/DECISIONS_PENDING-656c946.md` for:

1. Should `src/domain/` types be promoted to `optifolio_contracts`?
2. How to resolve `CANONICAL_MARKET_COLUMNS` / `STORE_VERSION` dual definition?
3. Should `src/core/` be split into `core` (pure computation) and `persistence` (SQLite)?
4. Is the three-layer calendar split (contracts → findata → src/core) correct?
5. Does the four-document structure (CLAUDE.md, AI_CONTEXT.md, CURRENT_STATE.md, PRODUCT_VISION.md) cover all AI collaboration needs?

---

## Next Steps (Priority Order)

### P0: Doc Updates ✅ (this session)
- [x] CLAUDE.md — updated for new package structure
- [x] AI_CONTEXT.md — architecture, data flow, module contracts updated
- [x] CURRENT_STATE.md — this file
- [x] DECISIONS_PENDING.md — architecture questions for peer review

### P1: Bug Fixes
- [ ] Fix B1: `asset_manager.py:359` crash reference
- [ ] Fix B2/B3: Eliminate dual `CANONICAL_MARKET_COLUMNS` / `STORE_VERSION`

### P2: Audit Verification
- [ ] Verify H2, H3, H4, H8 status
- [ ] Update audit tracking

### P3: Integration
- [ ] Wire dashboard to real analytics data (replace np.random)
- [ ] End-to-end test: create account → add product → confirm snapshot → view "My Money"

---

## Reliable Commands

```powershell
# Full test suite
python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider

# Privacy scan
python tools/privacy_scan.py --strict --with-detect-secrets

# Run API server
python -m uvicorn src.api.fastapi_app:app --port 8011
```

## Recent Commits (last 10)

```
f4f367b chore: update asset registry and candidates config
edb5a84 test: update tests for new package structure
82fc9df refactor(tools): update tools for new package imports
26161d8 refactor(src): update imports for new findata + contracts packages
24668a9 build: update pyproject.toml configs for package migration
ad19f98 feat(contracts): add identifiers, datasets, sources; update re-exports
5e1371c feat(findata): add canonical store, quality gate, FX sync, and rates
142647b feat(findata): add orchestration and serving layers
f522c32 feat(findata): add adapters layer (10 fetchers from FinData migration)
20a0fd5 chore: remove migrated src/data_foundation and symbols
0b17a30 chore: remove old FinData monolith
```
