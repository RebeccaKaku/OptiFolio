# Phase 0 Protection And Refactor Plan

## Phase 0 Status

The current workspace has been stabilized enough to continue safely tomorrow.

### Protected Local Files

These files are staged for removal from Git tracking, but they still exist locally and are now ignored:

- `config/secrets.yaml`
- `config/portfolio.yaml`
- `data/fm_database.db`
- `data/**/*.parquet`
- generated SQLite DB files such as `data/optifolio.db`

This is intentional repo hygiene: local data, real portfolio snapshots, and secrets should stay on the machine, not in Git history.

### New Safety Template

`config/secrets.example.yaml` is now tracked as the safe template for local secrets. Real credentials should live only in ignored `config/secrets.yaml`.

`config/portfolio.example.yaml` is now tracked as the safe template for local portfolio shape. Real holdings and cash balances should live only in ignored `config/portfolio.yaml`.

### Dependency State

Runtime and test dependencies have been installed in the current environment, including:

- `akshare`
- `yfinance`
- `aiohttp`
- `cvxpy`
- `ecos`
- `scs`
- `flask`
- `pytest`
- `pytest-cov`
- `selenium`

`requirements.txt` has been updated so a future environment can reproduce the same baseline.

### Current Validation

These checks passed after dependency installation:

```powershell
python -m compileall -q app.py src tests main.py
python -m pytest tests\test_asset_registry.py -q -p no:cacheprovider
```

The registry test file currently reports:

```text
2 passed, 8 skipped
```

The skips are intentional placeholders for AssetRegistry features that are not implemented yet.

### Known Workspace Notes

- Streamlit still exists but should now be treated as legacy.
- Do not invest more feature work into `app.py`.
- Existing Streamlit smoke tests showed the app can start, but the next product direction is a new FastAPI + React shell.
- `data/optifolio.db` is ignored and local-only.
- `data/fm_database.db` remains locally available for one-time migration compatibility.

## Next Direction

We are not rewriting the financial core. We are replacing the UI shell and gradually separating layers.

Target architecture:

```text
frontend/            # React + Vite UI
src/api/             # FastAPI routes
src/services/        # UI/API-facing business services
src/core/            # portfolio, assets, pricing, FX, database
src/data_core/       # fetchers and storage adapters
app.py               # legacy Streamlit entrypoint, frozen
```

## Phase 1: Freeze Streamlit And Build A New Shell

Tasks:

- Mark `app.py` as legacy in comments/docs. Done: new work should go through `src/services/` and `src/api/fastapi_app.py`.
- Create a FastAPI app entrypoint. Initial entrypoint: `src/api/fastapi_app.py`.
- Add API routes. Initial routes:
  - `GET /api/system/status`
  - `GET /api/dashboard/summary`
  - `GET /api/portfolio/value`
  - `GET /api/assets/overview`
- Create `src/services/` and move UI-facing orchestration there. Initial services now wrap system, dashboard, portfolio, and assets.
- Create a Vite React app under `frontend/`.
- Build a minimal dashboard page using the new API.

Definition of done:

- FastAPI starts independently of Streamlit.
- React page can render portfolio total value, cash value, asset type distribution, and system status.
- No UI route triggers import, DB migration, or network fetch unless explicitly requested.

## Phase 2: Service Layer Cleanup

Tasks:

- Add `DashboardService`.
- Add `PortfolioService`.
- Add `AssetService`.
- Move response-shaping out of Streamlit and into services.
- Return stable dictionaries or dataclasses with no UI framework dependencies.

Definition of done:

- Both FastAPI and any temporary Streamlit adapter can call the same services.
- API responses are consistent: `success`, `data`, `message`, `error`, `timestamp`.

## Phase 3: Portfolio And Pricing Hardening

Tasks:

- Keep local parquet as the first price source.
- Add explicit `price_source` metadata.
- Split FX into manual rates, local cache, and live fetcher.
- Remove noisy `print` calls and replace with logger usage.
- Ensure network failure never silently creates fake 1:1 FX for different currencies.

Definition of done:

- Offline portfolio valuation works deterministically.
- Online fetchers are optional enhancements, not startup dependencies.

## Phase 4: Asset Registry Decision

Tasks:

- Decide whether conflict assets are actually needed.
- If yes, design `conflict_id` and `is_conflict` deliberately.
- If no, delete or permanently rewrite skipped tests.
- Implement small, useful methods first:
  - `remove_asset`
  - `find_assets_by_type`
  - input validation for empty symbol/type

Definition of done:

- Default pytest does not rely on skipped placeholder tests.
- AssetRegistry tests reflect real product behavior.

## Phase 5: Repo Hygiene Finalization

Tasks:

- Confirm all local data and secret files are ignored.
- Keep only templates and tiny deterministic fixtures in Git.
- Document how to initialize local data.
- Consider moving test fixtures under `tests/fixtures/`.

Definition of done:

- Fresh clone has no private data.
- Existing local data survives branch changes.

## Phase 6: Remove Streamlit

Only do this after FastAPI + React covers the current dashboard.

Tasks:

- Delete or archive `app.py`.
- Remove Streamlit dependency if no longer used.
- Update README run commands.
- Remove Streamlit-specific docs.

Definition of done:

- Main local run path is FastAPI + React.
- Streamlit is not required for any supported workflow.
