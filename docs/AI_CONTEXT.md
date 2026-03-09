# NeoFM AI Context Document

> This document is intended for AI assistants to understand the codebase structure, design patterns, and implementation details.

## Project Overview

NeoFM is a financial data processing and portfolio optimization framework. It provides:
- Multi-source data fetching (crypto, stocks, funds)
- Data cleaning and alignment pipeline
- Portfolio optimization with Black-Litterman model

## Architecture Summary

```
NeoFM/
├── fetchers/          # Data source adapters
├── downloader/        # Raw data download with caching
├── processor/         # Data cleaning and alignment
├── portfolio/         # Portfolio optimization
├── api_checker/       # API connectivity testing
└── docs/              # Documentation
```

## Module Details

### 1. Fetchers Module (`fetchers/`)

**Purpose**: Abstract data fetching from multiple sources into a unified interface.

**Key Interface**: [`AsyncBaseFetcher`](fetchers/interfaces.py:9)
```python
class AsyncBaseFetcher(ABC):
    @abstractmethod
    async def fetch(
        self, 
        symbol: str, 
        start_date: str, 
        end_date: str, 
        timeframe: str = '1d',
        exchange: Optional[str] = None,
        **kwargs
    ) -> pd.DataFrame:
        pass
```

**Implementations**:
| Class | Source | Data Types |
|-------|--------|------------|
| `CryptoFetcher` | CCXT | Cryptocurrency OHLCV |
| `YahooFinanceFetcher` | yfinance | Stocks, ETFs, Forex |
| `CnFundFetcher` | akshare | Chinese funds (ETF, open-end, money market) |

**Output Format**: All fetchers return DataFrame with:
- Index: DatetimeIndex named 'timestamp'
- Columns: `open`, `high`, `low`, `close`, `volume` (lowercase)

### 2. Downloader Module (`downloader/`)

**Purpose**: Orchestrate data downloads with caching and batch support.

**Key Classes**:

[`DownloadTask`](downloader/models.py:12) - Request model:
```python
@dataclass
class DownloadTask:
    symbol: str
    source: str  # 'crypto', 'yahoo', 'cn_fund'
    start_date: str
    end_date: str
    timeframe: str = '1d'
    exchange: Optional[str] = None
```

[`DownloadResult`](downloader/models.py:42) - Response model:
```python
@dataclass
class DownloadResult:
    task: DownloadTask
    data: Optional[pd.DataFrame]
    success: bool
    error_message: Optional[str]
    latency_ms: float
    is_cached: bool = False
```

[`DataCache`](downloader/cache.py:15) - File-based caching:
- Cache key: `{source}_{symbol}_{start}_{end}_{timeframe}.parquet`
- TTL support via `.meta` companion files
- Parquet format for efficiency

[`DownloadManager`](downloader/manager.py:18) - Main orchestrator:
```python
class DownloadManager:
    def register_fetcher(self, name: str, fetcher: AsyncBaseFetcher)
    async def download(self, task: DownloadTask) -> DownloadResult
    async def download_batch(self, tasks: List[DownloadTask], max_concurrent: int = 5) -> List[DownloadResult]
```

**Concurrency Pattern**: Uses `asyncio.Semaphore` for rate limiting.

### 3. Processor Module (`processor/`)

**Purpose**: Clean, align, and standardize financial data.

**Design Pattern**: Chain of Responsibility via [`ProcessingPipeline`](processor/base.py:35)

**Processing Steps**:

[`DataCleaner`](processor/cleaner.py:15):
- `handle_missing_values()` - ffill, bfill, drop, interpolate, mean
- `remove_outliers()` - IQR method, z-score method
- `fill_gaps()` - Forward fill up to max_gap_days
- `validate_ohlcv()` - High >= Low, prices within range

[`DataAligner`](processor/aligner.py:15):
- `align_timezone()` - Convert to target timezone
- `align_frequency()` - Resample to target frequency
- `align_business_days()` - SSE, NYSE, HKEX, LSE calendars
- `align_multiple()` - Align multiple DataFrames to common dates

[`CorpActionHandler`](processor/corporate_actions.py:20):
- `adjust_for_splits()` - Price adjustment for stock splits
- `adjust_for_dividends()` - Dividend adjustment
- `calculate_adjusted_prices()` - Full corporate action handling

[`DataStandardizer`](processor/standardizer.py:15):
- `standardize_columns()` - Lowercase column names
- `standardize_index()` - DatetimeIndex named 'timestamp'
- `standardize_dtypes()` - Float for prices, numeric for volume

### 4. Portfolio Module (`portfolio/`)

**Purpose**: Portfolio optimization using pyportfolioopt.

**Key Classes**:

[`OptimizationResult`](portfolio/base.py:12) - Result model:
```python
@dataclass
class OptimizationResult:
    weights: Dict[str, float]
    expected_return: float
    volatility: float
    sharpe_ratio: float
    method_used: str
```

[`MeanVarianceOptimizer`](portfolio/mean_variance.py:15):
- Classical Markowitz optimization
- Methods: max_sharpe, min_volatility, max_return, min_risk
- Risk models: sample_cov, ledoit_wolf, exp_cov
- Expected returns: mean_historical, ema, capm

[`BlackLittermanOptimizer`](portfolio/black_litterman.py:18):
- Black-Litterman model implementation
- Views format: `{symbol: (expected_return, confidence)}`
- Omega calculation using Idzorek method
- Market equilibrium from market caps

[`RiskCalculator`](portfolio/risk.py:12):
- VaR (historical, parametric, cornish_fisher)
- CVaR (Expected Shortfall)
- Sharpe, Sortino, Calmar ratios
- Maximum drawdown

[`ConstraintsBuilder`](portfolio/constraints.py:15):
- Long-only constraint
- Weight bounds
- Sector limits
- Target volatility/return

## Data Flow

```
1. User Request
       ↓
2. DownloadManager.download(task)
       ↓
3. Check Cache → Hit: Return cached data
       ↓ Miss
4. Fetcher.fetch() → Raw DataFrame
       ↓
5. Save to Cache
       ↓
6. ProcessingPipeline.run()
       ↓
   DataCleaner → DataAligner → DataStandardizer
       ↓
7. Clean DataFrame
       ↓
8. PortfolioOptimizer.run(prices)
       ↓
9. OptimizationResult
```

## Error Handling Patterns

1. **Fetcher errors**: Return empty DataFrame with error logged
2. **Cache errors**: Fall back to fresh download
3. **Processing errors**: Raise with descriptive message
4. **Optimization errors**: Return result with success=False

## Configuration Points

| Module | Configuration | Default |
|--------|--------------|---------|
| DataCache | cache_dir | `.cache/` |
| DataCache | ttl_hours | 24 |
| DownloadManager | max_concurrent | 5 |
| DataCleaner | max_gap_days | 5 |
| PortfolioOptimizer | risk_free_rate | 0.025 |
| BlackLittermanOptimizer | tau | 0.05 |

## Dependencies

```
pyportfolioopt>=1.5.0  # Portfolio optimization
yfinance>=0.2.0        # Yahoo Finance data
ccxt>=4.0.0            # Crypto exchange data
akshare>=1.10.0        # Chinese financial data
pandas>=2.0.0          # Data manipulation
numpy>=1.24.0          # Numerical operations
scipy>=1.10.0          # Optimization routines
```

## Extension Points

1. **New Data Source**: Create class implementing `AsyncBaseFetcher`
2. **Processing Step**: Create class inheriting from `ProcessingStep`
3. **Optimization Method**: Create class inheriting from `BaseOptimizer`
4. **Risk Metric**: Add static method to `RiskCalculator`

## Common Tasks for AI

### Adding a new fetcher
1. Create new file in `fetchers/`
2. Inherit from `AsyncBaseFetcher`
3. Implement `fetch()` method
4. Register in `fetchers/__init__.py`
5. Register with `DownloadManager` for use

### Adding a new processing step
1. Create class inheriting from `ProcessingStep`
2. Implement `process(df) -> pd.DataFrame`
3. Add to pipeline: `pipeline.add_step(MyStep())`

### Adding a new optimization method
1. Create class inheriting from `BaseOptimizer`
2. Implement `optimize(prices) -> OptimizationResult`
3. Add to `PortfolioOptimizer` method selection

## Testing

Run test script:
```bash
python test_portfolio_optimization.py
```

This validates:
- Data fetching from Chinese funds
- Data processing pipeline
- Portfolio optimization (Mean-Variance and Black-Litterman)
- Risk metrics calculation
