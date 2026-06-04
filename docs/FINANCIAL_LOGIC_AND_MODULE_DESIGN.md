# Financial Logic And Module Design

**Date**: 2026-06-03
**Status**: proposed target architecture

This document is the top-level design for making OptiFolio robust as asset types, macro data, indexes, benchmarks, and algorithms expand. The key idea is simple: do not let provider APIs define the domain model. Define financial semantics first, normalize provider data into those contracts, then let algorithms consume explicit panels and feature sets.

Product direction: OptiFolio should first be a personal asset risk engine and allocation-advice engine, not a return-prediction toy. The first valuable questions are:

- What do I really hold?
- Which risks produce my return?
- How liquid is the portfolio?
- What happens in bad scenarios?
- Which positions create concentration, FX, credit, duration, or liquidity mismatch?
- Which adjustments are explainable and consistent with my goals?

---

## Design Principles

1. Separate financial identity from data source.
   `AAPL` is an instrument; `yfinance` is only one provider. A China PMI series is a macro indicator; AkShare is only one provider.

2. Separate tradable assets from non-tradable information.
   Stocks, ETFs, funds, bank wealth products, cash, bonds, futures, options, and crypto can be holdings. Indexes, macro series, yield curves, factor signals, and benchmarks are usually inputs to research and risk, not portfolio positions unless mapped to a tradable proxy.

3. Every time series must carry time semantics.
   A price date, a macro release date, a revised macro value, and an index level are not interchangeable. The system must know when a value became knowable.

4. Algorithms consume views, not raw data.
   Optimization/backtest/valuation should consume `PricePanel`, `ReturnPanel`, `FeaturePanel`, `BenchmarkPanel`, `ConstraintSet`, and `TransactionCostModel`, not fetcher DataFrames.

5. Metadata is part of the result.
   A NAV without price source, price date, FX source, corporate action treatment, and stale-data flags is not a financial result; it is just a number.

6. Model relationships as a graph, not as one more asset-type enum.
   A fund can hold a portfolio. A future can reference an index. An ETF can track an index but hold a basket. A structured note can reference several indexes with a payoff formula. These are edges between objects, not new one-off fields.

7. Separate facts, estimates, and advice.
   A real holding is a fact. A fund's current equity exposure inferred from a quarterly report is an estimate. A rebalance recommendation is advice. These must carry different timestamps, quality flags, and confidence levels.

---

## Domain Taxonomy

### Product, Position, Exposure

For personal finance workflows, the system needs a user-facing layer above raw instruments. A product is what the user bought; an instrument/series/portfolio graph explains what the product is economically.

Minimum product table:

```python
ProductDefinition(
    product_id: str,
    name: str,
    product_type: str,       # deposit, money_fund, bond_fund, mixed_fund, bank_wmp, fx, structured_deposit
    issuer: str | None,
    manager: str | None,
    currency: str,
    risk_level: str | None,
    liquidity_type: str | None,
    fee_policy_id: str | None,
    benchmark_id: str | None,
    primary_instrument_id: str | None,
    data_source: str,
    metadata: dict = {},
)
```

Minimum position table:

```python
PositionSnapshot(
    date: date,
    account_id: str,
    product_id: str,
    quantity: float | None,
    market_value: float,
    cost_basis: float | None,
    currency: str,
    available_amount: float | None,
    lockup_end_date: date | None,
    metadata: dict = {},
)
```

Minimum exposure table:

```python
ExposureSnapshot(
    date: date,
    product_id: str,
    exposure_type: str,      # asset_class, region, currency, industry, duration, credit, option_payoff
    bucket: str,             # equity, bond, cash, USD, 1-3y, AA+, technology, etc.
    weight: float,
    amount_base: float | None,
    data_quality: str,       # actual, reported, estimated, proxy, unknown
    as_of_date: date | None,
    known_at: datetime | None,
    source: str | None,
)
```

This layer makes it possible to answer personal-asset questions without pretending every product is just a stock-like price series.

### Instrument

An `Instrument` is a financial thing that may be held or traded.

Examples:

- `equity`: AAPL, 600519
- `fund`: open-end fund, ETF, money-market fund
- `bank_wealth_product`: BOC/BOSC/ICBC wealth-management product
- `bond`: government, corporate, convertible
- `cash`: CNY, USD, HKD
- `fx_pair`: USD/CNY
- `crypto_spot`: BTC/USDT
- `derivative`: future, option, swap

Minimum fields:

```python
InstrumentDefinition(
    instrument_id: str,
    symbol: str,
    name: str,
    instrument_type: str,
    quote_currency: str,
    exchange_id: str | None,
    calendar_id: str,
    timezone: str,
    tradable: bool,
    valuation_method: str,
    contract_multiplier: float = 1.0,
    settlement_lag_days: int = 0,
    metadata: dict = {},
)
```

### Informational Series

An informational series is not necessarily tradable, but it can explain or drive decisions.

Examples:

- `index_level`: S&P 500, CSI 300, Hang Seng Index
- `macro_indicator`: CPI, PMI, GDP, unemployment, policy rate
- `yield_curve`: Treasury curve, ChinaBond curve
- `factor_signal`: value, momentum, quality, carry, volatility
- `benchmark_return`: strategy benchmark
- `risk_free_rate`: daily or monthly risk-free curve
- `fee_or_friction`: subscription fee, redemption fee, management fee, spread

Minimum fields:

```python
SeriesDefinition(
    series_id: str,
    subject_id: str | None,
    series_type: str,
    frequency: str,
    unit: str,
    currency: str | None,
    calendar_id: str | None,
    source_priority: list[str],
    revision_policy: str,
    metadata: dict = {},
)
```

### Why This Matters

An index should not be silently optimized as if it were a buyable asset. A macro value should not enter a backtest before its release time. A bank product NAV should not be treated like intraday equity OHLCV. These differences must be encoded before the algorithm layer sees the data.

### Multi-Role Financial Objects

Some market concepts are both reference objects and sources of tradable exposure. The model should not force them into one type.

Example: a stock index.

- The index level itself is an informational `Series`.
- A futures contract on that index is a tradable derivative `Instrument`.
- An ETF tracking that index is another tradable `Instrument`.
- An option on the index or ETF is another derivative `Instrument`.

So the boundary is not "index or futures"; it is "underlying/reference series" versus "tradable implementation."

```python
SeriesDefinition(
    series_id="index:SSE:000001",
    series_type="index_level",
    subject_id=None,
    frequency="D",
    unit="index_point",
    currency=None,
    calendar_id="SSE",
    source_priority=["akshare", "manual"],
    revision_policy="append_only",
)

InstrumentDefinition(
    instrument_id="future:CFFEX:IF2409",
    symbol="IF2409",
    instrument_type="index_future",
    quote_currency="CNY",
    exchange_id="CFFEX",
    calendar_id="CFFEX",
    timezone="Asia/Shanghai",
    tradable=True,
    valuation_method="futures_mark_to_market",
    contract_multiplier=300,
    metadata={
        "underlying_series_id": "index:CSI:000300",
        "expiry": "2024-09-20",
    },
)
```

This gives the algorithm layer three different choices:

1. Use the index level as a benchmark or factor feature.
2. Trade a specific futures contract to express index exposure.
3. Trade an ETF or other proxy if futures are not allowed.

The exposure target and the implementation instrument are separate decisions.

### Exposure Model

To make multi-role objects explicit, add a small exposure layer:

```python
ExposureDefinition(
    exposure_id: str,              # e.g. "exposure:cn_large_cap"
    reference_series_id: str,      # e.g. CSI 300 index level
    tradable_proxy_ids: list[str], # ETF, futures, options, swaps
    default_proxy_id: str | None,
    hedge_ratio_policy: str,
    metadata: dict = {},
)
```

Use cases:

| Exposure | Reference series | Tradable proxies |
|---|---|---|
| China large-cap equity beta | CSI 300 index | CSI 300 ETF, IF futures |
| Shanghai market beta | SSE Composite index | broad-market ETF if available, no direct futures if unavailable |
| US equity beta | S&P 500 index | SPY, ES futures, index options |
| USD/CNY FX exposure | USD/CNY FX series | spot FX, forward, cash balance |

This prevents accidental logic like "because an index has futures, the index itself is tradable." The tradability belongs to the implementation instrument, not the reference series.

### Composite Underlyings

Current implementation status: the existing registry is essentially flat (`symbol`, `asset_type`, `currency`, `attributes`). It does not have a first-class way to say "this fund's underlying is this portfolio" or "this structured product references this basket." That should be added as a relationship layer, not hidden inside provider-specific metadata.

Target model:

```python
PortfolioDefinition(
    portfolio_id: str,
    name: str,
    components: list[PortfolioComponent],
    rebalance_policy: str | None,
    weighting_policy: str,
    currency: str,
    metadata: dict = {},
)

PortfolioComponent(
    target_id: str,          # instrument_id, series_id, exposure_id, or portfolio_id
    target_kind: str,        # "instrument", "series", "exposure", "portfolio"
    weight: float | None,
    quantity: float | None,
    role: str = "holding",   # holding, benchmark_member, hedge_leg, reference_leg
)

UnderlyingLink(
    owner_id: str,           # e.g. fund instrument id
    owner_kind: str,         # instrument, series, portfolio, exposure
    underlying_id: str,      # portfolio_id, series_id, exposure_id, instrument_id
    underlying_kind: str,
    relationship_type: str,  # holds, tracks, references, settles_to, hedges_with
    lookthrough_policy: str, # none, holdings, exposure, risk_only
    valid_from: date | None,
    valid_to: date | None,
    metadata: dict = {},
)
```

Example: a fund whose underlying is a portfolio:

```python
InstrumentDefinition(
    instrument_id="fund:CN:ABC123",
    symbol="ABC123",
    instrument_type="fund",
    quote_currency="CNY",
    exchange_id=None,
    calendar_id="CN_FUND_NAV",
    timezone="Asia/Shanghai",
    tradable=True,
    valuation_method="published_nav",
    metadata={"nav_series_id": "nav:fund:CN:ABC123"},
)

PortfolioDefinition(
    portfolio_id="portfolio:fund:CN:ABC123:reported_holdings",
    name="ABC123 reported holdings",
    components=[
        PortfolioComponent("equity:CN:600519", "instrument", weight=0.08, quantity=None),
        PortfolioComponent("bond:CN:GOV10Y", "instrument", weight=0.15, quantity=None),
        PortfolioComponent("cash:CNY", "instrument", weight=0.05, quantity=None),
    ],
    rebalance_policy="reported_quarterly",
    weighting_policy="reported_weight",
    currency="CNY",
)

UnderlyingLink(
    owner_id="fund:CN:ABC123",
    owner_kind="instrument",
    underlying_id="portfolio:fund:CN:ABC123:reported_holdings",
    underlying_kind="portfolio",
    relationship_type="holds",
    lookthrough_policy="risk_only",
    valid_from=None,
    valid_to=None,
)
```

Why this matters:

- Valuation may use the fund's published NAV.
- Risk attribution may look through to the reported holdings.
- Optimization may choose whether the fund is one investable line item or a look-through basket.
- Backtests can avoid pretending quarterly reported holdings were known daily before disclosure.

So an instrument can be traded as one line item while still having an underlying portfolio for risk, explanation, or exposure decomposition.

### Payoff And Replication

Some instruments are not just "holding an underlying." They transform the underlying through a contract.

Examples:

- index future: linear exposure to an index, with multiplier and expiry
- option: nonlinear payoff on an underlying
- structured note: basket payoff with barriers/coupons
- leveraged ETF: daily leveraged return of an index

Represent this with a payoff contract:

```python
PayoffDefinition(
    payoff_id: str,
    owner_instrument_id: str,
    underlying_refs: list[str],   # series_id, instrument_id, exposure_id, portfolio_id
    payoff_type: str,             # linear, option, barrier_note, leveraged_return
    parameters: dict,
    valuation_model: str,
    Greeks_policy: str | None,
)
```

This keeps "what it references" separate from "how it pays."

### Cashflow Model

Many personal holdings are cashflow products, not simple daily-return assets. Deposits, bank wealth-management products, structured deposits, coupons, maturities, redemptions, and fees need a ledger.

```python
CashflowEvent(
    event_id: str,
    product_id: str,
    account_id: str | None,
    event_type: str,          # purchase, redemption, coupon, interest, dividend, fee, tax, maturity, fx_conversion
    trade_date: date,
    settle_date: date | None,
    amount: float,
    currency: str,
    units: float | None,
    known_at: datetime,
    source: str,
    metadata: dict = {},
)
```

Cashflow-aware metrics:

- money-weighted return / IRR: "How much did I actually earn?"
- time-weighted return / TWR: "How did the product or strategy perform independent of cash timing?"
- realized income
- unrealized gain/loss
- maturity schedule
- expected versus actual repayment

Do not use stock-style daily returns for everything. A fixed-term deposit and a structured deposit need cashflow reconstruction even if a daily NAV does not exist.

---

## Time Semantics

Every canonical observation should be explicit about time:

```python
Observation(
    series_id: str,
    value: float | dict,
    effective_date: date,      # period or trading day the value refers to
    observed_at: datetime | None,
    released_at: datetime | None,
    known_at: datetime,        # earliest time the system may use it
    source: str,
    revision: int = 0,
    quality_flags: list[str] = [],
)
```

Use cases:

| Data | `effective_date` | `released_at` / `known_at` |
|---|---|---|
| US equity close | NYSE trading date | after NYSE close plus provider lag |
| China mutual fund NAV | fund NAV date | next day or provider-specific publication time |
| Crypto daily bar | UTC bar date | after UTC day end |
| CPI | reference month | official release timestamp |
| GDP revision | reference quarter | revision release timestamp |
| Index level | index trading date | after index close/publication |

Rule: backtests and historical features may only use observations with `known_at <= decision_time`.

---

## Canonical Data Contracts

The target data foundation should store several canonical tables, not one overloaded price table.

### `instrument_registry`

Identity and financial metadata for tradable instruments.

Key columns:

- `instrument_id`
- `symbol`
- `instrument_type`
- `quote_currency`
- `calendar_id`
- `timezone`
- `tradable`
- `valuation_method`
- `source_metadata`

### `series_registry`

Identity and metadata for any time series.

Key columns:

- `series_id`
- `series_type`
- `subject_id`
- `frequency`
- `unit`
- `currency`
- `revision_policy`

### `market_observations`

Long-form canonical observations for prices, NAVs, indexes, FX, macro, and signals.

Key columns:

- `series_id`
- `effective_date`
- `known_at`
- `value`
- `field`
- `source`
- `revision`
- `quality_flags`

### Specialized Views

Specialized views are allowed and encouraged, but they should be derived from canonical contracts:

- `PricePanel`: adjusted prices or NAVs for tradable instruments.
- `ReturnPanel`: returns computed under explicit calendar/fill rules.
- `FeaturePanel`: macro/index/factor features aligned to decision times.
- `BenchmarkPanel`: benchmark returns and risk-free series.
- `CostPanel`: fees, spreads, taxes, borrow cost, slippage estimates.

### Risk And Advice Views

For the personal risk engine, add derived views that are not raw market data:

- `ExposurePanel`: product-level and portfolio-level exposure by asset class, region, currency, industry, duration, credit rating, issuer, manager, and payoff type.
- `LiquidityPanel`: market value bucketed by redeemability: T+0, T+1, 7 days, 1 month, 3 months, 1 year, locked/no early redemption.
- `CashflowPanel`: expected and realized cashflows by date, product, account, and currency.
- `ConcentrationPanel`: issuer, manager, bank, product, underlying security, industry, and currency concentration.
- `ScenarioPanel`: stress-test outputs such as equity drawdown, FX shock, rate shock, credit-spread shock, and liquidity freeze.

These views are what the rule engine and advice engine should consume.

---

## Risk Engine Design

The first serious algorithm suite should explain risk, not predict winners.

### Return And Accounting Metrics

Minimum metrics:

- daily/current market value
- cumulative gain/loss
- period return
- annualized return
- maximum drawdown
- volatility and Sharpe/Sortino when the product has meaningful return history
- IRR for investor-specific money-weighted return
- TWR for product/strategy performance
- income versus capital gain
- local-currency return and base-currency return

FX decomposition:

```text
base_currency_return = local_asset_return + fx_return + interaction_term
```

For example, a USD money fund is not just "USD yield"; for a CNY-based user it is also USD/CNY exposure.

### Exposure Dimensions

Track exposures with explicit quality flags:

| Dimension | Examples |
|---|---|
| Asset class | cash, money_market, bond, equity, alternative, derivative, structured_payoff |
| Currency | CNY, USD, HKD, EUR |
| Liquidity | T+0, T+1, 7d, 1m, 3m, 1y, locked |
| Credit | sovereign, bank, policy_bank, credit_bond, LGFV, real_estate, unrated |
| Duration | cash, ultra_short, short, medium, long |
| Equity | market beta, region, sector, style, fund look-through |
| Issuer/manager | bank, fund company, wealth-management subsidiary |
| Payoff | principal_protected, barrier, option_like, leveraged |

If exact data is unavailable, use an estimate with `data_quality="estimated"` or `data_quality="proxy"`, not a fake precise value.

### Look-Through Levels

Look-through should be staged:

| Level | Meaning | Use now? |
|---|---|---|
| Level 0 | Product-label classification only | Yes, immediate baseline. |
| Level 1 | Asset-class weights: stock/bond/cash/other/FX | Highest priority. |
| Level 2 | Reported holdings: top stocks, bonds, industries, ratings | Add after report ingestion. |
| Level 3 | Nested holdings: FOF, fund-of-funds, bank asset-management products | Design now, implement gradually. |

Important time rule: reported holdings are point-in-time facts with disclosure lag. A fund's quarterly holdings should use `as_of_date` for portfolio date and `known_at` for disclosure time. Backtests must not use holdings before `known_at`.

### Liquidity Risk

Minimum outputs:

- emergency-fund coverage months
- percent available within 7 days
- percent available within 30 days
- locked-asset ratio
- maturity ladder
- upcoming open/redemption windows

This should be one of the first useful dashboards because personal portfolios often fail through liquidity mismatch, not only market loss.

### Credit And Duration Risk

Early approximation is acceptable:

- money fund: short duration, low rate risk
- short bond fund: low-to-medium duration risk
- long bond fund: medium-to-high duration risk
- bank WMP R1/R2: cash/fixed-income proxy unless better holdings are known
- structured deposit: principal component plus embedded payoff

Later versions can ingest duration, credit-rating mix, top bonds, LGFV/real-estate exposure, and issuer concentration from fund reports.

### Rule Engine

Rules should be the first advice algorithm family.

```python
RiskRule(
    rule_id: str,
    category: str,       # liquidity, concentration, currency, duration, credit, product_risk, rebalance
    severity: str,
    inputs: list[str],
    condition: str,
    message_template: str,
    recommendation_template: str,
)
```

Useful first rules:

- emergency fund below 6 months of spending
- single bank or issuer concentration above threshold
- single fund company concentration above threshold
- FX exposure above target range
- equity look-through exposure above target range
- 7-day liquidity below target
- upcoming maturity or redemption window
- locked assets above target
- structured product worst-case payoff below expectation

Rules are explainable, testable, and much safer than early ML recommendations.

### Product Screening Engine

Screening is separate from allocation. It ranks or filters products under explicit criteria.

Examples:

- money funds: 7-day annualized yield, per-10k yield, scale, fee, liquidity, historical drawdown/deviation
- bond funds: duration, credit mix, max drawdown, institutional holder ratio, fund-manager tenure, scale, fee, convertible-bond exposure
- bank WMP: risk level, term, benchmark yield, NAV volatility, underlying asset type, redemption constraints, issuer
- structured deposits: principal protection, linked underlying, payoff range, barrier/knock-in/knock-out terms, worst-case return

Do not treat "highest advertised yield" as the ranking objective. Product screening should expose tradeoffs.

### Alert Engine

Alerts are practical and should precede return prediction:

- product NAV continuous drawdown
- fund drawdown above historical percentile
- fund scale shrinking quickly
- credit/duration exposure rising in a report
- product approaching maturity or open period
- FX loss beyond threshold
- liquidity bucket falling below target
- issuer/manager concentration increasing

Alert outputs should include reason, evidence, severity, and suggested action.

---

## Algorithm Layer Contract

Algorithms should receive explicit request objects and panels. They should not know whether data came from AkShare, yfinance, BOC, local Parquet, or a manual file.

The algorithm layer should be generic by composition, not by one huge universal function. Every algorithm declares what inputs it needs, then the data layer builds exactly those inputs.

### Algorithm Plugin Interface

Target contract:

```python
AlgorithmSpec(
    algorithm_id: str,
    algorithm_type: str,      # valuation, optimizer, backtest, risk, signal, allocation
    required_inputs: list[str],
    optional_inputs: list[str],
    supported_universe: dict,
    output_schema: str,
    assumptions: dict,
)

AlgorithmContext(
    instruments: InstrumentRegistryView,
    series: SeriesRegistryView,
    relationships: RelationshipGraph,
    panels: dict[str, Panel],
    calendars: CalendarRegistry,
    costs: CostModel | None,
    constraints: ConstraintSet | None,
    decision_time: datetime,
    metadata: dict = {},
)

class Algorithm:
    spec: AlgorithmSpec

    def validate_inputs(self, context: AlgorithmContext) -> ValidationReport:
        ...

    def run(self, request: object, context: AlgorithmContext) -> object:
        ...
```

Examples:

| Algorithm | Required inputs | Optional inputs |
|---|---|---|
| Accounting metrics | cashflow panel, price panel, position snapshots | FX panel, fee panel |
| Risk rule engine | exposure panel, liquidity panel, concentration panel | user targets, spending assumptions |
| Product screening | product definitions, risk/return metrics, fee data | peer group statistics |
| Alert engine | risk panels, cashflow panel, product events | news/sentiment feed later |
| Mean-variance optimizer | return panel, covariance model, constraints | cost model, benchmark |
| Black-Litterman | return panel, covariance model, views, priors | market caps, confidence model |
| Macro-conditioned allocation | return panel, feature panel, regime model | benchmark, risk-free series |
| Fund look-through risk | fund NAV panel, underlying portfolio graph | reported holdings, factor exposures |
| Derivative valuation | underlying panel, payoff definition, calendar | Greeks model, volatility surface |
| Backtest | strategy, price panel, decision calendar | feature panel, cost model, execution model |

This design is "universal" because algorithms depend on typed capabilities, not on asset-type branches.

### Data Bundle Builder

Before running an algorithm, build a `DataBundle` from the algorithm spec:

```python
DataBundleRequest(
    universe_ids: list[str],
    requested_inputs: list[str],
    start: date,
    end: date,
    decision_time_policy: str,
    lookthrough_policy: str,
    missing_data_policy: str,
)

DataBundle(
    price_panel: PricePanel | None,
    return_panel: ReturnPanel | None,
    feature_panel: FeaturePanel | None,
    benchmark_panel: BenchmarkPanel | None,
    cost_panel: CostPanel | None,
    relationship_graph: RelationshipGraph,
    validation_report: ValidationReport,
)
```

The bundle builder handles:

- point-in-time filtering by `known_at`
- instrument/series/exposure/portfolio relationship expansion
- look-through policy
- proxy selection
- missing-data policy
- currency conversion
- calendar alignment

The algorithm only sees the final bundle and the validation report.

### Relationship Graph

Use a graph as the central joiner between financial concepts:

```python
RelationshipGraph(
    nodes={
        instrument_id: InstrumentDefinition,
        series_id: SeriesDefinition,
        portfolio_id: PortfolioDefinition,
        exposure_id: ExposureDefinition,
        payoff_id: PayoffDefinition,
    },
    edges=[
        UnderlyingLink(...),
        SourceAlias(...),
        ProxyLink(...),
        BenchmarkLink(...),
    ],
)
```

Important edge types:

| Edge | Meaning |
|---|---|
| `holds` | portfolio or fund holds instruments/portfolios |
| `tracks` | ETF/fund tracks an index or exposure |
| `references` | derivative/structured note references an underlying |
| `settles_to` | contract settles to series or instrument |
| `proxy_for` | instrument can implement an exposure |
| `benchmark_for` | series is a benchmark for portfolio/strategy |
| `priced_by` | instrument has NAV/price series |
| `alias_of` | provider code maps to canonical id |

This graph is what makes the system expandable without multiplying special cases.

### Valuation

Input:

```python
ValuationRequest(
    portfolio_snapshot,
    as_of_date,
    decision_time,
    base_currency,
    price_policy,
    fx_policy,
    corporate_action_policy,
)
```

Consumes:

- holdings and cash
- price panel for held instruments
- FX panel
- corporate action ledger
- fee/friction rules
- calendar registry

Output must include:

- total value
- per-position value
- per-position `price_date`, `known_at`, `source`, `stale_days`
- FX rate, FX date, FX source
- corporate action adjustments
- warnings and quality flags

### Optimization

Input:

```python
OptimizationRequest(
    universe,
    objective,
    return_model,
    risk_model,
    constraints,
    cost_model,
    feature_set,
    estimation_window,
)
```

Consumes:

- `ReturnPanel` for investable instruments
- optional `FeaturePanel` for macro/factor-conditioned models
- benchmark/risk-free panel
- constraints and costs

Output must include:

- weights
- expected return/risk
- model assumptions
- input data window
- excluded instruments and reasons
- constraint binding diagnostics

Optimization should not be the first advice layer. It should run after:

1. holdings and cashflows are correct,
2. exposure panels are available,
3. liquidity and concentration constraints are explicit,
4. user goals and drawdown tolerance are encoded,
5. costs, lockups, and redemption constraints are available.

The first allocation algorithm should be target exposure plus rebalance bands, not Sharpe maximization:

```text
target: cash 30%, fixed_income 40%, equity 10%, FX 10%, other 10%
actual: cash 45%, fixed_income 35%, equity 5%, FX 12%, other 3%
advice: cash overweight, equity underweight, but check liquidity and lockups before trades
```

Mean-variance, risk parity, and Black-Litterman can come later, using look-through exposures and constraints rather than product labels.

### Backtest

Input:

```python
BacktestRequest(
    strategy,
    universe,
    start,
    end,
    rebalance_calendar,
    decision_time_policy,
    execution_policy,
    cost_model,
)
```

Consumes:

- point-in-time `FeaturePanel`
- price/return panel
- benchmark panel
- cost model
- calendar and execution rules

Hard rule: signal generation time, decision time, execution time, and valuation time must be separate fields.

---

## Module Boundary Design

Target package layout:

```text
src/
  domain/
    instruments.py        # InstrumentDefinition, InstrumentType
    series.py             # SeriesDefinition, SeriesType
    relationships.py      # UnderlyingLink, ExposureDefinition, PayoffDefinition
    portfolio.py          # PortfolioSnapshot, Position, CashBalance
    observations.py       # Observation, quality flags
    requests.py           # ValuationRequest, OptimizationRequest, BacktestRequest
    results.py            # ValuationResult, AllocationResult, BacktestResult

  market/
    calendars.py          # ExchangeCalendar, release calendars, known_at policies
    conventions.py        # settlement, day count, trading session conventions

  data_foundation/
    schemas.py            # canonical schema validation
    registry.py           # instrument and series registry repository
    relationships.py      # relationship graph repository
    observations.py       # observation repository
    panels.py             # PricePanel/FeaturePanel/DataBundle construction
    quality.py            # completeness, stale data, outlier checks

  ingestion/
    adapters/             # provider adapters; wraps existing fetchers
    normalizers/          # provider output -> observations
    pipelines.py          # ingestion orchestration

  analytics/
    valuation.py          # canonical valuation engine
    returns.py            # return construction policies
    features.py           # macro/index/factor alignment
    risk_models.py        # covariance/factor risk model builders
    cost_models.py        # fees, slippage, taxes

  algorithms/
    base.py               # AlgorithmSpec, AlgorithmContext, Algorithm interface
    optimization.py       # allocation algorithms
    backtest.py           # strategy simulation
    risk.py               # portfolio risk reports

  services/
    portfolio_service.py  # app-facing orchestration
    research_service.py
    data_service.py

  api/
    fastapi_app.py
```

Current modules can migrate gradually. Do not rename everything at once.

---

## Naming Standard

### Prefer Financial Semantics

Use:

- `instrument_id` instead of ambiguous `asset_id` when the object is tradable or potentially tradable.
- `series_id` for macro/index/factor/FX data series.
- `portfolio_id` for a reusable basket or holdings definition, including fund look-through holdings.
- `exposure_id` for an economic exposure that can be implemented by multiple instruments.
- `underlying_id` only inside a typed relationship edge that also says `underlying_kind`.
- `relationship_type` for graph edges such as `holds`, `tracks`, `references`, `proxy_for`, `priced_by`.
- `effective_date` for the date the value refers to.
- `known_at` for the earliest usable timestamp.
- `decision_time` for when a strategy decides.
- `execution_time` for when trades execute.
- `valuation_time` for when NAV is computed.
- `quote_currency` for the currency of an instrument price.
- `base_currency` for portfolio reporting currency.

Avoid:

- `symbol` as a universal primary key.
- `date` without semantics.
- `data`, `info`, `result` as public contract names unless wrapped in typed result objects.
- `fetch()` returning silently empty data on failures.
- `v2` as a permanent name. It is fine temporarily, but promote to a semantic name before the next stable API.

### Suggested Renames

| Current | Target | Reason |
|---|---|---|
| `PortfolioServiceV2` | `PortfolioValuationService` or make it canonical `PortfolioService` | `V2` says sequence, not responsibility. |
| `ValuationEngine.value()` | `value_snapshot()` | Clarifies that it values a snapshot, not arbitrary data. |
| `price_date` on result | `valuation_price_summary` + per-position `price_date` | One date hides mixed-market staleness. |
| `asset_id` in market data | `instrument_id` for tradables; `series_id` for generic data | Macro/index data should not pretend to be assets. |
| `attributes` for everything | typed relationship objects plus metadata | Relationships such as underlying, proxy, holdings, and benchmark should be queryable and testable. |
| `fetchers/` | `ingestion/adapters/` eventually | Provider adapter, not domain object. |
| `data_core/` | merge into `ingestion/` and `data_foundation/` | Current name overlaps with `data_foundation`. |
| `processor/` | `data_foundation/quality.py`, `analytics/returns.py`, `market/calendars.py` | Current folder mixes unrelated transformations. |
| `breakdiown` | `breakdown` | Typo in central valuation code. |

---

## Migration Strategy

### Phase 0: Product Direction And Existing Data Cleanup

Declare the supported product goal:

- personal asset inventory
- valuation and performance accounting
- cashflow and maturity tracking
- risk exposure decomposition
- rules-based advice and alerts
- allocation optimization only after risk foundations are stable

Current registry issues to fix later:

- `asset_registry.yaml` is flat and cannot represent relationships.
- nested `attributes.attributes...` should be treated as legacy data hygiene debt.
- product identity, instrument identity, and data-source aliases should be split.

Definition of done:

- docs and AI task prompts use "risk engine / advice engine" language before "prediction algorithm."
- no new feature encodes complex relationships inside free-form `attributes`.

### Phase 1: Contracts Before Refactor

Add domain contracts without changing public behavior:

- `ProductDefinition`
- `PositionSnapshot`
- `ExposureSnapshot`
- `CashflowEvent`
- `InstrumentDefinition`
- `SeriesDefinition`
- `PortfolioDefinition`
- `UnderlyingLink`
- `ExposureDefinition`
- `PayoffDefinition`
- `Observation`
- `PriceObservation`
- `MacroObservation`
- `PanelRequest`
- `PanelBuildResult`

Definition of done:

- Existing tests still pass.
- No old module is deleted.
- New tests validate time semantics and identifiers.

### Phase 2: Registry Split

Split current asset registry concepts:

- tradable instruments
- informational series
- reusable portfolios/baskets
- relationship graph edges
- source-specific aliases
- provider capability metadata

Definition of done:

- Instrument lookup does not depend on provider naming.
- Index and macro series can be registered without pretending to be holdings.
- A fund can point to an underlying portfolio without changing valuation behavior.

### Phase 3: Panel Builders

Build algorithm inputs from canonical observations:

- `build_cashflow_panel()`
- `build_exposure_panel()`
- `build_liquidity_panel()`
- `build_concentration_panel()`
- `build_price_panel()`
- `build_return_panel()`
- `build_feature_panel()`
- `build_benchmark_panel()`

Definition of done:

- Algorithms consume panels only.
- Known-at filtering is tested.
- Macro/index data can be included as features without entering the tradable universe.
- Risk/advice algorithms can run without market prediction.

### Phase 4: Valuation, Performance, And Cashflow Hardening

Promote date-aware valuation to the canonical path:

- per-position price metadata
- FX source metadata
- corporate actions applied by date
- stale price warnings
- calendar/cutoff rules
- IRR/TWR calculation from cashflows
- local-currency versus base-currency return decomposition
- maturity and redemption schedules

Definition of done:

- Mixed US/CN/crypto valuation tests cover morning, afternoon, and historical decision times.
- Deposit, bank WMP, fund, and FX position examples have correct cashflow/performance behavior.

### Phase 5: Risk And Advice Engines

Implement explainable risk/advice modules before advanced optimization:

- liquidity bucket report
- concentration report
- FX exposure report
- credit/duration proxy report
- look-through exposure report
- rule engine
- alert engine
- product screening engine

Definition of done:

- Each recommendation separates fact, estimate, and advice.
- Every risk number carries `data_quality`, `as_of_date`, and `known_at` where relevant.
- Rules are unit-tested with simple offline fixtures.

### Phase 6: Algorithm Isolation

Move algorithms behind stable request/result contracts:

- algorithm spec and capability declaration
- data bundle builder
- relationship graph expansion
- optimization
- risk model building
- backtest
- feature generation
- transaction cost model

Definition of done:

- Adding a macro feature or benchmark requires no optimizer changes.
- Adding an instrument type requires no optimizer changes if returns/prices can be produced.
- Adding an algorithm requires declaring inputs and writing an adapter, not changing registries or fetchers.

### Phase 7: Advanced Allocation And Prediction

Only after the risk/advice foundation:

- target exposure plus rebalance bands
- risk-budget allocation
- mean-variance / risk parity / Black-Litterman
- macro-conditioned allocation
- prediction as auxiliary signal, not primary truth

Definition of done:

- optimizer respects liquidity, lockup, redemption fee, currency, and risk-budget constraints.
- predicted returns are optional inputs with provenance and confidence metadata.

---

## AI-Friendly Task Slicing

Each AI task should be small, contract-first, and testable without network access.

Good task template:

```text
Goal:
Add <one contract/adapter/panel/rule>.

Allowed files:
<small file list>.

Do not touch:
app.py, unrelated fetchers, real local data.

Acceptance:
- unit tests for the new contract/rule
- existing tests pass with:
  python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider
- docs updated if public behavior changed
```

### Recommended Atomic Tasks

#### Domain Contracts

1. Add `src/domain/products.py` with `ProductDefinition`, `ProductType`, and issuer/manager fields.
2. Add `src/domain/positions.py` with `PositionSnapshot`, lockup fields, and account/product ids.
3. Add `src/domain/exposures.py` with `ExposureSnapshot`, exposure dimensions, `data_quality`, `as_of_date`, and `known_at`.
4. Add `src/domain/cashflows.py` with `CashflowEvent` and event types.
5. Add `src/domain/instruments.py` with `InstrumentDefinition` and `InstrumentType`.
6. Add `src/domain/series.py` with `SeriesDefinition` and `SeriesType`.
7. Add `src/domain/observations.py` with `Observation`, `effective_date`, `known_at`, `revision`, and quality flags.
8. Add `src/domain/relationships.py` with `UnderlyingLink`, `ExposureDefinition`, and `PayoffDefinition`.
9. Add `PortfolioDefinition` and `PortfolioComponent` for reusable baskets and fund look-through holdings.
10. Add tests that prove index/macro series are not tradable by default.
11. Add tests that prove a fund can be valued by NAV while separately pointing to an underlying portfolio for look-through risk.
12. Add tests that separate fact, estimate, and advice records.

#### Time Semantics

13. Add calendar registry with NYSE, SSE, SEHK, UTC/crypto, and bank NAV calendars.
14. Add `known_at` policy tests for US close, China close, crypto daily bar, and macro release.
15. Add panel filtering test: values with `known_at > decision_time` are excluded.
16. Add reported-holdings disclosure-lag test: quarter-end holdings are unusable before disclosure `known_at`.

#### Data Foundation

17. Add source alias mapping: provider symbol -> product/instrument/series id.
18. Add observation repository in a new file without modifying existing price repository.
19. Add relationship graph repository in a new file without modifying the old asset registry.
20. Add `build_price_panel()` from observations for tradable instruments only.
21. Add `build_feature_panel()` from macro/index/factor series.
22. Add `build_cashflow_panel()` from cashflow events.
23. Add `build_exposure_panel()` from direct and look-through exposure snapshots.
24. Add `build_liquidity_panel()` from positions and product liquidity metadata.
25. Add `build_data_bundle()` that expands relationships according to a look-through policy.

#### Valuation And Performance

26. Extend `PositionValue` with `price_date`, `known_at`, `price_source`, and `stale_days`.
27. Add `FxRateObservation` or FX panel source metadata.
28. Fix corporate-action history by applying actions per date.
29. Add mixed-calendar valuation tests.
30. Add IRR calculation from `CashflowEvent` fixtures.
31. Add TWR calculation for product/strategy performance.
32. Add base-currency return decomposition into local return and FX return.

#### Risk, Rules, Screening, Alerts

33. Add liquidity bucket report with T+0/T+1/7d/1m/3m/1y/locked buckets.
34. Add concentration report by product, issuer, manager, bank, currency, and asset class.
35. Add Level 0 exposure mapping by product label.
36. Add Level 1 exposure mapping by stock/bond/cash/other weights.
37. Add `RiskRuleEngine` with liquidity, concentration, currency, and exposure rules.
38. Add `ProductScreeningEngine` interface with one money-fund example scorer.
39. Add `AlertEngine` interface with maturity/open-window and drawdown examples.

#### API And Services

40. Rename or wrap `PortfolioServiceV2` behind a semantic service name.
41. Add POST to CORS methods and test CORS preflight.
42. Map domain errors to stable HTTP statuses.
43. Add endpoint docs for valuation metadata.
44. Add API response shapes for risk report, rule advice, product screening, and alerts.

#### Algorithm Plugins

45. Add `src/algorithms/base.py` with `AlgorithmSpec`, `AlgorithmContext`, and an `Algorithm` protocol.
46. Wrap the existing mean-variance optimizer behind the new algorithm interface.
47. Add target-exposure rebalance algorithm before advanced optimization.
48. Add a dummy macro-feature algorithm test that consumes `FeaturePanel` without touching optimizer internals.
49. Add a derivative/payoff algorithm stub that validates required `PayoffDefinition` input but does not implement pricing yet.

#### Refactor Hygiene

50. Add legacy markers to old modules.
51. Replace `print()` with logger in one fetcher at a time.
52. Rename typo-level variables only when covered by tests.
53. Archive stale docs one file at a time.

---

## Non-Goals For Now

- Do not rewrite all fetchers at once.
- Do not delete `app.py` until FastAPI + frontend covers the workflow.
- Do not force macro/index data into the same schema as prices.
- Do not add a complex database before the observation contracts are stable.
- Do not make Qlib, vectorbt, or PyPortfolioOpt central domain dependencies. They are algorithm adapters, not domain models.

---

## North Star

The ideal OptiFolio core should answer:

1. What financial object is this?
2. Is it tradable, informational, or both?
3. What does this value mean?
4. When did it become knowable?
5. Which algorithm input view should it enter?
6. Which assumptions and sources produced the final result?

If those six questions are explicit in code, new asset types, macro data, indexes, and new algorithms become extensions rather than rewrites.
