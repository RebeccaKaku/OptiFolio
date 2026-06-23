# Google Jules Cloud Task Handoff

> **Status (2026-06-23): All tasks (6-11) complete. All DS tasks (001-027) implemented.
> This document is retained for historical reference. File paths reference the
> pre-migration `FinData/` structure; current equivalents are in `packages/findata/`.**

Context: OptiFolio v0.2.0, 982 tests green. FinData → packages migration complete.
Streamlit `app.py` is FROZEN — all new work goes to
`src/api/`, `src/services/`, `src/analytics/`, `packages/findata/`.

## Rules

- Keep private data out of git. Do not touch `local/`, real holdings, `.db`,
  `.parquet`, `.csv`, `.safe_export/`, `config/secrets.yaml`.
- Do NOT edit `app.py` (legacy Streamlit). All API work goes in `src/api/fastapi_app.py`.
- Keep changes small and PR-sized. One task = one PR.
- Run `python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider` before submitting.
- Run `python tools/privacy_scan.py --strict --with-detect-secrets` before submitting.
- Use `logging` (not `print()`) for new log lines. Import from `logging.getLogger(__name__)`.
- Follow existing response conventions: services return via `success()` / `failure()` from
  `src/services/response.py`; API handlers use `_json_response()`.
- The fd singleton (`from findata import fd`) is the only public data API — do not import
  fetchers directly.

---

## Task 6 (DONE): Wire AlertEngine Into Application Services

**Zone**: A — Alerts
**Files**: `src/services/application.py`, `src/api/fastapi_app.py`
**Depends on**: nothing (crossroads H5 already fixed)

Goal: make `AlertEngine` reachable from the API and daily scheduler.

Scope:
- In `src/services/application.py`, import `AlertEngine` from `src.analytics.alerts`
  and add an `alerts: AlertEngine` field to the `ApplicationServices` dataclass.
  Instantiate it in `get_application_services()`.
- In `src/api/fastapi_app.py`, add two endpoints:
  - `GET /api/alerts` — returns recent alerts. For now, calls
    `get_application_services().alerts.run_all()` with an empty context dict
    (this returns all alerts that don't need external data).
  - `POST /api/alerts/run` — accepts an optional JSON body with context keys
    (`quality_summary`, `concentration_report`, `fx_exposure_report`,
    `liquidity_report`, `returns_summary`, `fund_statuses`, `maturity_dates`,
    `threshold_overrides`). Passes context to `AlertEngine.run_all(**ctx)`.
    Returns the list of `Alert` dataclasses serialized to dicts.
- Wrap alert dataclass serialization: each `Alert` has fields `alert_id`, `title`,
  `reason`, `evidence`, `severity`, `suggested_action`, `created_at`. The endpoint
  should return them as a JSON list.

Acceptance:
- `GET /api/alerts` returns 200 with a JSON list (may be empty if no data context provided).
- `POST /api/alerts/run` with `{"quality_summary": {"threshold_pct": 50.0, "stale_assets": ["AAPL"], "n_days": 5}}` returns a list containing a `stale_price_threshold` alert.
- `tests/test_fastapi_app.py` still passes. Add one new test for each endpoint.
- No imports from `app.py` or legacy modules.

---

## Task 7 (DONE): FinData Store Cleanup — Dead Code And Re-Export Layer

**Zone**: B — Data Foundation
**Files**: `FinData/adapters/interfaces.py` (DELETE), `FinData/store/schemas.py` (EDIT)
**Depends on**: nothing

Goal: remove orphaned code and complete the re-export layer so FinData is truly self-contained.

Scope:
- **Delete `FinData/adapters/interfaces.py`**. Verify no file imports from it:
  ```bash
  rg "from.*interfaces|import.*interfaces" --type py
  ```
  If the grep returns nothing (it shouldn't — `AsyncBaseFetcher` was confirmed dead code
  in the 2026-06-05 audit), delete the file.
- **Fix `FinData/store/schemas.py`**: add re-exports for `_COLUMN_ALIASES`,
  `_canonical_column_name`, and `STORE_VERSION` from `src.data_foundation.schemas`.
  Remove the duplicate `store_version: str = "1.0"` (dead code — never imported).
- **Fix `FinData/store/quality.py`**: change the import at line 24 from
  `from src.data_foundation.schemas import _COLUMN_ALIASES, _canonical_column_name`
  to `from .schemas import _COLUMN_ALIASES, _canonical_column_name`.
  This removes the cross-package private-name import.

Acceptance:
- `FinData/adapters/interfaces.py` no longer exists.
- `FinData/store/schemas.py` exports `_COLUMN_ALIASES`, `_canonical_column_name`, `STORE_VERSION`.
- `FinData/store/quality.py` imports those names from `FinData.store.schemas`, not from `src.data_foundation.schemas`.
- Full test suite passes: `python -m pytest tests/ -q --basetemp .pytest_tmp -p no:cacheprovider`.
- No new warnings.

---

## Task 8 (DONE): Fix Dashboard Hardcoded Date And Approximate Position Values

**Zone**: C — API / Dashboard
**Files**: `src/api/static_dashboard.py`
**Depends on**: nothing

Goal: fix two bugs in the static dashboard HTML/JS generator.

Scope:
- **Bug 1 (H7)**: Line 127 has a hardcoded date in the JavaScript:
  ```javascript
  const res = await get('/api/portfolio/v2/risk/exposure?as_of=2024-02-07');
  ```
  Replace `2024-02-07` with a dynamic value:
  ```javascript
  const today = new Date().toISOString().slice(0, 10);
  const res = await get(`/api/portfolio/v2/risk/exposure?as_of=${today}`);
  ```
- **Bug 2 (M12)**: Lines 149-155 evenly split `ac.value` across `ac.asset_ids`.
  This is a misleading approximation. Instead, if per-asset values are not
  available from the exposure endpoint, display the asset class total and
  list the member asset_ids without fake per-asset numbers. Change the table
  to show `ac.value` as the class total and list `ac.asset_ids.join(", ")`
  as members rather than showing `ac.value / ac.asset_ids.length` per asset.

Acceptance:
- No hardcoded dates in the generated JavaScript.
- Positions table shows class totals + member list, not fake per-asset splits.
- The `static_dashboard.py` still imports and runs without error.
- No new dependencies.

---

## Task 9 (DONE): Fix Pandas FutureWarning In Ingestion Log

**Zone**: B — Data Foundation
**Files**: `FinData/store/ingestion_log.py`
**Depends on**: nothing

Goal: fix the pandas FutureWarning about DataFrame concatenation with empty or
all-NA entries.

Scope:
- In `FinData/store/ingestion_log.py` around line 53, there is:
  ```python
  df = pd.concat([existing_df, df], ignore_index=True)
  ```
  The warning says: "The behavior of DataFrame concatenation with empty or
  all-NA entries is deprecated. In a future version, this will no longer
  exclude empty or all-NA columns when determining the result dtypes."
- Fix: check if `existing_df` is empty before concat. If `existing_df.empty`,
  return `df` directly. If `df.empty`, return `existing_df` directly.
  Only concat when both are non-empty.
- Do not change the method signature or return type.

Acceptance:
- The FutureWarning no longer appears when running `test_ingestion_log_save_load`.
- `python -m pytest tests/test_ingestion_log.py -v` passes with zero warnings.
- Full test suite still passes.

---

## Task 10 (DONE): Unify Exposure Pct Convention

**Zone**: D — Financial Core
**Files**: `src/analytics/exposure.py`
**Depends on**: nothing

Goal: fix the inconsistent convention where `ExposureItem.pct` uses a fraction
(0-1) but `ConcentrationItem.pct` uses a percentage (0-100).

Scope:
- In `src/analytics/exposure.py`:
  - Find `ExposureItem` dataclass — its `pct` field stores `data["value"] / total_value`
    (a decimal fraction like 0.6 for 60%).
  - Find `ConcentrationItem` dataclass — its `pct` field stores
    `round(bucket["value"] / total_value * 100, 2)` (a percentage like 60.0 for 60%).
  - **Decision**: unify to fractions (0-1), not percentages. Update `ConcentrationItem`
    to store `round(bucket["value"] / total_value, 4)` (fraction).
  - Update ALL code that reads `ConcentrationItem.pct` and expects a percentage.
    Search with: `rg "ConcentrationItem|concentration.*pct|\.pct" src/analytics/ tests/`
  - Update `ExposureAnalyzer.analyze()` and any method that creates `ConcentrationItem`
    to multiply by 100 only at display/render time, not at storage time.
  - Update tests in `tests/test_analytics_exposure.py` to expect fractions.

Acceptance:
- `ExposureItem.pct` and `ConcentrationItem.pct` are both in 0-1 range.
- All existing tests pass after updating expected values.
- `python -m pytest tests/test_analytics_exposure.py tests/test_analytics_concentration.py -v` passes.

---

## Task 11 (DONE): Wire Scheduler Daily Alert Check

**Zone**: A — Alerts
**Files**: `tools/scheduler.py`
**Depends on**: Task 6 (AlertEngine in ApplicationServices)

Goal: add an alert-check step to the daily pipeline so stale prices,
concentration creep, and other risks generate notifications automatically.

Scope:
- In `tools/scheduler.py`, after the existing price-ingestion step, add a new
  step that:
  1. Calls `ApplicationServices.research.run_stale_price_check()` to get
     quality data.
  2. Calls `ApplicationServices.alerts.run_all()` with that context.
  3. Logs each alert at WARNING (severity=warning) or ERROR (severity=critical).
  4. If the Bark MCP is configured, sends a notification for critical alerts.
     Use `logging.getLogger("optifolio.alerts").warning(...)` for now;
     Bark integration is a separate follow-up.
- Wrap the alert step in try/except so a failure in alerting does not block
  the rest of the daily pipeline.
- Add a CLI flag `--skip-alerts` to `scheduler.py` to skip the alert step.

Acceptance:
- `python tools/scheduler.py --dry-run` shows the alert step in the pipeline plan.
- If the quality store has data, alerts are checked and logged.
- Alert step failure does not crash the scheduler.
- `--skip-alerts` flag works.
- No imports from `app.py`.

---

## Dependency Graph

```
Task 6 (AlertEngine wiring) — DONE ──→  Task 11 (scheduler alerts) — DONE
Task 7 (store cleanup) — DONE            ← independent
Task 8 (dashboard fixes) — DONE          ← independent
Task 9 (pandas FutureWarning) — DONE     ← independent
Task 10 (pct convention) — DONE          ← independent
```

Only Task 11 depends on Task 6. All other tasks can run in parallel.

---

## DS Task Status (2026-06-23)

| Task | Status | Description |
| :--- | :--- | :--- |
| DS-001~027 | ✅ Complete | All 27 DeepSeek tasks implemented |

> See `docs/CURRENT_STATE.md` for current milestone status and remaining integration work.

## Quick Start For Jules

Each task above has:
- Exact file paths to edit
- The code to change (old → new)
- The exact test command to verify
- Clear acceptance criteria

Create one GitHub issue per task with the `jules` label. The issue title should
match the task title (e.g. "Task 6: Wire AlertEngine Into Application Services").
Paste the task description (Goal, Scope, Acceptance) into the issue body.
