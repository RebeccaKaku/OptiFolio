# DeepSeek Debug Handoff

This file is the coordination guide for parallel cleanup work. Please follow the ownership boundaries so our changes do not collide.

## Current Goal

Stabilize OptiFolio after the recent Gemini-generated changes. Priority is runtime correctness first, then tests, then naming/documentation cleanup.

## Do Not Touch

Codex is currently owning these areas:

- `src/api/enhanced_api_service.py`
- `src/api/portfolio_api.py`
- `src/core/portfolio_core.py`
- `app.py` API response handling paths
- Financial calculations, currency conversion, portfolio value semantics

If you find a bug in those files, write it down in your summary instead of editing it.

## Safe Areas For DeepSeek

You can work on these areas with low conflict risk:

- Documentation cleanup under `docs/`
- README consistency cleanup
- Branding text cleanup from `FM` / `NeoFM` to `OptiFolio`
- Test alignment in `tests/`, especially tests that call methods missing from the current implementation
- `.gitignore` and repository hygiene proposals
- Adding `*.example.yaml` style sample configs, if useful

## Task 1: Branding Cleanup

Search for old names:

```powershell
rg -n "NeoFM|FM 金融|Financial Manager|fm_|FM Dashboard|fm_database|fm_export" README.md docs app.py config src
```

Preferred output:

- Update docs and visible UI copy to `OptiFolio`.
- Do not rename database files or exported file prefixes yet unless Codex explicitly approves it.
- If a string is part of a public migration path or stored data path, leave it and report it.

## Task 2: Test Alignment

The current `tests/test_asset_registry.py` expects features that `src/asset_importer.py::AssetRegistry` does not implement:

- `conflicts`
- `register_conflict_asset`
- `find_assets_by_type`
- `detect_currency_from_name`
- `remove_asset`

Preferred output:

- Either mark obsolete tests as skipped with a clear reason, or rewrite them to match current behavior.
- Do not implement large new registry features unless there is an explicit design decision.
- Keep tests deterministic and avoid network calls by default.

## Task 3: Repo Hygiene Proposal

Inspect tracked runtime data and sensitive config:

```powershell
git ls-files config data
git check-ignore -v config\secrets.yaml data\fm_database.db data\raw\AAPL.parquet
```

Preferred output:

- Propose `.gitignore` changes for runtime data, SQLite DBs, generated JSON, and local secrets.
- Do not delete tracked files.
- Do not run destructive git commands.
- If changing `.gitignore`, keep sample/config templates tracked where appropriate.

## Validation

Use only lightweight checks unless dependencies are installed:

```powershell
python -m compileall -q .
python -c "import pathlib; print('ok')"
```

If `pytest` is unavailable, report that rather than installing dependencies.

## Final Summary Format

Please report:

- Files changed
- What was fixed
- What you deliberately did not touch
- Commands run and whether they passed
- Any issues Codex should handle in API/portfolio logic

## Next Assignment: Repo Hygiene Follow-Through

I see staged removals for tracked runtime data and `config/secrets.yaml`. Treat this as "stop tracking generated/local files", not as deleting the user's local working copies.

Please continue with these tasks:

- Confirm the data and secrets files still exist locally after being removed from the Git index.
- Add safe tracked templates if missing, for example `config/secrets.example.yaml`.
- Add a short note in README or docs explaining that real data, SQLite DBs, parquet files, raw JSON, and local secrets are ignored.
- Do not edit these Codex-owned files: `app.py`, `src/api/*`, `src/core/*`, `src/data_core/fetchers/*`.
- Do not stage or unstage Codex-owned files.
- Do not physically delete local data files.
- I noticed `src/core/database.py` was changed to use `data/optifolio.db`. Please do not make further edits under `src/core/`; just document any related observations in `docs/DEEPSEEK_TO_CODEX.md`.

Suggested validation:

```powershell
Test-Path config\secrets.yaml
Test-Path data\fm_database.db
git diff --cached --name-status
python -m compileall -q .
```

Please update `docs/DEEPSEEK_TO_CODEX.md` with what you changed and whether the removals are staged-only.
