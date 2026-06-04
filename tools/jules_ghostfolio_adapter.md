## Task: Create Ghostfolio-compatible API adapter for OptiFolio

### Goal

Create a new FastAPI route group `src/api/ghostfolio_compat.py` that exposes Ghostfolio-compatible API endpoints. This allows deploying Ghostfolio's open-source frontend (Angular) pointed at OptiFolio's backend, replacing Ghostfolio's own NestJS/Prisma backend.

### Ghostfolio API Endpoints to Implement

All routes under prefix `/api/v1/`. These are what Ghostfolio's frontend calls:

#### 1. `GET /api/v1/portfolio/details`
The main dashboard endpoint. Response shape:
```json
{
  "accounts": [],
  "holdings": {
    "AAPL": {
      "symbol": "AAPL", "name": "Apple Inc.", "quantity": 100,
      "marketPrice": 315.20, "currency": "USD",
      "allocationInPercentage": 0.15, "performance": 0.05,
      "assetClass": "EQUITY", "assetSubClass": "STOCK"
    }
  },
  "summary": {
    "currentNetWorth": 673444.00, "totalInvestment": 500000.00,
    "grossPerformance": 173444.00, "grossPerformancePercentage": 0.347
  },
  "platforms": [],
  "hasError": false
}
```
Map from: our `GET /api/portfolio/v2/value` + `GET /api/portfolio/v2/holdings`

#### 2. `GET /api/v1/portfolio/performance`
Performance chart data. Response shape:
```json
{
  "chart": [
    {"date": "2026-01-01", "netWorth": 600000.00, "netPerformanceInPercentage": 0.0, "totalInvestment": 500000.00, "value": 100000.00}
  ],
  "performance": {
    "currentNetWorth": 673444.00, "totalInvestment": 500000.00,
    "grossPerformance": 173444.00, "grossPerformancePercentage": 0.347,
    "currentValueInBaseCurrency": 673444.00
  }
}
```
Map from: our `GET /api/portfolio/v2/history` + `GET /api/portfolio/v2/value`

#### 3. `GET /api/v1/portfolio/holdings`
Built from our `GET /api/portfolio/v2/value` positions. Return array of holding objects.
Support query params: `symbol`, `query` (search)

#### 4. `GET /api/v1/portfolio/dividends`
Built from our `GET /api/portfolio/v2/corporate-actions` — filter for dividend type.
Return array of `{date, symbol, investment, quantity, currency}`

#### 5. `GET /api/v1/portfolio/investments`
Aggregate investment timeline from saved portfolio history.
Map from: our `GET /api/portfolio/v2/history-entries`
Return `{investments: [{date, investment}], streaks: {currentStreak, longestStreak}}`

#### 6. `GET /api/v1/portfolio/report`
Simple stub: return `{xRay: {categories: [], statistics: {totalCount: 0}}}` for now.

### Architecture

```python
# src/api/ghostfolio_compat.py
from fastapi import APIRouter
router = APIRouter(prefix="/api/v1")

@router.get("/portfolio/details")
def ghostfolio_portfolio_details():
    # Call existing PortfolioServiceV2 endpoints
    value = get_application_services().portfolio_v2.get_value()
    holdings = get_application_services().portfolio_v2.get_current_holdings()
    # Transform to Ghostfolio format
    ...
```

Wire into `src/api/fastapi_app.py`:
```python
from .ghostfolio_compat import router as ghostfolio_router
app.include_router(ghostfolio_router)
```

### Rules

- Reuse existing PortfolioServiceV2 — do NOT duplicate business logic
- Handle edge cases: empty portfolio, missing prices, single-asset portfolios
- All amounts in CNY (base currency)
- Asset class mapping: us_equity→EQUITY, cn_stock→EQUITY, cn_fund→FUND, bank_wmp→OTHER, cash→CASH
- Follow existing code patterns (frozen dataclasses, to_dict(), service responses)
- Write tests: `tests/test_ghostfolio_compat.py`
- Test command: `C:\Users\Z\miniconda3\envs\optifolio313\python.exe -m pytest tests/ -q --tb=line`
