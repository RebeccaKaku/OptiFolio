# OptiFolio — Personal Asset Risk & Allocation Engine

OptiFolio is a multi-asset portfolio management system with a self-contained data
department (FinData), date-aware valuation, risk analytics, and a FastAPI service layer.

**Direction**: risk engine first, allocation advice second. Do not treat every asset
as a stock-like price series, and do not predict returns before understanding exposures.

## Quick Start

```bash
# Environment
conda activate optifolio313  # Python 3.13.13

# Install
pip install -r requirements.txt

# Start server
python tools/start_app.py      # FastAPI on port 8011

# Ingest portfolio prices
python tools/ingest_portfolio_prices.py

# Daily pipeline
python tools/scheduler.py
```

## Architecture

```text
FinData/               # Self-contained data department (4 sub-modules)
  adapters/            # Provider adapters — one file per asset class
  store/               # Storage engine — Parquet + DuckDB + QualityGate
  orchestration/       # Scheduling, ingestion, rate limiting, fallback chains
  serving/             # Public data API — prices, returns, metrics, rates, export

src/
  analytics/           # Liquidity, concentration, FX exposure, risk rules, screening, alerts
  api/                 # FastAPI routes — V1 (legacy) + V2 (date-aware) + Ghostfolio compat
  core/                # ValuationEngine, FxRateProvider, calendars, corporate actions, fees
  data_foundation/     # Canonical market data schema + MarketDataRepository
  domain/              # Domain contracts — instruments, series, products, positions, cashflows
  research/            # BacktestEngine (vectorbt + pandas fallback)
  services/            # PortfolioServiceV2, research service, fund friction, dividend detection

tools/                 # CLI tools
config/                # YAML configuration (templates only — secrets in local/)
tests/                 # 592 tests, 30 skipped
```

## Key Design Principles

1. **FinData is self-contained.** All data flows through `from FinData import fd`. No direct fetcher imports outside FinData.
2. **Data quality is enforced.** QualityGate runs 8 checks on every write. Empty data NEVER overwrites good data.
3. **Valuation is date-aware.** `value_on(T)` uses close prices with date ≤ T, per-asset staleness tracking.
4. **Products ≠ instruments.** Funds, bank WMPs, and structured deposits have NAV semantics, not OHLCV semantics.
5. **Algorithms consume panels, not raw fetcher DataFrames.**

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /api/portfolio/v2/value?as_of=YYYY-MM-DD` | Date-aware portfolio NAV |
| `GET /api/portfolio/v2/history?start=&end=` | Daily valuation history |
| `GET /api/portfolio/v2/risk/liquidity` | T+0 / T+1 / 7d / 1m / 3m / 1y / locked breakdown |
| `GET /api/portfolio/v2/risk/concentration` | Currency / issuer / asset class concentration |
| `GET /api/portfolio/v2/risk/fx-exposure` | Currency exposure + sensitivity |
| `POST /api/portfolio/v2/risk/rules` | Rule engine with configurable thresholds |
| `POST /api/portfolio/v2/corporate-actions/*` | Record dividends, splits, mergers |
| `GET /api/market/prices?assets=AAPL,QQQ` | Price matrix from canonical store |
| `GET /api/market/assets` | All asset IDs in canonical storage |
| `GET /api/data/quality?asset_id=AAPL` | Data quality reports |
| `GET /api/v1/portfolio/details` | Ghostfolio-compatible adapter |
| `GET /api/v1/portfolio/holdings` | Ghostfolio holdings |
| `GET /api/alerts` | Risk alerts (wiring in progress) |

## Documentation

| Document | Audience |
|----------|----------|
| `docs/CURRENT_STATE_2026-06-05.md` | Onboarding — what works, what's broken, what's next |
| `CLAUDE.md` | AI assistant project instructions |
| `docs/FINANCIAL_LOGIC_AND_MODULE_DESIGN.md` | Architects — target architecture, naming, migration |
| `docs/TIME_ALIGNMENT_DESIGN.md` | Cross-market time alignment problem and solution |
| `FinData/README.md` | FinData internal architecture and conventions |
| `FinData/adapters/README.md` | How to add a new data source |
| `FinData/store/README.md` | Storage layer — schemas, QualityGate, repository API |
| `FinData/orchestration/README.md` | Scheduling, cadence, rate limiting |
| `FinData/serving/README.md` | Public data API — usage examples |

## Development

```bash
# Tests
C:\Users\Z\miniconda3\envs\optifolio313\python.exe -m pytest tests/ -q --tb=line

# Privacy scan
python tools/privacy_scan.py --strict --with-detect-secrets

# Lint / type check
# (not configured yet — feel free to add)
```

## Private Data

Real portfolio data, secrets, and local state live in `local/` and are git-ignored.
Templates in `config/*.example.yaml` are safe to commit.
