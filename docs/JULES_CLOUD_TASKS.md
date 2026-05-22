# Google Jules Cloud Task Handoff

Context: Codex has landed the first runnable architecture foundation for
OptiFolio. The new path is `data_foundation -> research/service -> FastAPI`,
with DuckDB/Parquet/Pandera for market data and a vectorbt-compatible backtest
boundary. Do not rewrite this foundation; extend it through the interfaces.

## Rules

- Keep private data out of git. Do not touch `local/`, real holdings, `.db`,
  `.parquet`, `.csv`, or `.safe_export/`.
- Avoid editing legacy Streamlit UI unless a task explicitly asks for migration.
- Keep changes small and PR-sized. One task equals one PR.
- Run `C:\Users\Z\miniconda3\python.exe -m pytest -q` before submitting.
- Run `C:\Users\Z\miniconda3\python.exe tools\privacy_scan.py --strict --with-detect-secrets`.

## Task 1: Ingestion Adapter Into MarketDataRepository

Goal: make existing fetchers write canonical market data.

Scope:
- Add a service or adapter that takes provider output from existing fetchers and
  calls `MarketDataRepository.save_raw`.
- Support at least one US equity via yfinance and one CN fund/ETF via existing
  akshare fetchers.
- Do not add private symbols or real portfolio data.

Acceptance:
- A test creates fake provider data and verifies it lands in `data/foundation`
  through a temporary repository.
- The repository can return a price matrix for saved assets.

## Task 2: Optimization Endpoint Hardening

Goal: make `/api/research/optimize` stable for normal user mistakes.

Scope:
- Validate method/objective values before calling `PortfolioOptimizer`.
- Return service-layer failure responses for unknown assets, insufficient price
  history, and optimizer infeasibility.
- Keep optimizer implementation in `portfolio/`; services should orchestrate only.

Acceptance:
- FastAPI tests cover invalid objective, empty data, and a successful fake data case.

## Task 3: Backtest Engine Vectorbt Adapter

Goal: replace the current deterministic fallback with a real vectorbt adapter while
keeping the existing `BacktestEngine.run` interface.

Scope:
- Use vectorbt inside `src/research/backtest.py` or behind a helper.
- Preserve `BacktestRequest` and `BacktestResult`.
- Keep the current pure-Pandas implementation as fallback if vectorbt import fails.

Acceptance:
- Existing `tests/test_research_backtest.py` still passes.
- Add one test asserting the engine reports whether it used vectorbt or fallback.

## Task 4: Test Hygiene Cleanup

Goal: separate runnable tests from scratch diagnostics.

Scope:
- Move or mark `tests/scratch/*` so full test output is not dominated by
  `PytestReturnNotNoneWarning`.
- Do not delete useful diagnostics; convert them to scripts if they are not real tests.

Acceptance:
- `pytest -q` has no return-value warnings from scratch tests.
- Core tests remain collected and passing.

## Task 5: Developer Runtime Script

Goal: make app startup boring and repeatable.

Scope:
- Add a documented command/script for starting FastAPI with the supported Python
  environment.
- Use a non-conflicting default port such as `8011`.
- Document that Python `>=3.11,<3.14` is required because the quant stack is not
  reliable on Python 3.14 yet.

Acceptance:
- README or docs show the exact command.
- A smoke test or documented manual check hits `/health`.
