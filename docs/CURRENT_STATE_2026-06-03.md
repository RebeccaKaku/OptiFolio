# OptiFolio Current State And Code Review

**Date**: 2026-06-03
**Branch**: `master`
**Package version**: `0.2.0` in `pyproject.toml`
**Runtime target**: Python `>=3.11, <3.14` recommended for the quant stack; `pyproject.toml` currently allows `>=3.10,<3.14`
**Verified tests**: `77 passed, 12 skipped`

Use this document as the live project map until the next review pass.

---

## One-Line Status

OptiFolio has a useful FastAPI/service/data-foundation core, but it is mid-migration from a Streamlit-era monolith. The biggest risks are financial semantics, not syntax: cross-market time alignment, deterministic valuation, FX correctness, cashflow/risk-exposure modeling, and fetcher trust boundaries.

The top-level target design for handling more asset types, indexes, macro data, product cashflows, look-through exposures, risk/advice engines, naming, module boundaries, and AI-sized implementation tasks is now documented in `docs/FINANCIAL_LOGIC_AND_MODULE_DESIGN.md`.

---

## Verified Commands

The plain `pytest -q` command is not reliable on this Windows workspace because it may collect `scratch/pytest` and may try to use a restricted temp/cache path.

Recommended local test command:

```powershell
python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider
```

Current result:

```text
77 passed, 12 skipped in 53.78s
```

Also useful:

```powershell
python tools/privacy_scan.py --strict --with-detect-secrets
```

---

## Current Architecture

```text
app.py                  # legacy Streamlit dashboard, frozen for new work
main.py                 # legacy command-line optimization entrypoint
src/api/fastapi_app.py  # current HTTP API entrypoint, default port 8011
src/services/           # business service facade for API/UI
src/core/               # asset, portfolio, valuation, fee, database core
src/data_foundation/    # canonical market data schema + Parquet/DuckDB repository
src/research/           # backtest and research adapters
fetchers/               # async provider-specific data fetchers
portfolio/              # optimization and risk algorithms
config/*.example.yaml   # safe templates
local/                  # ignored private runtime state
```

Direction: keep new product work in `src/services/`, `src/api/fastapi_app.py`, `src/data_foundation/`, and future `frontend/`; treat `app.py`, old `src/api/api_service.py`, and old `src/core/portfolio_core.py` as compatibility surfaces unless a migration task explicitly touches them.

---

## Potential Hazards

### P0/P1 Financial Logic

| Area | Evidence | Risk | Plan |
|---|---|---|---|
| Cross-market time alignment | `src/data_foundation/schemas.py:103-121`, `docs/TIME_ALIGNMENT_DESIGN.md` | Daily prices are closer to exchange-local dates now, but `value_on(T)` still has no cutoff/knowability semantics. Mixed US/CN/crypto portfolios can still accidentally use not-yet-knowable closes. | Implement calendar registry + cutoff-aware valuation before serious backtests or live NAV decisions. |
| Valuation date semantics | `src/core/valuation.py:262` uses the earliest price date across assets | A multi-asset valuation can report one `price_date` that hides per-asset staleness. A stale US asset and fresh CN asset collapse into one date. | Expose per-position `price_date` and staleness; keep portfolio-level `price_date` only as summary metadata. |
| Personal-product semantics | `config/asset_registry.yaml` is flat `symbol/asset_type/currency/attributes` | Deposits, WMPs, structured deposits, funds, and FX positions need cashflows, liquidity, issuer, lockup, and exposure metadata. The current registry cannot express that cleanly. | Introduce Product/Position/Exposure/Cashflow contracts before adding more product logic. |
| FX determinism | `src/core/valuation.py:64-111` | Fallback FX rates are hardcoded and live FX is off by default. This is useful offline, but dangerous if presented as production NAV. | Add explicit FX source metadata, configured manual rates, dated local FX history, and stale-rate warnings. |
| Corporate actions in history | `src/services/portfolio_service_v2.py:98-104` | `get_value_history()` applies corporate actions up to the end date once, then values all prior dates with end-adjusted holdings. That can distort historical series before a dividend/split/merger. | Apply corporate actions incrementally per valuation date. |

### P1 API And Data Safety

| Area | Evidence | Risk | Plan |
|---|---|---|---|
| CORS blocks write routes | `src/api/fastapi_app.py:58` allows only `GET` and `OPTIONS`, while POST routes exist at lines 161, 176, 266, 280, 292 | Browser frontend calls to backtest/optimize/corporate-action routes can fail preflight even though API tests pass. | Add `POST` to CORS methods, or configure allowed methods by environment. |
| Failed service calls become HTTP 500 | `src/api/fastapi_app.py:36-38` | Expected domain failures such as no price data become server errors. Clients cannot distinguish bad input, missing data, and actual crashes. | Map service `error_code` values to 4xx/422/503 where appropriate. |
| TLS verification fallback | `fetchers/bosc.py:147-178`, `fetchers/boc.py:121` | Fetchers retry with `verify=False`; useful for brittle bank portals, but this weakens transport trust and should not be silent. | Make insecure fallback opt-in/configured, log structured warnings, and record `transport_security` metadata in raw snapshots. |
| Fetchers swallow provider errors | `fetchers/boc.py:101-184`, `fetchers/bosc.py:58-189` | Returning empty DataFrames on request errors makes "no data" indistinguishable from "provider failed." | Introduce typed fetch errors or response objects with `status`, `error`, and provider metadata. |
| Data repository full rewrites | `src/data_foundation/repository.py:31-37` | Every save loads and rewrites the whole Parquet file. This is simple but fragile as data grows and unsafe under concurrent writers. | Move to partitioned Parquet by asset/source or a DuckDB table with transactional upserts. |

### P2 Maintainability

| Area | Evidence | Risk | Plan |
|---|---|---|---|
| Streamlit monolith remains large | `app.py` is about 70 KB | Hard to review and easy to regress if new work goes there. | Freeze `app.py`; migrate only workflows needed by FastAPI + React. |
| Duplicate legacy/new service paths | `src/services/portfolio_service.py`, `src/services/portfolio_service_v2.py`, `src/core/portfolio_core.py`, `src/core/valuation.py` | Developers may choose the wrong path and create behavior splits. | Define ownership: V2 valuation is canonical; legacy portfolio is adapter-only. |
| Large mixed-responsibility modules | `src/asset_importer.py`, `src/core/enhanced_asset_manager.py`, `src/core/portfolio_core.py`, `src/core/dashboard_engine.py` | Each mixes IO, data shaping, logging, fallback, and business rules. | Extract pure domain functions first; keep public API stable. |
| Logging is inconsistent | Many modules use `print()` and broad `except Exception` | Hard to debug batch fetches and services in production. | Replace with `src/core/logger.py` or standard `logging`, with source/symbol/date context. |
| Skipped tests encode undecided features | `tests/test_asset_registry.py`, `tests/test_asset_importer.py` | 12 skipped tests include conflict assets, removal, validation, and `get_full_id`; they are product decisions, not just missing tests. | Decide which features matter, implement or delete the placeholder tests. |
| Naming typo | `src/core/valuation.py:379-399` uses `breakdiown` | Low runtime risk, but confusing in a central file. | Rename to `breakdown` during the next valuation cleanup. |

---

## Documentation Issues Fixed In This Pass

- Updated this current-state file from a task ledger into a live review baseline.
- Updated `docs/README.md` to point to current docs and remove stale `README_DASHBOARD.md` references.
- Added a current-state pointer and reliable test command to root `README.md`.

Still stale and should be archived or rewritten later:

- `docs/代码审查与改进建议.md` is a 2026-02 Streamlit-era review.
- Several Chinese docs still describe the old dashboard-first architecture.
- `README.md` still contains long legacy fetcher examples; useful as history, but no longer a concise onboarding guide.

---

## Near-Term Plan

### 1. Make The Financial Core Safe

- Use `docs/FINANCIAL_LOGIC_AND_MODULE_DESIGN.md` as the architecture target: position OptiFolio first as a personal asset risk engine and allocation-advice engine, then split products, positions, instruments, informational series, exposures, cashflows, and relationships.
- Prioritize accounting/risk capabilities before prediction: cashflow ledger, IRR/TWR, base-currency return decomposition, liquidity buckets, concentration, credit/duration/equity/FX exposures, rule advice, product screening, and alerts.
- Implement the remaining pieces of `docs/TIME_ALIGNMENT_DESIGN.md`: calendar registry, per-asset exchange timezone, cutoff-aware `value_on`, and cross-market tests.
- Add per-position `price_date`, `price_source`, `fx_source`, and stale-data flags to valuation results.
- Fix `PortfolioServiceV2.get_value_history()` so corporate actions are applied by each historical date.
- Replace hardcoded FX-only behavior with configured manual rates plus dated local FX history.

### 2. Make API Behavior Frontend-Ready

- Add POST to CORS allowed methods.
- Convert common domain failures to stable HTTP status codes.
- Add V2 route tests for valuation history and corporate-action POST routes.
- Document request/response schemas for the frontend.

### 3. Make Tests Reproducible

- Add pytest config for `testpaths = ["tests"]`.
- Add a stable workspace-local temp/cache policy or document the required command in developer setup.
- Resolve the 12 skipped tests by product decision: implement asset conflict support or delete the placeholders.
- Run privacy scan before publishing.

### 4. Reduce Migration Confusion

- Mark legacy modules clearly in docstrings and docs.
- Start the naming migration from broad terms to financial contracts: `instrument_id` for tradables, `series_id` for macro/index/factor data, `effective_date` and `known_at` for time semantics.
- Define canonical paths:
  - valuation: `src/core/valuation.py`
  - portfolio service: `src/services/portfolio_service_v2.py`
  - API: `src/api/fastapi_app.py`
  - market data: `src/data_foundation/`
- Avoid adding features to `app.py`.

---

## Long-Term Plan

### Product

- Build `frontend/` with React + Vite against FastAPI.
- Support portfolio import/edit workflows from local templates without exposing private files.
- Add explainable portfolio NAV: price source, FX source, corporate actions, and stale-data warnings visible in UI.

### Quant And Research

- Harden multi-calendar backtests against look-ahead bias.
- Decide the role of Qlib: either implement `src/research/qlib_adapter.py` for factor/ML export, or remove it from the active roadmap.
- Add benchmark comparison, risk attribution, and transaction-cost-aware rebalancing.

### Data Platform

- Partition market data by asset/source/date instead of rewriting one Parquet file.
- Track provider provenance, request status, schema version, and fetch timestamp.
- Add migration scripts for existing canonical data when schema changes.

### Operations

- Create a supported local dev environment for Python 3.11/3.12/3.13.
- Add CI with tests, privacy scan, and package metadata checks.
- Add structured logging for fetchers, services, and data writes.
- Decide whether this remains single-user local software or needs multi-user auth and permissions.

---

## Definition Of Ready For New Feature Work

Before large new features:

- `python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider` passes.
- No private files appear in `git status --short`.
- New logic lands in FastAPI/services/core, not `app.py`.
- Financial outputs include enough metadata to explain price date, source, FX rate, and staleness.
