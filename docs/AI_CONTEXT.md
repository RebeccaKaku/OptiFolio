# OptiFolio AI Context Document

> **Product priority:** Read `docs/PRODUCT_VISION_AND_EXECUTION_PLAN.md` before proposing or implementing new work. It is the current product north star and overrides older feature queues when priorities conflict.

> This document is the source of truth for AI assistants working on this codebase.
> Last updated: 2026-06-23. Cross-check with `docs/CURRENT_STATE.md`.

## Project Identity

- **Name**: OptiFolio v0.2.0
- **Purpose**: Personal multi-asset portfolio risk engine and allocation advice system
- **Tagline**: "Risk engine first, allocation advice second"
- **Runtime**: Python 3.14.2 (Windows), >=3.10
- **Build**: Hatchling (`pyproject.toml`)
- **Tests**: 982 passed, 0 failures (use `python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider`)

## Architecture (Current — 2026-06-23)

```
packages/
  optifolio_contracts/           # Pure types, protocols, enums — stdlib ONLY
    calendars.py                 #   ExchangeCalendarProtocol
    datasets.py                  #   Dataset ID constants (EQUITIES_OHLCV_DAILY, FX_SPOT_DAILY, …)
    fx.py                        #   FxRateProviderProtocol, FxRateError, HardcodedFxRateProvider
    identifiers.py               #   parse_instrument_id(), normalize_instrument_id()
    market_data.py               #   CANONICAL_MARKET_COLUMNS, CANONICAL_OBSERVATION_COLUMNS, STORE_VERSION
    quality.py                   #   ValuationFreshness, ValuationQuality
    sources.py                   #   Data source constants (AKSHARE, YFINANCE, BOC_WEB, …)
    symbols.py                   #   CN symbol normalization helpers
  findata/                       # Self-contained data department
    __init__.py                  #   fd singleton — from findata import fd
    config.py                    #   FinDataConfig — data directory resolution
    fx.py / fx_sync.py           #   FX rate handling + sync
    rates.py                     #   Macro rates (SOFR, SHIBOR, CPI, …)
    adapters/                    #   10 provider fetchers + FetcherProtocol + FETCHER_REGISTRY
    store/                       #   CanonicalStore, QualityGate, MarketDataRepository, ingestion_log
    orchestration/               #   Orchestrator, cadence, rate_limiter, fallback, ingest
    serving/                     #   DataProvider — fd.prices(), fd.panel(), fd.ohlcv(), fd.returns(), …
    calendars/                   #   Timezone registry (thin; full calendars in src/core/calendars.py)

src/
  domain/        # Pure dataclasses — products, positions, exposures, cashflows, instruments,
                 #   series, observations, fees, import_drafts, decision_journal, macro_view,
                 #   model_governance, purpose_buckets, relationships, corporate_actions
  core/          # Valuation, calendars, portfolio_book_db, portfolio_ledger, fees,
                 #   corporate_actions, asset_manager, config_manager, paths, exceptions, cache
  analytics/     # alerts, concentration, exposure, fx_exposure, liquidity, permanent_loss,
                 #   returns, return_attribution, reconciliation, rule_engine, screening,
                 #   new_money_engine, product_comparison, trade_friction, usd_scenario,
                 #   allocation_targets, currency_aggregation
  api/           # fastapi_app.py (port 8011), ghostfolio_compat.py, static_dashboard.py,
                 #   my_money_api.py, portfolio_book_api.py
  services/      # application.py (service graph), portfolio_service_v2.py,
                 #   portfolio_book_service.py, book_valuation_service.py,
                 #   my_money_service.py, research_service.py, decision_journal_service.py,
                 #   import_draft_service.py, fund_friction_service.py, …
  research/      # backtest.py, model_registry.py, qlib_adapter.py
  runtime/       # bootstrap.py — local state initialization

app.py           # LEGACY Streamlit dashboard — FROZEN, target: delete
config/          # YAML configs (asset_registry, candidates, settings templates)
tools/           # CLI: scheduler.py, sync_fx_rates.py, sync_macro_rates.py, privacy_scan.py, …
tests/           # test files, all pytest
```

## Dependency Direction (CRITICAL)

```
optifolio_contracts   (stdlib only — no pandas, no akshare, no FastAPI)
    ↑
findata               (pandas, numpy, duckdb, akshare, yfinance — NO src/ imports)
    ↑
src/                  (FastAPI, services, analytics, core, domain — imports from both packages)
```

**Never reverse.** `packages/` must NOT import from `src/`.
`optifolio_contracts` must NOT import from `findata` or `src/`.

## Key Rules (CRITICAL — violations will be rejected)

1. **`findata` is the ONLY data path.** All market data flows through `from findata import fd`. Never import adapters directly.
2. **Do NOT edit `app.py`.** It is frozen legacy Streamlit. Target: delete when dashboard is fully replaced.
3. **Services use `success()` / `failure()`** from `src/services/response.py`. API handlers use `_json_response()`.
4. **Use `logging`**, not `print()`. Import: `import logging; _log = logging.getLogger(__name__)`.
5. **Keep private data out of git.** `local/`, `config/secrets.yaml`, `.parquet`, `.db`, `.csv` are git-ignored.
6. **Run tests before submitting.** `python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider`.
7. **Run privacy scan.** `python tools/privacy_scan.py --strict --with-detect-secrets`.
8. **One PR = one task.** Keep changes small, single-purpose, with tests.

## Migration Traps — DO NOT DO

1. **DO NOT recreate `FinData/`.** Migrated to `packages/findata/` on 2026-06-23. `from FinData import fd` → `from findata import fd`.
2. **DO NOT recreate `src/data_foundation/`.** Moved to `packages/findata/findata/store/`.
3. **DO NOT import from `src/` into `packages/`.**
4. **DO NOT define `CANONICAL_MARKET_COLUMNS` or `STORE_VERSION` outside `optifolio_contracts/market_data.py`.**
5. **DO NOT use `from FinData.store.schemas import ...`** — use `from optifolio_contracts.market_data import CANONICAL_MARKET_COLUMNS`.
6. **DO NOT use `from src.core.symbols import ...`** — use `from optifolio_contracts.identifiers import parse_instrument_id`.
7. **DO NOT use `from src.data_core.fetchers.factory import ...`** — this module no longer exists.

## Data Flow

```
Provider (akshare / yfinance / BOC / BOSC / ICBC)
    │
    ▼
findata/adapters/   →  FetchResult (never empty DataFrame without metadata)
    │
    ▼
findata/store/      →  QualityGate.inspect() → 9 checks → accept / reject
    │                    CanonicalStore.accept() → normalize → Parquet + DuckDB
    ▼
findata/serving/    →  DataProvider → prices(), ohlcv(), panel(), returns(), metrics(), fx_rate()
    │
    ▼
src/services/       →  PortfolioServiceV2, MyMoneyService, ResearchService
    │
    ▼
src/api/            →  FastAPI → JSONResponse
```

## Module Contracts

### findata adapters (`packages/findata/findata/adapters/`)
- Every adapter returns `FetchResult` (symbol, dataframe, metadata, success, error).
- `FetcherProtocol` is the sync interface (in `adapters/__init__.py`).
- `FETCHER_REGISTRY` maps asset_type → fetcher class.
- `get_fetcher(asset_type)` returns a fetcher instance or None for unsupported types.

### findata store (`packages/findata/findata/store/`)
- `CanonicalStore` wraps `MarketDataRepository` with `QualityGate`.
- `QualityGate.inspect(df, existing)` runs 9 checks, returns `QualityReport`.
- `MarketDataRepository` does DuckDB queries + Parquet reads/writes.
- `get_prices(assets, fields=("adj_close",))` — single field → pivoted matrix; multi-field → flat DataFrame.
- Schema columns defined in `optifolio_contracts.market_data` (CANONICAL_MARKET_COLUMNS).

### findata serving (`packages/findata/findata/serving/`)
- `DataProvider` is the public API. `from findata import fd` returns its singleton.
- `fd.prices("AAPL")` → Series. `fd.panel(["AAPL","QQQ"])` → pivoted DataFrame.
- `fd.ohlcv("AAPL")` → flat DataFrame with open/high/low/close/adj_close/volume columns.
- `fd.returns("AAPL")` → Series of daily returns.
- `fd.metrics("AAPL")` → dict of computed metrics.
- `fd.fx_rate("USD", "CNY")` → float.
- `fd.rate("1y_cn")` → float (macro rate).
- `fd.observations([...])` → Series or DataFrame.

### optifolio_contracts (`packages/optifolio_contracts/`)
- Pure types with zero external dependencies (stdlib only).
- `parse_instrument_id("fund.cn.000198")` → `InstrumentIdParts(domain="fund", source="cn", local_id="000198")`.
- `ValuationQuality` enum: `ACTUAL / REPORTED / ESTIMATED / PROXY / UNKNOWN`.
- `ValuationFreshness` enum: `FRESH / STALE / MISSING`.
- `CANONICAL_MARKET_COLUMNS` — authoritative column names for all OHLCV data.
- `STORE_VERSION` — increment when canonical schema changes.

### src/domain (`src/domain/`)
- Pure dataclasses defining the financial domain model.
- `ProductDefinition` — what the user bought (name, issuer, currency, risk_level, liquidity_type).
- `PositionSnapshot` — how much of a product is held (quantity, market_value, cost_basis, currency).
- `ExposureSnapshot` — what the product is actually exposed to (asset_class, region, duration, credit).
- `CashflowEvent` — money movements (subscription, redemption, interest, fee, fx_conversion).
- `DecisionJournalEntry` — why a decision was made, what was assumed, what was the outcome.
- These types carry `Product` vs `Instrument` semantics — a product is what you buy; an instrument is the underlying.

### src/services
- `ApplicationServices` is the service graph (dataclass, `@lru_cache` singleton).
- `PortfolioServiceV2` is the CANONICAL portfolio service — date-aware, corporate-action-aware.
- `MyMoneyService` powers the "My Money" summary page (DS-015).
- `PortfolioBookService` manages personal book CRUD.
- `AlertEngine` (in `src/analytics/alerts.py`) — implemented, wired into API and scheduler.

### src/api
- `fastapi_app.py` on port 8011. CORS allows GET/OPTIONS only (POST needs adding).
- `_json_response(payload)` wraps service responses for HTTP.
- `my_money_api.py` — "My Money" summary endpoint.
- `portfolio_book_api.py` — accounts, products, snapshots, cashflows CRUD.
- Ghostfolio compat routes at `/api/v1/portfolio/*`.

### src/core/portfolio_book_db.py
- Versioned SQLite database for personal data (accounts, products, snapshots, cashflows).
- Strictly isolated from market data (`findata`).
- Sequential migration system (currently at v8).
- Supports full database backup and verified restore.

## Milestone Status (2026-06-23)

| Milestone | DS Tasks | Code | User-Visible |
|-----------|----------|------|-------------|
| M1: 可中断建账 | DS-001~010 | ✅ Implemented | Needs integration verification |
| M2: 可信"我的钱" | DS-011~015 | ✅ Implemented | Needs real-data wiring |
| M3: 看穿产品外壳 | DS-016~019 | ✅ Implemented | Needs exposure data |
| M4: 决策工具 | DS-020~023 | ✅ Implemented | Needs integration |
| M5: 判断实验室 | DS-024~027 | ✅ Implemented | Needs research data |

All 27 DeepSeek tasks have code implementations. The gap is integration — wiring analytics to real data, replacing stubs, and verifying end-to-end user flows.

## Known Issues (2026-06-23)

### Confirmed Bugs
- `src/core/asset_manager.py:359` imports from `src.data_core.fetchers.factory` — module was deleted, will crash at runtime.
- `CANONICAL_MARKET_COLUMNS` defined in BOTH `optifolio_contracts/market_data.py` AND `findata/store/schemas.py` — dual source of truth.

### Audit Issues Needing Verification
- H2: QualityGate duplicate repository — was fix applied?
- H3: `_is_duplicate` broken (Check 8) — was fix applied?
- H4: `_trigger_refresh` dead stub — wired in recent commit?
- H8: `dashboard_engine.py` np.random dummy data — still present?

### Architecture Questions
See `docs/OPEN_QUESTIONS.md` for pending decisions on domain/contracts boundary, src/core/ split, and calendar layer consolidation.

## Test Commands

```powershell
# Full suite (reliable command for this workspace)
python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider

# Single file
python -m pytest tests/test_findata_serving.py -v

# Single test
python -m pytest tests/test_findata_fetcher.py::test_classification -v
```

## Key File Inventory

| File | Role |
|------|------|
| `packages/findata/findata/__init__.py` | `fd` singleton |
| `packages/findata/findata/adapters/__init__.py` | FetcherProtocol, FETCHER_REGISTRY |
| `packages/findata/findata/store/repository.py` | CanonicalStore |
| `packages/findata/findata/store/quality.py` | QualityGate (9 checks) |
| `packages/findata/findata/serving/provider.py` | DataProvider |
| `packages/findata/findata/orchestration/orchestrator.py` | Orchestrator |
| `packages/optifolio_contracts/optifolio_contracts/__init__.py` | Public type re-exports |
| `packages/optifolio_contracts/optifolio_contracts/identifiers.py` | Asset identifier parsing |
| `packages/optifolio_contracts/optifolio_contracts/market_data.py` | CANONICAL_MARKET_COLUMNS, STORE_VERSION |
| `src/api/fastapi_app.py` | FastAPI entrypoint (port 8011) |
| `src/services/application.py` | Service graph |
| `src/services/portfolio_service_v2.py` | Canonical portfolio service |
| `src/services/my_money_service.py` | "My Money" summary |
| `src/core/portfolio_book_db.py` | Personal book (SQLite, v8) |
| `src/core/valuation.py` | ValuationEngine |
| `src/analytics/alerts.py` | AlertEngine |
| `src/domain/products.py` | ProductDefinition |
| `src/domain/positions.py` | PositionSnapshot |
| `app.py` | FROZEN Streamlit legacy — DO NOT EDIT |
