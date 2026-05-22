# Jules PR Review - 2026-05-22

GitHub CLI authentication is currently expired in the local environment, so this
review is based on fetched remote branches rather than direct PR comments.

## Reviewed Branches

- `origin/performance/concurrent-fetching-11702494980423128856`
- `origin/feat-add-bosc-icbc-boc-fetchers-3932753337894319283`

## Performance PR: Concurrent Data Fetching

Decision: accepted with local porting instead of direct merge.

Reason:
- The branch has no merge base with current `origin/main`, so it cannot be
  merged cleanly.
- The core idea is sound: throttle requests per provider/asset type while
  allowing unrelated provider groups to fetch concurrently.
- The implementation was ported into current `src/data_loader.py` with a focused
  regression test in `tests/test_data_loader.py`.

Validation:
- `C:\Users\Z\miniconda3\python.exe -m pytest tests\test_data_loader.py -q`
  passes.

## BOSC / BOC / ICBC Fetcher PR

Decision: do not merge yet. Needs revision.

Findings:
- The PR changes `config/asset_registry.yaml`. Fetcher work must not mutate
  shared registry/config state, especially while privacy cleanup is still active.
- `BoscFetcher.fetch()` always returns an empty DataFrame, so it implements the
  interface but cannot serve the normal data-loader path. A fetcher should either
  return canonical OHLCV data for a symbol/date range or be exposed as a separate
  discovery/snapshot service.
- Tests are too weak for ICBC and BOSC. `test_icbc_fetcher_sync_defaults` has no
  assertion, and BOSC only checks that a file exists rather than validating
  schema, index type, and close values.
- `httpx.AsyncClient(verify=False)` in BOSC disables TLS verification globally
  for that fetcher. If this is truly required, it needs an explicit comment,
  narrow configuration, and a test path that does not normalize insecure network
  behavior.
- The PR updates dependencies from an old `pyproject.toml` shape and would drop
  current architecture dependencies if merged naively.
- The branch has no merge base with current `origin/main`, so Jules should rebase
  or recreate the PR from current main before submitting changes.

Required revision:
- Recreate the PR from current `origin/main`.
- Do not modify `config/asset_registry.yaml`.
- Add `BoscFetcher.fetch()` behavior that returns a validated OHLCV DataFrame,
  or split BOSC discovery/snapshot sync into a non-fetcher service with clear
  naming.
- Strengthen tests to assert returned DataFrames, saved Parquet content, index
  type, expected values, and empty/error cases.
- Keep dependency changes additive against the current `pyproject.toml` and
  `requirements.txt`.
- Run full tests and the privacy scan before resubmitting.
