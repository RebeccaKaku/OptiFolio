# OptiFolio — Personal Asset Risk & Allocation Engine

Multi-asset portfolio management with a self-contained data department (`findata`),
date-aware valuation, risk analytics, and a FastAPI service layer.

**Direction**: risk engine first, allocation advice second.

## Quick Start

```bash
conda activate optifolio313       # Python >=3.10
pip install -r requirements.txt
python tools/start_app.py          # FastAPI on port 8011
python tools/scheduler.py          # daily pipeline
```

## Architecture

```
packages/
  optifolio_contracts/   pure types (stdlib only) — identifiers, quality, sources
  findata/               data department — adapters → store → serving + orchestration

src/
  domain/       dataclasses — products, positions, exposures, cashflows
  core/         valuation, calendars, portfolio_book_db, fees, corporate actions
  analytics/    alerts, exposure, concentration, liquidity, screening, attribution
  services/     business orchestration (no quant math)
  api/          FastAPI routes (no business logic)
  research/     backtest engine, model registry
```

**Dependency direction**: `contracts ← findata ← src`. Never reverse.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /api/portfolio/v2/value?as_of=YYYY-MM-DD` | Date-aware portfolio NAV |
| `GET /api/portfolio/v2/history?start=&end=` | Daily valuation history |
| `GET /api/portfolio/v2/risk/liquidity` | Liquidity breakdown |
| `GET /api/portfolio/v2/risk/concentration` | Concentration analysis |
| `GET /api/portfolio/v2/risk/fx-exposure` | Currency exposure |
| `GET /api/market/prices?assets=AAPL,QQQ` | Price matrix |
| `GET /api/alerts` | Risk alerts |

## Documentation

| Document | Purpose |
|----------|---------|
| `CLAUDE.md` | AI assistant instructions — rules, architecture, migration traps |
| `docs/CURRENT_STATE.md` | Live project map — test counts, bugs, next steps |
| `docs/TODO.md` | Prioritized task queue |
| `docs/AI_CONTEXT.md` | Full architecture reference |
| `docs/PRODUCT_VISION_AND_EXECUTION_PLAN.md` | Product north star |
| `docs/JULES.md` | How to dispatch work to Jules |
| `docs/GLOSSARY.md` | Financial semantics dictionary |

## Development

```bash
# Full test suite
python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider

# Privacy scan
python tools/privacy_scan.py --strict --with-detect-secrets
```

## Private Data

Real portfolio data, secrets, and local state live in `local/` and are git-ignored.
Templates in `config/*.example.yaml` are safe to commit.
