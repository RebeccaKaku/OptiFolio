# Open Architecture Questions

**Date**: 2026-06-23
**Status**: Awaiting peer review / decision

These questions arose during the FinData → packages refactoring. They affect long-term architecture and should be decided before the next major refactoring step. Each question includes the current state, options, and trade-offs.

---

## Q1: Should `src/domain/` types be promoted to `optifolio_contracts`?

### Current State

`src/domain/` contains 15 files of pure dataclasses with zero external dependencies:
`products.py`, `positions.py`, `exposures.py`, `cashflows.py`, `instruments.py`,
`series.py`, `observations.py`, `fees.py`, `import_drafts.py`, `decision_journal.py`,
`macro_view.py`, `model_governance.py`, `purpose_buckets.py`, `relationships.py`,
`corporate_actions.py`.

`optifolio_contracts` is explicitly for "pure types, protocols, enums — stdlib only."

### Options

**Option A: Move all domain types to contracts.**
- Pro: One place for all pure types. No confusion about "does this go in domain or contracts?"
- Con: `optifolio_contracts` becomes very large (~15 files). Some domain types may be OptiFolio-specific rather than generally reusable.

**Option B: Keep contracts minimal; domain stays separate.**
- Pro: `contracts` stays as the "cross-package API surface" — only types shared between `findata` and `src/`. Domain types are `src/`-internal and can evolve independently.
- Con: Two places for types. An AI might put a type in the wrong place.

**Option C: Hybrid — contracts holds cross-package types; domain holds app-internal types.**
- What goes to contracts: types used by BOTH `findata` AND `src/` (identifiers, quality, sources, market_data columns).
- What stays in domain: types used only within `src/` (products, positions, cashflows, decision_journal, purpose_buckets).
- Pro: Clear boundary rule. Con: Requires judgment calls.

### Financial Implication

`ProductDefinition` and `PositionSnapshot` are the core financial identity types. If they move to `contracts`, any package (including future ones) can depend on them. If they stay in `src/domain/`, only `src/` code can use them directly.

---

## Q2: How to resolve dual `CANONICAL_MARKET_COLUMNS` / `STORE_VERSION`?

### Current State

`CANONICAL_MARKET_COLUMNS` and `STORE_VERSION` are defined in TWO places:
- `optifolio_contracts/market_data.py` (tuple-based, stdlib only)
- `findata/store/schemas.py` (list-based, imports pandas)

If one is changed without the other → silent data inconsistency.

### Options

**Option A: Single source in `contracts`. Delete the `findata` copy.**
- `findata/store/schemas.py` imports from `optifolio_contracts.market_data`.
- Pro: One source of truth. Con: `schemas.py` currently adds pandas-specific helpers (`_COLUMN_ALIASES`, `_normalize_columns`) that would need a separate home.

**Option B: `contracts` defines string constants; `findata` defines pandas dtypes.**
- `contracts` has column NAMES only. `findata` has column names + dtype mappings + normalization logic.
- Pro: Clean separation. Con: Two files must stay in sync for column names.

**Option C: `findata` is the single source; `contracts` re-exports.**
- Reverses the dependency direction for this one case.
- Pro: Simpler for findata development. Con: Violates the `contracts ← findata` dependency rule.

### Recommendation

**Option B** — `contracts` owns column names as string constants; `findata` adds dtype and normalization helpers that import from contracts. This preserves the dependency direction while giving each layer the right level of detail.

---

## Q3: Should `src/core/` be split?

### Current State

`src/core/` has 18 files mixing different concerns:

| Concern | Files |
|---------|-------|
| Valuation math | `valuation.py`, `book_valuation.py` |
| SQLite persistence | `portfolio_book_db.py`, `portfolio_ledger.py`, `portfolio_history.py`, `portfolio_history_tracker.py` |
| Asset management | `asset_manager.py`, `enhanced_asset_manager.py` |
| Calendars | `calendars.py` |
| Configuration | `config_manager.py`, `paths.py` |
| Fees | `fees.py` |
| Corporate actions | `corporate_actions.py` |
| Infrastructure | `cache.py`, `exceptions.py`, `interfaces.py`, `logger.py` |

### Options

**Option A: Split into `src/core/` (pure computation) and `src/persistence/` (SQLite).**
- `core/` keeps: valuation, calendars, fees, corporate_actions, interfaces.
- `persistence/` takes: portfolio_book_db, portfolio_ledger, portfolio_history*.
- Pro: Clean separation of "what to compute" from "how to store." Con: Another top-level directory.

**Option B: Keep as-is for now.**
- Pro: No churn. Con: The blob grows. Each new persistence concern gets dumped in core/.

**Option C: Three-way split: `core/` (math), `persistence/` (SQLite), `config/` (paths, config_manager).**
- Pro: Even cleaner. Con: More directories.

---

## Q4: Is the three-layer calendar split correct?

### Current State

| Layer | File | Content |
|-------|------|---------|
| contracts | `optifolio_contracts/calendars.py` | `ExchangeCalendarProtocol` — abstract interface (timezone, is_business_day) |
| findata | `findata/calendars/__init__.py` | Timezone registry — hardcoded asset_type → IANA timezone mapping |
| src/core | `src/core/calendars.py` | Full `ExchangeCalendar` — pandas, holidays, close_time, business day logic |

### Question

Is the three-layer split intentional and correct, or should `findata`'s timezone registry and `src/core`'s full calendar be merged?

### Arguments

**Keep three layers**: Each layer adds capability without pulling dependencies downward. `findata` doesn't need pandas for timezone lookup. `src/core` needs pandas for holiday calendars. This is dependency inversion done right.

**Merge findata + src/core**: The timezone registry in findata is trivial (40 lines, no logic). It could live in `src/core/calendars.py` and findata could import from src/core — but this VIOLATES the `packages/` ← `src/` dependency rule.

### Recommendation

Keep three layers. The split is the correct application of dependency inversion. Just document it clearly: `contracts` defines the WHAT, `findata` provides the minimal WHERE (timezone), `src/core` provides the full WHEN (holidays, business days).

---

## Q5: Does the four-document structure cover multi-AI needs?

### Proposed Structure

| Document | Question It Answers | Audience |
|----------|-------------------|----------|
| `CLAUDE.md` | "How do I work with this project?" | Any AI entering the project |
| `AI_CONTEXT.md` | "How does everything fit together?" | AI implementing features |
| `CURRENT_STATE.md` | "Where are we right now?" | AI resuming after a break |
| `PRODUCT_VISION.md` | "What are we building and why?" | AI deciding what to work on next |

### Questions

1. Is four documents the right number? Too many? Too few?
2. Should `OPEN_QUESTIONS.md` be a permanent doc or temporary (delete after decisions)?
3. Should we add a `DECISIONS.md` (ADR log) for recording architecture decisions once made?
4. Should `plans/deepseek/README.md` remain the task execution contract, or should it be merged into `AI_CONTEXT.md`?

---

## Financial Semantic Questions

These are less about code organization and more about getting the domain model right:

### F1: Product vs Instrument — are we clear?

`PRODUCT_VISION` §5.3 says a "USD WMP" has four layers: holding form, denomination currency, underlying risk, purpose. The code has `ProductDefinition` and separate exposure tracking. But `src/domain/instruments.py` exists alongside `src/domain/products.py`. What exactly is an `Instrument` vs a `Product` in our model? When would code need one vs the other?

### F2: Valuation source priority — where is the authoritative implementation?

`PRODUCT_VISION` §7 (M2/DS-012) specifies: manual confirmed market value > public NAV × shares > carried forward old value. Where in the codebase does this priority chain live? Is it in `src/core/valuation.py`? `src/core/book_valuation.py`? Both?

### F3: Currency handling — three currencies, one model?

The spec distinguishes: product currency (what the product is denominated in), account currency (what the bank account holds), and reporting currency (CNY for the user). Does the current `ValuationResult` carry all three? Are FX conversions applied at the right layer?

### F4: Quality tags — are they used consistently?

`ValuationQuality` enum: `ACTUAL / REPORTED / ESTIMATED / PROXY / UNKNOWN`. Every position, every valuation result should carry this tag. Is this consistently applied across the codebase? Or do some code paths silently assume `ACTUAL`?

---

## Next Steps

1. Review these questions with domain experts.
2. Record decisions (create `docs/DECISIONS.md` if needed).
3. Update `AI_CONTEXT.md` and `CLAUDE.md` to reflect decisions.
4. Implement the decided changes.
