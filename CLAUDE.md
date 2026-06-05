# CLAUDE.md — OptiFolio Project Instructions

## Project Context

OptiFolio v0.2.0 — personal multi-asset portfolio risk engine. Python 3.14.2 on Windows.
592 tests green. FinData is the self-contained data department (32 files, ~4200 lines).

## Critical Rules

1. **FinData is the ONLY data path.** `from FinData import fd` — never import fetchers directly.
2. **app.py is FROZEN.** 1550-line Streamlit monolith. Do NOT edit it. All new work → `src/api/`, `src/services/`, `src/analytics/`.
3. **Private data stays out of git.** `local/`, `config/secrets.yaml`, `.parquet`, `.db`, `.csv` are all git-ignored.
4. **Use `logging`**, not `print()`. `import logging; _log = logging.getLogger(__name__)`.
5. **Services use `success()` / `failure()`** from `src/services/response.py`. API uses `_json_response()`.
6. **Every adapter returns `FetchResult`** — never an empty DataFrame without metadata.
7. **QualityGate runs 8 checks** on every write — empty data NEVER overwrites good data.
8. **Do not import private names across packages** — use re-export layers (e.g. `FinData/store/schemas.py`).

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

## Naming Conventions

- Asset identifiers: uppercase ticker (`AAPL`), 6-digit CN code (`600519`), bank WMP code (`GRSDR260056`)
- Asset types: `us_equity`, `cn_stock`, `cn_fund_etf`, `cn_fund_open`, `cn_money_market_fund`, `bank_wmp`, `forex`, `crypto`
- Canonical columns: `asset_id`, `date`, `open`, `high`, `low`, `close`, `adj_close`, `volume`, `currency`, `source`, `timezone`
- Date strings: ISO format `YYYY-MM-DD`
