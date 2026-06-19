# CLAUDE.md — OptiFolio Project Instructions

## Project Context

OptiFolio v0.2.0 — personal multi-asset portfolio risk engine on Python 3.14 / Windows.
Test counts change frequently; use `docs/AI_CONTEXT.md` and a fresh test run. FinData is the self-contained data department.

## Critical Rules

1. **FinData is the ONLY data path.** `from FinData import fd` — never import fetchers directly.
2. **Private data stays out of git.** `local/`, `config/secrets.yaml`, `.parquet`, `.db`, `.csv` are all git-ignored.
3. **Use `logging`**, not `print()`. `import logging; _log = logging.getLogger(__name__)`.
4. **Services use `success()` / `failure()`** from `src/services/response.py`. API uses `_json_response()`.
5. **Every adapter returns `FetchResult`** — never an empty DataFrame without metadata.
6. **QualityGate runs 9 checks** on every write — empty data NEVER overwrites good data.
7. **Do not import private names across packages** — use re-export layers (e.g. `FinData/store/schemas.py`).
8. **Prefer simplicity over compatibility.** This is pre-1.0. Delete dead code; remove unnecessary abstractions; don't keep "just in case" inheritance. Duck typing is sufficient when no `isinstance` checks exist. A deleted file is better than a kept compatibility shim.
9. **Method signatures: optional > required.** Use `context=None, **kwargs` instead of `context: Dict`. Let callers omit what they don't need. Use `Body(None)` for optional JSON bodies in FastAPI.
10. **Don't nest adapters.** Put fetcher logic directly in the `FetcherProtocol` implementation. No "thin wrapper → real fetcher" two-level delegation. No `BaseFetcher → FetcherAdapter` inheritance chains when a single class suffices.

## Reliable Test Command

```powershell
python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider
```

Do NOT use plain `pytest -q` — it may collect `scratch/` and use restricted temp paths on this Windows workspace.

Other required checks:
```powershell
python tools/privacy_scan.py --strict --with-detect-secrets
```

## Key Files

| File | Purpose |
|------|---------|
| `FinData/__init__.py` | fd singleton — THE data API |
| `FinData/store/quality.py` | QualityGate — 8 checks on every write |
| `FinData/store/repository.py` | CanonicalStore — validated storage |
| `FinData/serving/provider.py` | DataProvider — prices, ohlcv, returns, metrics, fx |
| `FinData/orchestration/orchestrator.py` | Orchestrator — schedule + dispatch |
| `src/api/fastapi_app.py` | FastAPI on port 8011 |
| `src/services/application.py` | Service graph (`get_application_services()`) |
| `src/services/portfolio_service_v2.py` | Canonical portfolio service |
| `src/analytics/alerts.py` | AlertEngine (implemented, being wired) |
| `src/core/valuation.py` | ValuationEngine |
| `src/data_foundation/repository.py` | MarketDataRepository (DuckDB + Parquet) |
| `config/asset_registry.yaml` | Flat asset registry v2.0 |

## Live Documents

- `docs/CURRENT_STATE_2026-06-05.md` — live project map, hazards, plans
- `docs/AI_CONTEXT.md` — full architecture reference for AI assistants
- `docs/JULES_CLOUD_TASKS.md` — task queue for Jules agents
- `docs/FINANCIAL_LOGIC_AND_MODULE_DESIGN.md` — target architecture blueprint
- `docs/TIME_ALIGNMENT_DESIGN.md` — cross-market time alignment design

## Architecture Boundaries

```
FinData/          ← self-contained data department (adapters → store → serving)
src/data_foundation/  ← canonical schema + MarketDataRepository (used BY FinData)
src/services/     ← business orchestration (no quant math here)
src/analytics/    ← risk analytics and alerts
src/api/          ← FastAPI routes (no business logic here)
src/core/         ← domain logic (valuation, calendars, corporate actions)
portfolio/        ← optimization algorithms (PyPortfolioOpt, cvxpy)
```

## Design Principles (learned from Jules code review 2026-06-05)

- **Duck typing beats ABC inheritance.** `BocFetcher`, `IcbcFetcher`, etc. are looked up via `FETCHER_REGISTRY` and called by duck typing. No code ever does `isinstance(x, AsyncBaseFetcher)`. The abstract base class added complexity without value. Deleted.
- **`to_dict()` lives on the dataclass.** Don't create standalone serialization helpers (`_alert_to_dict(a)`) when the class already has `.to_dict()`. One source of truth for serialization.
- **Auto-wire services.** `get_application_services().alerts` automatically provides dependencies. Don't require callers to pass them manually.
- **Inline, don't delegate.** `CnStockFetcher` was a thin wrapper → real fetcher. Now it's a single class implementing `FetcherProtocol` with all the logic. One file, one class, no delegation.
- **Kill backwards-compat shims before 1.0.** `store_version = STORE_VERSION` alias → just use `STORE_VERSION` in tests. `save_raw` → rename to `save_canonical`, keep `save_raw` only as deprecated wrapper with warning.

## Naming Conventions

- Asset identifiers: uppercase ticker (`AAPL`), 6-digit CN code (`600519`), bank WMP code (`GRSDR260056`)
- Asset types: `us_equity`, `cn_stock`, `cn_fund_etf`, `cn_fund_open`, `cn_money_market_fund`, `bank_wmp`, `forex`, `crypto`
- Canonical columns: `asset_id`, `date`, `open`, `high`, `low`, `close`, `adj_close`, `volume`, `currency`, `source`, `timezone`
- Date strings: ISO format `YYYY-MM-DD`



## Spec-driven working protocol

- Product priority comes from `docs/PRODUCT_VISION_AND_EXECUTION_PLAN.md`.
- DeepSeek-sized work comes from one file in `plans/deepseek/`; also obey `plans/deepseek/README.md`.
- One session implements one task. Do not start the next numbered task or broaden the allowed-file list.
- Before editing, inspect `git status`, restate the contract, and list intended files. Preserve pre-existing changes.
- Stop only when the spec conflicts with the code, requires a forbidden file, risks real data, or needs an architectural decision.
- Never stage, commit, push, touch `local/`, or write real financial data unless the user explicitly requests it.
- Finish with changed files, financial assumptions, exact test results, non-goals, and residual risks.
