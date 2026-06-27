# CLAUDE.md — OptiFolio Project Instructions

## Project Context

OptiFolio v0.2.0 — personal multi-asset portfolio risk engine. Python >=3.10 (dev on 3.14 / Windows).
Test counts change frequently. Read `docs/CURRENT_STATE-656c946.md` and run a fresh test.
The data layer is in `packages/findata/` (formerly `FinData/`); shared types live in `packages/optifolio_contracts/`.
`app.py` (legacy Streamlit) has been deleted. All interfaces are now FastAPI on port 8011.

## Critical Rules

1. **`findata` is the ONLY data path.** `from findata import fd` — never import adapters directly.  Callers do NOT decide where data comes from: `fd.prices("AAPL")` is all they write.  findata internally resolves the source (cache → yfinance → akshare → bank scraper) and `mode="live"` triggers a refresh when data is missing or stale.  No module outside `packages/findata/` may import `yfinance`, `akshare`, or any fetcher directly.
2. **Private data stays out of git.** `local/`, `config/secrets.yaml`, `.parquet`, `.db`, `.csv` are all git-ignored.
3. **Use `logging`**, not `print()`. `import logging; _log = logging.getLogger(__name__)`.
4. **Services use `success()` / `failure()`** from `src/services/response.py`. API uses `_json_response()`.
5. **Every adapter returns `FetchResult`** — never an empty DataFrame without metadata.
6. **QualityGate runs 9 checks** on every write — empty data NEVER overwrites good data.
7. **Do not import private names across packages** — use re-export layers. `optifolio_contracts` is the public type layer.
8. **Prefer simplicity over compatibility.** This is pre-1.0. Delete dead code; remove unnecessary abstractions; don't keep "just in case" inheritance. Duck typing is sufficient when no `isinstance` checks exist. A deleted file is better than a kept compatibility shim.
9. **Method signatures: optional > required.** Use `context=None, **kwargs` instead of `context: Dict`. Let callers omit what they don't need. Use `Body(None)` for optional JSON bodies in FastAPI.
10. **Don't nest adapters.** Put fetcher logic directly in the `FetcherProtocol` implementation. No "thin wrapper → real fetcher" two-level delegation.

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
| `packages/findata/findata/__init__.py` | `fd` singleton — THE public data API |
| `packages/findata/findata/adapters/` | 12 provider fetchers + FetcherProtocol + registry |
| `packages/findata/findata/store/` | CanonicalStore, QualityGate, MarketDataRepository, schemas |
| `packages/findata/findata/serving/provider.py` | DataProvider — prices, ohlcv, returns, metrics, fx |
| `packages/findata/findata/orchestration/orchestrator.py` | Orchestrator — schedule + dispatch |
| `packages/optifolio_contracts/optifolio_contracts/__init__.py` | Pure types, identifiers, quality enums, sources |
| `src/api/fastapi_app.py` | FastAPI on port 8011 |
| `src/services/application.py` | Service graph (`get_application_services()`) |
| `src/services/portfolio_service_v2.py` | Canonical portfolio service |
| `src/analytics/alerts.py` | AlertEngine — wired, exposed at `/api/alerts` |
| `src/core/valuation.py` | ValuationEngine |
| `src/core/portfolio_book_db.py` | Personal book SQLite database (v11 schema) |
| `src/domain/` | Domain models — products, positions, exposures, cashflows, instruments |
| `src/runtime/bootstrap.py` | Local state initialization (DB, portfolio config) |
| `config/asset_registry.yaml` | Flat asset registry v2.0 |

## Live Documents

| Document | Purpose |
|----------|---------|
| `docs/CURRENT_STATE-656c946.md` | Live project map: test counts, known bugs, architecture diagram, next steps |
| `docs/TODO-656c946.md` | Prioritized task queue with file lists and acceptance criteria |
| `docs/AI_CONTEXT-656c946.md` | Full architecture reference — module contracts, data flow, rules |
| `docs/PRODUCT_VISION_AND_EXECUTION_PLAN.md` | Product north star (highest priority) |
| `docs/JULES-656c946.md` | How to dispatch work to Jules — issue format, batching, pitfalls |
| `docs/DECISIONS_PENDING-656c946.md` | Open architecture / financial questions for peer review |
| `docs/GLOSSARY-656c946.md` | Financial semantics dictionary |

Reference (read on demand): `ARCHITECTURE_FOUNDATION-656c946.md`, `CONTRACTS-656c946.md`, `DATA_AUDIT-656c946.md`, `FINANCIAL_LOGIC_AND_MODULE_DESIGN.md`, `TIME_ALIGNMENT_DESIGN.md`, `JULES_CLOUD_TASKS-656c946.md`

## Architecture Boundaries

```
packages/
  optifolio_contracts/  ← pure types, protocols, enums (stdlib only, NO pandas/akshare/fastapi)
      ↑
  findata/              ← self-contained data department
      │                    adapters → store → serving
      │                    orchestration (cadence, rate limiter, fallback)
      ↑
src/
  domain/       ← pure dataclasses (no FastAPI/SQLite/pandas in model definitions)
  core/         ← valuation, calendars, portfolio book DB, fees, corporate actions
  analytics/    ← risk analytics, alerts, exposure, liquidity, screening, attribution
  services/     ← business orchestration (no quant math here)
  api/          ← FastAPI routes (no business logic here)
  research/     ← backtest engine, model registry, Qlib adapter
  runtime/      ← local state bootstrap
config/         ← YAML configs (asset_registry, candidates, settings templates)
tools/          ← CLI utilities (scheduler, export, privacy_scan, health check)
tests/          ← pytest suite (run count from CURRENT_STATE)
```

**Dependency direction: contracts ← findata ← src.** Never the reverse.
`packages/` must NOT import from `src/`.
`optifolio_contracts` must NOT import from `findata`.

## Migration Traps — DO NOT DO

These are the most common ways an AI session can go wrong:

1. **DO NOT recreate `FinData/`.** Migrated to `packages/findata/` on 2026-06-23.
   `from FinData import fd` → `from findata import fd`.
2. **DO NOT recreate `src/data_foundation/` or `src/core/symbols.py`.** Moved to packages.
3. **DO NOT import from `src/` into `packages/`.** Dependency direction is one-way:
   `contracts ← findata ← src`. Never reverse.
4. **DO NOT recreate `app.py`.** Deleted 2026-06-23. All interfaces are FastAPI on port 8011.
5. **CANONICAL_MARKET_COLUMNS / STORE_VERSION**: currently defined in both
   `optifolio_contracts/market_data.py` and `findata/store/schemas.py` (KNOWN BUG).
   Target: single source in `optifolio_contracts/market_data.py`. Do NOT add a third definition.
6. **DO NOT add new data fetchers for asset types or markets the user does not hold.**
   Every fetcher must serve a real position. No "just in case" data coverage.
7. **All imports from deleted modules** must use their replacements:
   - `from FinData.store.schemas` → `from optifolio_contracts.market_data`
   - `from src.core.symbols` → `from optifolio_contracts.identifiers`
   - `from src.data_core.fetchers.factory` → module deleted, use `findata.adapters.FETCHER_REGISTRY`

## Design Principles (learned from code review)

- **Duck typing beats ABC inheritance.** `BocFetcher`, `IcbcFetcher`, etc. are looked up via `FETCHER_REGISTRY` and called by duck typing.
- **`to_dict()` lives on the dataclass.** Don't create standalone serialization helpers when the class already has `.to_dict()`.
- **Auto-wire services.** `get_application_services().alerts` automatically provides dependencies.
- **Inline, don't delegate.** One file, one class, no delegation chains.
- **Kill backwards-compat shims before 1.0.** No `store_version = STORE_VERSION` aliases.

## Naming Conventions

- Asset identifiers: uppercase ticker (`AAPL`), qualified CN fund (`fund.cn.000198`), CN stock (`600519`), bank WMP code (`GRSDR260056`)
- Asset types: `us_equity`, `cn_stock`, `cn_fund_etf`, `cn_fund_open`, `cn_money_market_fund`, `bank_wmp`, `forex`, `crypto`
- Canonical columns: `asset_id`, `date`, `open`, `high`, `low`, `close`, `adj_close`, `volume`, `currency`, `source`, `timezone`
- Date strings: ISO format `YYYY-MM-DD`
- Identifier format: `{domain}.{source}.{local_id}` (e.g., `fund.cn.000198`, `equity.us.AAPL`)

## Jules — Dispatching Work

Jules (Google Labs coding agent) watches this repo for issues labeled `jules`. It picks
them up, opens PRs, and you review/merge. Jules runs in parallel — multiple issues can
be worked simultaneously.

### Creating Issues
```bash
gh issue create --title "..." --body "..." --label jules --repo RebeccaKaku/OptiFolio
```
See `docs/JULES-*.md` for issue format, batching rules, and pitfall documentation.

### Batching Rules (CRITICAL)
1. **Batches MUST touch mutually exclusive files.** Jules runs parallel — same file = merge hell.
2. **One theme per batch.** "Delete dead modules" is one theme. Don't mix themes.
3. **Keep each batch ~2-6 files, ~100-500 line delta.**
4. **Pure-deletion batches are safest** — rarely break tests.
5. **Push all prerequisite changes BEFORE creating Jules issues** — Jules branches off current main.

### Issue Format
Every Jules issue MUST include these sections:
```markdown
## Scope — one sentence

### Files to DELETE
### Files to EDIT — what and why

### Acceptance
- Exact test command
- grep patterns that must return zero

### Financial impact
### Files NOT to touch
```

### PR Review Cycle
1. Create issues → set 20-minute `ScheduleWakeup` timer.
2. On wakeup: `gh pr list --repo RebeccaKaku/OptiFolio`.
3. For each Jules PR:
   a. `gh pr checkout <N>` → review diff.
   b. Check imports: `grep -rn "from FinData\|from src.data_foundation\|from src.core.symbols"`.
   c. `git merge origin/main` → resolve conflicts (Jules often branches off stale main).
   d. `python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider`.
   e. If green: `gh pr merge <N> --squash`. If red: fix, commit, push, then merge.
4. After merge: `git checkout main && git pull origin main`.
5. Dispatch next batch of issues.

### Fallback Escalation
- **20 min**: first check. If no PRs, reschedule another 20-minute timer.
- **40 min**: second check. If still no PRs, tasks may be too complex. Simplify the easiest issue and complete it yourself. Leave simplified versions for Jules.
- **2 hours**: third+ check. Jules likely down. Complete ALL remaining tasks yourself. Use `Agent` tool with `subagent_type: "general-purpose"` for parallel work.

### After Jules Merge
Always:
1. `git pull origin main`
2. Run full test suite
3. `grep -rn "from FinData\|from src.data_foundation" src/ tests/` — must be empty
4. Commit any fixes, push

## Working Protocol

- Product priority comes from `docs/PRODUCT_VISION_AND_EXECUTION_PLAN.md`.
- All 27 DS tasks (DS-001~027) are code-complete. New work should target integration gaps
  (wiring real data, replacing stubs, end-to-end verification) or be proposed as a new
  task with clear scope, allowed files, and acceptance criteria.
- Before editing, inspect `git status`, restate the contract, and list intended files.
  Preserve pre-existing changes.
- Stop and ask when: the spec conflicts with code, a file outside scope needs changes,
  real data is at risk, or an architecture decision is needed.
- Never stage, commit, push, touch `local/`, or write real financial data unless the
  user explicitly requests it.
- Finish with: changed files, financial assumptions, exact test results, non-goals,
  and residual risks.
