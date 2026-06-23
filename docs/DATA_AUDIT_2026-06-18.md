# FinData Data Audit Report — 2026-06-18

> **Note (2026-06-23):** File paths updated for FinData → packages migration.
> Line numbers may have shifted; substance of findings unchanged.

**Auditor:** Claude (Financial Data QA) | **Tests:** 641/641 pass | **Branch:** main

---

## Executive Summary

FinData is well-architected with solid test coverage, but **the data it serves is dangerously stale, partially incorrect, and has structural quality issues that tests do not catch**. 18 issues found across 4 severity tiers.

---

## 🔴 CRITICAL (5 issues)

### C1. ALL 322 assets are stale — no data newer than 14 days

**File:** `data/foundation/market_prices.parquet`
**Evidence:** Every asset last updated before 2026-06-11. US equities (AAPL, GOOGL, QQQ, GLD, TLT, SGOV) end at 2024-02-06 — **>2 years stale**.

**Root cause:** Data was bulk-loaded via `archive_migration`, not through the live orchestrator. The orchestrator works but isn't run regularly. No cron/background refresh mechanism exists.

### C2. Hardcoded rate fallbacks are wrong and used in production

**File:** `packages/findata/findata/serving/provider.py` (formerly `FinData/serving/provider.py`):
115-119`
```python
_RATE_FALLBACKS = {
    "1y_cn": 0.017,   # 1.7% — actual SHIBOR 1Y ≈ 1.46% (0.2pp off)
    "5y_cn": 0.036,   # 3.6% — actual CN 5Y bond ≈ 1.4% (2.2pp off!)
    "10y_cn": 0.028,  # 2.8% — actual CN 10Y bond ≈ 1.7% (1.1pp off!)
}
```
**Impact:** Every valuation using `fd.rate("5y_cn")` gets a risk-free rate 2.2pp wrong. Tests at `test_findata_serving.py:269` assert against this wrong value, cementing the error.

**Fix:** Replace hardcoded fallbacks with lookups from stored SHIBOR observations; add `1y_us` based on SOFR.

### C3. ALL 9294 rows have timezone="UTC" — cross-market time alignment broken

**File:** `data/foundation/market_prices.parquet` (timezone column), `packages/findata/findata/store/schemas.py` (normalization code exists but timezone param never passed during import)

**Impact:** US equities should be `America/New_York`, CN stocks `Asia/Shanghai`. "Monday's close" may be tagged on wrong calendar date.

### C4. Policy rates 300+ days stale

**File:** `data/foundation/observations.parquet`
| Series | Last Date | Days Stale |
|--------|-----------|------------|
| RATE_POLICY_EU | 2025-07-24 | 329 |
| RATE_POLICY_JP | 2025-07-31 | 322 |
| RATE_POLICY_US | 2025-07-31 | 322 |
| RATE_POLICY_UK | 2025-08-07 | 315 |

**Fix:** `python tools/sync_macro_rates.py` — tool exists and is correct, just not being run.

### C5. Duplicate asset IDs — same security under two IDs

**File:** `data/foundation/market_prices.parquet`
| sh/sz prefixed | Plain 6-digit | Security |
|----------------|-------------|----------|
| sh600028 | 600028 | Sinopec |
| sh600519 | 600519 | Kweichow Moutai |
| sh601398 | 601398 | ICBC |
| sh601899 | 601899 | Zijin Mining |
| sz000001 | 000001 | Ping An Bank |

**Impact:** `fd.prices("600519")` ≠ `fd.prices("sh600519")`. Portfolio valuation would double-count or miss positions.

**Fix:** Canonical convention is 6-digit CN codes. Migrate `shXXXXXX`/`szXXXXXX` → plain codes, deduplicate.

---

## 🟡 HIGH (4 issues)

### H1. Tests never validate against live/recent real-world market data

**File:** All test files — every test uses synthetic `_make_df()` with `np.linspace(100, 150, 60)`.
**Verification:** Live fetchers DO work — AAPL=$299.24, USD/CNY=7.30 confirmed 2026-06-18.
**Fix:** Add smoke tests per fetcher type verifying realistic price ranges and OHLCV relationships.

### H2. `DataProvider.fx_rate()` never uses live FX rates

**File:** `packages/findata/findata/serving/provider.py` (formerly `FinData/serving/provider.py`):
162-173`, `src/core/valuation.py:127-169`
**Root cause:** `FxRateProvider.get_rate()` has `try_live=False` by default. No code path calls it with `try_live=True`. Stored FX data is also stale.

### H3. Tests assert against hardcoded stubs instead of verifying reasonableness

**File:** `tests/test_findata_serving.py:254-285`
- `assert result["value"] == pytest.approx(0.017)` — 1y_cn stub
- `assert result["value"] == pytest.approx(0.036)` — 5y_cn stub (2.2pp wrong)
- `assert result["value"] == pytest.approx(0.028)` — 10y_cn stub (1.1pp wrong)
- `assert result > 0` for fx_rate — too weak, should check 6-8 range for USD/CNY

### H4. 57 rows have zero volume AND flat OHLCV (O=H=L=C)

**File:** `data/foundation/market_prices.parquet`
**Affected assets:** `23GS8125`, `AMHQLXTTUSD01B`, `WPXK24M1203A`
**Impact:** Non-trading days stored as trading days. QualityGate's spike check (50% threshold) doesn't flag 0% changes.
**Fix:** Add QualityGate check for "suspicious flat trading days" — flag when O=H=L=C AND volume=0.

---

## 🟠 MEDIUM (5 issues)

### M1. Tests don't verify `warning` field content for hardcoded stubs

**File:** `tests/test_findata_serving.py:261`
`assert "warning" in result` only checks key existence, not value. Would pass with `"warning": None`.

### M2. US equities source="archive_migration" — not real fetcher label

All US data has `source="archive_migration"`. If orchestrator re-ingests via `UsEquityFetcher`, source changes to `"akshare-sina"`, potentially breaking consumers.

### M3. 100% of `released_at` and `observed_at` are NaN in observations

**File:** `data/foundation/observations.parquet` (3586 rows)
**Root cause:** `tools/sync_macro_rates.py` normalization functions don't populate these fields.

### M4. Redundant test classes across files

**Files:** `tests/test_findata_storage.py` AND `tests/test_findata_serving.py`
Both contain near-identical `TestFdPrices`, `TestFdPanel`, `TestFdSingleton`, `TestFdBackCompat` classes.
**Fix:** Consolidate into one canonical location, remove duplicates.

### M5. `annualized_return` with <5 data points is unstable

**File:** `packages/findata/findata/serving/provider.py` (formerly `FinData/serving/provider.py`):
262-266`
Formula `(1 + total) ** (365/days) - 1` produces extreme values with 1-3 data points. Guarded for <2 but not for 3-5 over <1 week.

---

## 🟢 LOW (4 issues)

### L1. No check that FETCHER_REGISTRY values match expected concrete classes

**File:** `tests/test_findata_fetcher.py:210-219`
Only checks `isinstance(inst, FetcherProtocol)`, not that `FETCHER_REGISTRY["cn_stock"]` is specifically a `CnStockFetcher`.

### L2. `_RATE_FALLBACKS` has no USD risk-free rate

`risk_free_rate=0.0` is the default for `DataProvider.metrics()`. SOFR was 3.6% on 2026-06-09.
**Fix:** Add `1y_us` based on SOFR observations.

### L3. `test_sync_macro_rates.py` uses 2024 dates

All test data is January-February 2024 — not catching staleness problems.

### L4. No end-to-end integration test

No test covers: `Orchestrator.schedule() → fetch → QualityGate.inspect() → CanonicalStore.accept() → DataProvider.prices()`. Layer-boundary bugs (like timezone=UTC propagation) are invisible.

---

## Data Quality Metrics Summary

| Metric | Value | Status |
|--------|-------|--------|
| Assets in store | 322 | — |
| Assets with data <7 days old | 0/322 | 🔴 |
| Assets with data <14 days old | 0/322 | 🔴 |
| US equities data end date | 2024-02-06 | 🔴 |
| Observation series stale (>300d) | 4/14 | 🔴 |
| Duplicate asset IDs | 5 pairs | 🔴 |
| Rows with zero volume | 57/9294 (0.6%) | 🟡 |
| Rows where O=H=L=C | 57/9294 (0.6%) | 🟡 |
| Timezone="UTC" rows | 9294/9294 (100%) | 🔴 |
| NaN in close column | 0/9294 | ✅ |
| Future leakage (known_at < effective_date) | 0/3586 | ✅ |
| Hardcoded 1y_cn rate error | 0.2pp (13.7%) | 🔴 |
| Hardcoded 5y_cn rate error | ~2.2pp (~157%) | 🔴 |
| Tests passing | 641/641 | ✅ |

---

## Fix Plan (dependency order)

### Phase 1: Crossroads fixes (must go first — unblock everything else)

| Seq | Issue | What | Why first |
|-----|-------|------|-----------|
| 1a | C2 | Replace `_RATE_FALLBACKS` with stored-observation lookup, add `1y_us` from SOFR | Every rate consumer gets wrong data. Fixing data source before refreshing data. |
| 1b | C5 | Deduplicate sh/sz-prefixed asset IDs → plain 6-digit codes | Cross-module: affects storage, serving, valuation, and all tests |
| 1c | H4 | Add "flat price" check to QualityGate | Data quality gate must be correct before re-ingesting data |
| 1d | M4 | Consolidate redundant test classes | Tests are the safety net for all Phase 2 work |

### Phase 2: Independent fixes (can run in parallel agents)

| Agent | Issues | What |
|-------|--------|------|
| A | C1, C4 | Run `sync_macro_rates.py` + `Orchestrator.full_scan()` to refresh all data |
| B | C3 | Add timezone parameter to data import/re-ingestion; fix normalization to pass exchange timezone |
| C | H1, H3 | Add live-data validation tests; replace hardcoded-value assertions with range checks |
| D | H2, M1, M3 | Wire `try_live=True` in fx_rate path; strengthen warning assertion; populate `released_at` in sync tool |
| E | M5, L1, L2, L3 | Guard annualized_return on min data points; add concrete class checks; add USD risk-free rate; update sync test dates |

---

## Agent Task Definitions

### Agent A: Refresh all stale data
- Run `python tools/sync_macro_rates.py` to refresh policy + interbank + FRED rates
- Run `Orchestrator.full_scan()` to refresh all 322 assets through live fetchers
- Verify data freshness after refresh
- Verify US equities now have 2026 data

### Agent B: Fix timezone handling
- Identify all data import paths that don't pass `timezone` parameter
- Map asset types → exchange timezones (US → `America/New_York`, CN → `Asia/Shanghai`, etc.)
- Update `normalize_market_frame()` calls to pass correct timezone
- Re-ingest data with correct timezone (or patch existing data)

### Agent C: Add live data validation tests
- Add fetcher smoke tests: verify each fetcher returns data with realistic ranges
- Replace hardcoded rate assertions with range checks against stored observations
- Add OHLCV relationship tests (low ≤ close ≤ high, etc.)

### Agent D: Fix FX rate live path + observation metadata
- Wire `try_live=True` in `DataProvider.fx_rate()` live path
- Strengthen warning assertion in rate tests
- Populate `released_at` field in `sync_macro_rates.py` normalization functions

### Agent E: Edge case hardening
- Add `min_data_points` guard to `_calc_annualized_return`
- Add concrete class assertions to fetcher registry tests
- Add `1y_us` rate based on SOFR observations to `_RATE_FALLBACKS`
- Update sync test dates to current year
