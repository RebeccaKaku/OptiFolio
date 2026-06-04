# FinData Adapters — Provider Implementation Guide

## Contract

Every adapter implements `FetcherProtocol`:

```python
class FetcherProtocol:
    def fetch(self, symbol: str, start_date: str, end_date: str, **kwargs) -> FetchResult:
        """Fetch data. Return FetchResult — never validate, never store, never retry."""
```

`FetchResult` carries:
- `symbol`, `provider` — identity
- `data` — raw pd.DataFrame (or None on failure)
- `success`, `latency_ms`, `errors` — telemetry
- `metadata` — extra context (row count, date range, etc.)

## Rules

1. **No validation.** Do not call `.empty`, do not check columns. That's QualityGate's job.
2. **No storage.** Do not write files. That's CanonicalStore's job.
3. **No retry.** Do not implement retry logic. That's the orchestrator's job.
4. **Return FetchResult always.** Even on failure — return `FetchResult(success=False, errors=[...])`.
5. **Lazy import heavy dependencies.** akshare, yfinance, etc. — import inside `fetch()`, not at module level.

## Adding a New Adapter

```python
# FinData/adapters/new_provider.py
from . import FetcherProtocol, FetchResult
import time

class NewProviderFetcher(FetcherProtocol):
    PROVIDER = "new-provider-name"

    def fetch(self, symbol, start_date, end_date, **kwargs):
        t0 = time.time()
        try:
            import provider_lib
            df = provider_lib.get_data(symbol, start_date, end_date)
            return FetchResult(
                symbol=symbol, provider=self.PROVIDER, data=df,
                success=True, latency_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            return FetchResult(
                symbol=symbol, provider=self.PROVIDER, data=None,
                success=False, latency_ms=(time.time() - t0) * 1000,
                errors=[str(e)],
            )
```

Then register in `FinData/adapters/__init__.py`:

```python
FETCHER_REGISTRY["new_asset_type"] = NewProviderFetcher()
```

## Current Adapters

| File | Asset Type | Data Source | Method |
|------|-----------|-------------|--------|
| `us_equity.py` | US stocks, ETFs | akshare Sina | `stock_us_daily(adjust="qfq")` |
| `cn_stock.py` | CN A-shares | EastMoney → Sina → Tencent | Multi-source fallback cascade |
| `cn_fund.py` | CN funds (ETF, open, money) | akshare | Smart routing by fund type |
| `forex.py` | FX rates | PBOC via akshare Sina | `currency_boc_sina()` |
| `bank_wmp.py` | Bank WMP (BOC/BOSC/ICBC) | BOC JSON / BOSC GET / ICBC POST | Symbol pattern dispatch |
| `boc_wm.py` | BOC wealth management | bocwm.cn JSON API | Single-request full history |
| `boc_structured.py` | BOC structural deposits | boc.cn HTML scrape | Personal + institutional |
| `bosc.py` | BOSC wealth management | bosc.cn GET API + snapshot | Paginated full history |
| `icbc.py` | ICBC wealth management | icbc.com.cn JSON API | Paginated with SSL context |
