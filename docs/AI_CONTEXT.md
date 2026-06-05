# OptiFolio AI Context Document

> This document is the source of truth for AI assistants working on this codebase.
> Last updated: 2026-06-05. Always cross-check with `docs/CURRENT_STATE_2026-06-05.md`.

## Project Identity

- **Name**: OptiFolio v0.2.0
- **Purpose**: Personal multi-asset portfolio risk engine and allocation advice system
- **Tagline**: "Risk engine first, allocation advice second"
- **Runtime**: Python 3.14.2 (Windows), >=3.11,<3.14 supported
- **Build**: Hatchling (`pyproject.toml`)
- **Tests**: 592 passed, 30 skipped, 0 failures (use `python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider`)

## Architecture (Current — 2026-06-05)

```
FinData/                       # Self-contained data department — the ONLY data path
  __init__.py                  # fd singleton — import from FinData import fd
  adapters/                    # 10 provider fetchers + FetcherProtocol + FETCHER_REGISTRY
  store/                       # CanonicalStore, QualityGate (8 checks), ingestion log, portfolio ledger
  orchestration/               # Orchestrator, cadence, rate limiter, fallback chains, ingest.py
  serving/                     # DataProvider — fd.prices(), fd.panel(), fd.returns(), fd.metrics(), fd.ohlcv()

src/
  analytics/                   # alerts, concentration, exposure, fx_exposure, liquidity, returns, rule_engine, screening
  api/                         # fastapi_app.py (port 8011), ghostfolio_compat.py, static_dashboard.py
  core/                        # valuation, calendars, corporate_actions, fees, dashboard_engine, config_manager
  data_foundation/             # canonical schema + MarketDataRepository (DuckDB/Parquet) — used BY FinData, not instead of it
  domain/                      # products, positions, instruments, series, observations, cashflows
  research/                    # BacktestEngine (vectorbt + pandas fallback), qlib_adapter (placeholder)
  services/                    # application.py (service graph), portfolio_service_v2.py (canonical), research_service.py

app.py                         # LEGACY Streamlit dashboard — FROZEN, do NOT edit
config/                        # YAML configs (settings, candidates, asset_registry, *.example.yaml)
tools/                         # CLI: start_app.py, scheduler.py, ingest_portfolio_prices.py, export_to_ghostfolio.py, privacy_scan.py
tests/                         # 31 test files, all pytest
```

## Key Rules (CRITICAL — violations will be rejected)

1. **FinData is the ONLY data path.** All market data flows through `from FinData import fd`. Never import fetchers directly.
2. **Do NOT edit `app.py`.** It is frozen legacy Streamlit. All new work → `src/api/`, `src/services/`, `src/analytics/`.
3. **Services use `success()` / `failure()`** from `src/services/response.py`. API handlers use `_json_response()` from `fastapi_app.py`.
4. **Use `logging`**, not `print()`. Import: `import logging; _log = logging.getLogger(__name__)`.
5. **Keep private data out of git.** `local/`, `config/secrets.yaml`, `.parquet`, `.db`, `.csv` are git-ignored.
6. **Run tests before submitting.** `python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider`.
7. **Run privacy scan.** `python tools/privacy_scan.py --strict --with-detect-secrets`.
8. **One PR = one task.** Keep changes small, single-purpose, with tests.

## Data Flow

```
Provider (akshare/yfinance/ccxt/BOC/BOSC/ICBC)
    │
    ▼
FinData/adapters/   →  FetchResult (never empty DataFrame without metadata)
    │
    ▼
FinData/store/      →  QualityGate.inspect() → 8 checks → accept/reject
    │                    CanonicalStore.accept() → normalize → save_raw (Parquet + DuckDB)
    ▼
FinData/serving/    →  DataProvider → prices(), ohlcv(), panel(), returns(), metrics(), fx_rate()
    │
    ▼
src/services/       →  PortfolioServiceV2, ResearchService, DashboardService
    │
    ▼
src/api/            →  FastAPI → JSONResponse
```

## Module Contracts

### FinData adapters
- Every adapter returns `FetchResult` (symbol, dataframe, metadata, success, error).
- `FetcherProtocol` is the sync interface (in `FinData/adapters/__init__.py`).
- `FETCHER_REGISTRY` maps asset_type → fetcher class.
- `get_fetcher(asset_type)` returns a fetcher instance or None for unsupported types.

### FinData store
- `CanonicalStore` wraps `MarketDataRepository` with `QualityGate`.
- `QualityGate.inspect(df, existing)` runs 8 checks, returns `QualityReport`.
- `MarketDataRepository` does DuckDB queries + Parquet reads/writes.
- `get_prices(assets, fields=("adj_close",))` — single field → pivoted matrix; multi-field → flat DataFrame.

### FinData serving
- `DataProvider` is the public API. `from FinData import fd` returns its singleton.
- `fd.prices("AAPL")` → Series. `fd.panel(["AAPL","QQQ"])` → pivoted DataFrame.
- `fd.ohlcv("AAPL")` → flat DataFrame with open/high/low/close/adj_close/volume columns.
- `fd.returns("AAPL")` → Series of daily returns.
- `fd.metrics("AAPL")` → dict of computed metrics.
- `fd.fx_rate("USD", "CNY")` → float.
- `mode="live"` triggers orchestrator refresh (wired, may fail gracefully).

### src/services
- `ApplicationServices` is the service graph (dataclass, `@lru_cache` singleton).
- `PortfolioServiceV2` is the CANONICAL portfolio service — date-aware, corporate-action-aware.
- `AlertEngine` (in `src/analytics/alerts.py`) is implemented but not yet wired into services (Task 6 pending).

### src/api
- `fastapi_app.py` on port 8011. CORS allows GET/OPTIONS only (POST needs adding).
- `_json_response(payload)` wraps service responses for HTTP.
- Ghostfolio compat routes at `/api/v1/portfolio/*` (some endpoints still stubs).
- New endpoints should use `@app.get`/`@app.post` with `tags` kwarg.

## Recent Changes (2026-06-05)

- Crossroads bugs fixed: QualityGate repo sharing (H2), `_is_duplicate` canonicalization (H3), `check_stale_prices` envelope unwrap (H5), `ohlcv()` multi-field (H1), `_trigger_refresh` wired (H4).
- `MarketDataRepository.get_prices()` now supports multi-field queries.
- `bank_wmp.py` regex tightened: BOC `^[A-Z]{5,}[A-Z0-9]{5,}$`, BOC checked before BOSC.
- Duplicate FastAPI routes removed. `application.py` typing imports fixed.
- `orchestrator.py` import path fixed.

## Known Issues (Post-Audit)

See `docs/CURRENT_STATE_2026-06-05.md` for full catalogue. Quick reference:
- **H6**: AlertEngine never wired (Task 6 pending)
- **H7**: static_dashboard hardcoded date (Task 8 pending)
- **H8**: dashboard_engine returns np.random dummy data
- **H9**: Ghostfolio compat stubs return empty data
- **M2**: `FinData/adapters/interfaces.py` is dead code (Task 7 pending)
- **M9**: ExposureItem.pct (0-1) vs ConcentrationItem.pct (0-100) inconsistent (Task 10 pending)
- **L3**: `breakdiown` typo in `valuation.py:379`

## Test Commands

```powershell
# Full suite (reliable command for this workspace)
python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider

# Single file
python -m pytest tests/test_findata_serving.py -v

# Single test
python -m pytest tests/test_findata_fetcher.py::TestBankWmpClassification -v
```

## File Inventory (key files only)

| File | Lines | Role |
|------|-------|------|
| `FinData/__init__.py` | ~80 | fd singleton |
| `FinData/adapters/__init__.py` | ~70 | FetcherProtocol, FETCHER_REGISTRY |
| `FinData/store/repository.py` | ~120 | CanonicalStore |
| `FinData/store/quality.py` | ~500 | QualityGate (8 checks) |
| `FinData/serving/provider.py` | ~250 | DataProvider |
| `FinData/orchestration/orchestrator.py` | ~260 | Orchestrator |
| `src/api/fastapi_app.py` | ~610 | FastAPI entrypoint |
| `src/services/application.py` | ~45 | Service graph |
| `src/services/portfolio_service_v2.py` | ~760 | Canonical portfolio service |
| `src/core/valuation.py` | ~420 | ValuationEngine |
| `src/analytics/alerts.py` | ~500 | AlertEngine |
| `src/analytics/exposure.py` | 209 | ExposureAnalyzer |
| `src/core/dashboard_engine.py` | ~560 | Dashboard (mostly np.random — needs rewrite) |
| `app.py` | 1550 | FROZEN Streamlit legacy |
