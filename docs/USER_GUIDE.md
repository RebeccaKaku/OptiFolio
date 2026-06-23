# OptiFolio User Guide

> A practical guide for using OptiFolio to fetch financial data and optimize portfolios

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Data Fetching](#data-fetching)
4. [Data Processing](#data-processing)
5. [Portfolio Optimization](#portfolio-optimization)
6. [Complete Example](#complete-example)
7. [Troubleshooting](#troubleshooting)

---

## Installation

### Requirements
- Python 3.9+
- pip package manager

### Install Dependencies

```bash
pip install pandas numpy scipy pyportfolioopt yfinance ccxt akshare
```

### Project Structure

```
OptiFolio/
├── fetchers/      # Data source modules
├── downloader/    # Download management
├── processor/     # Data cleaning
├── portfolio/     # Optimization
└── api_checker/   # Network diagnostics
```

---

## Quick Start

### 1. Fetch Stock Data

```python
from fetchers import YahooFinanceFetcher

fetcher = YahooFinanceFetcher()
df = await fetcher.fetch(
    symbol='AAPL',
    start_date='2024-01-01',
    end_date='2024-12-31'
)
print(df.head())
```

### 2. Optimize a Portfolio

```python
from portfolio import PortfolioOptimizer

optimizer = PortfolioOptimizer(method='black_litterman')
result = optimizer.run(prices_df)

print("Optimal Weights:", result.weights)
print("Expected Return:", result.expected_return)
print("Sharpe Ratio:", result.sharpe_ratio)
```

---

## Data Fetching

### Available Data Sources

| Source | Class | Symbols | Example |
|--------|-------|---------|---------|
| Yahoo Finance | `YahooFinanceFetcher` | US stocks, ETFs, Forex | AAPL, MSFT, EURUSD=X |
| Cryptocurrency | `CryptoFetcher` | Crypto pairs | BTC/USDT, ETH/USDT |
| Chinese Funds | `CnFundFetcher` | Chinese fund codes | 110022, 161725 |

### Yahoo Finance (Stocks & ETFs)

```python
from fetchers import YahooFinanceFetcher

fetcher = YahooFinanceFetcher()

# Fetch Apple stock
df = await fetcher.fetch(
    symbol='AAPL',
    start_date='2024-01-01',
    end_date='2024-12-31',
    timeframe='1d'
)

# Fetch ETF
spy = await fetcher.fetch('SPY', '2024-01-01', '2024-12-31')

# Fetch forex
eurusd = await fetcher.fetch('EURUSD=X', '2024-01-01', '2024-12-31')
```

### Cryptocurrency

```python
from fetchers import CryptoFetcher

# Default: Binance
fetcher = CryptoFetcher()

# Fetch BTC/USDT
df = await fetcher.fetch(
    symbol='BTC/USDT',
    start_date='2024-01-01',
    end_date='2024-12-31'
)

# Use different exchange
okx_fetcher = CryptoFetcher(exchange_id='okx')
df = await okx_fetcher.fetch('ETH/USDT', '2024-01-01', '2024-12-31', exchange='okx')
```

### Chinese Funds

```python
from fetchers import CnFundFetcher

fetcher = CnFundFetcher()

# Fetch fund data (6-digit code)
df = await fetcher.fetch(
    symbol='110022',  # 易方达消费行业
    start_date='2024-01-01',
    end_date='2024-12-31'
)
```

### Output Format

All fetchers return a pandas DataFrame with standardized format:

```
              open    high     low   close    volume
timestamp                                           
2024-01-02  185.64  186.45  184.35  185.92  45678900
2024-01-03  184.50  185.20  183.80  184.25  38924500
...
```

---

## Data Processing

### Using the Processing Pipeline

```python
from processor import ProcessingPipeline, DataCleaner, DataAligner, DataStandardizer

# Create pipeline
pipeline = ProcessingPipeline()
pipeline.add_step(DataCleaner())
pipeline.add_step(DataAligner())
pipeline.add_step(DataStandardizer())

# Process data
clean_df = pipeline.run(raw_df)
```

### Data Cleaning Options

```python
cleaner = DataCleaner()

# Handle missing values
df = cleaner.handle_missing_values(df, method='ffill', limit=5)

# Remove outliers
df = cleaner.remove_outliers(df, method='iqr', threshold=1.5)

# Fill gaps
df = cleaner.fill_gaps(df, max_gap_days=5)

# Validate OHLCV data
is_valid = cleaner.validate_ohlcv(df)
```

### Data Alignment

```python
aligner = DataAligner()

# Align timezone
df = aligner.align_timezone(df, target_tz='Asia/Shanghai')

# Align to business days
df = aligner.align_business_days(df, calendar='SSE')  # Shanghai Stock Exchange

# Align multiple DataFrames
aligned = aligner.align_multiple({
    'AAPL': aapl_df,
    'MSFT': msft_df,
    'GOOG': goog_df
})
```

---

## Portfolio Optimization

### Mean-Variance Optimization

```python
from portfolio import MeanVarianceOptimizer

optimizer = MeanVarianceOptimizer(
    risk_free_rate=0.02,  # 2% risk-free rate
    long_only=True
)

# Maximize Sharpe ratio
result = optimizer.optimize(prices_df, method='max_sharpe')

# Minimize volatility
result = optimizer.optimize(prices_df, method='min_volatility')

print(f"Optimal Weights: {result.weights}")
print(f"Expected Return: {result.expected_return:.2%}")
print(f"Volatility: {result.volatility:.2%}")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
```

### Black-Litterman Optimization

The Black-Litterman model combines market equilibrium with investor views.

```python
from portfolio import BlackLittermanOptimizer

optimizer = BlackLittermanOptimizer(risk_free_rate=0.02)

# Set your views: {symbol: (expected_return, confidence)}
# Confidence: 0.0 (no confidence) to 1.0 (full confidence)
optimizer.set_views({
    'AAPL': (0.15, 0.7),   # Expect 15% return, 70% confident
    'MSFT': (0.12, 0.6),   # Expect 12% return, 60% confident
    'GOOG': (0.08, 0.5)    # Expect 8% return, 50% confident
})

# Set market capitalizations (optional but recommended)
optimizer.set_market_caps({
    'AAPL': 3_000_000_000_000,
    'MSFT': 2_800_000_000_000,
    'GOOG': 1_800_000_000_000
})

# Run optimization
result = optimizer.optimize(prices_df)
```

### Unified Interface

```python
from portfolio import PortfolioOptimizer

# Create optimizer
optimizer = PortfolioOptimizer(method='black_litterman')

# Add views
optimizer.add_views({
    'AAPL': (0.15, 0.7),
    'MSFT': (0.12, 0.6)
})

# Run optimization
result = optimizer.run(prices_df)

# Get detailed report
report = optimizer.get_report()
print(report)
```

### Risk Metrics

```python
from portfolio import RiskCalculator

# Calculate returns
returns = prices_df.pct_change().dropna()

# Value at Risk
var_95 = RiskCalculator.calculate_var(returns, confidence=0.95)
print(f"VaR (95%): {var_95:.2%}")

# Conditional VaR (Expected Shortfall)
cvar = RiskCalculator.calculate_cvar(returns, confidence=0.95)
print(f"CVaR (95%): {cvar:.2%}")

# Sharpe Ratio
sharpe = RiskCalculator.calculate_sharpe(returns, risk_free_rate=0.02)
print(f"Sharpe Ratio: {sharpe:.2f}")

# Maximum Drawdown
max_dd = RiskCalculator.calculate_max_drawdown(returns)
print(f"Max Drawdown: {max_dd:.2%}")

# All metrics at once
metrics = RiskCalculator.calculate_all_metrics(returns, risk_free_rate=0.02)
```

---

## Complete Example

### Portfolio Optimization for Chinese Funds

```python
import asyncio
from datetime import datetime, timedelta
from fetchers import CnFundFetcher
from downloader import DownloadManager, DownloadTask
from processor import ProcessingPipeline, DataCleaner, DataAligner, DataStandardizer
from portfolio import PortfolioOptimizer, RiskCalculator

async def main():
    # 1. Setup
    manager = DownloadManager()
    manager.register_fetcher('cn_fund', CnFundFetcher())
    
    # 2. Define funds
    funds = {
        '110022': 'Consumer Fund',
        '161725': 'Baijiu Fund',
        '510300': 'CSI 300 ETF',
    }
    
    # 3. Download data
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365*2)).strftime('%Y-%m-%d')
    
    tasks = [
        DownloadTask(symbol=code, source='cn_fund', 
                     start_date=start_date, end_date=end_date)
        for code in funds.keys()
    ]
    
    results = await manager.download_batch(tasks)
    
    # 4. Process data
    pipeline = ProcessingPipeline()
    pipeline.add_step(DataCleaner())
    pipeline.add_step(DataAligner())
    pipeline.add_step(DataStandardizer())
    
    prices = {}
    for result in results:
        if result.success:
            clean_df = pipeline.run(result.data)
            prices[result.task.symbol] = clean_df['close']
    
    prices_df = pd.DataFrame(prices).dropna()
    
    # 5. Optimize portfolio
    optimizer = PortfolioOptimizer(method='black_litterman')
    optimizer.add_views({
        '110022': (0.15, 0.7),  # Bullish on consumer
        '161725': (0.12, 0.6),  # Moderately bullish on baijiu
    })
    
    result = optimizer.run(prices_df)
    
    # 6. Display results
    print("\n=== Optimal Portfolio Allocation ===")
    for symbol, weight in result.weights.items():
        name = funds.get(symbol, symbol)
        print(f"{name} ({symbol}): {weight:.2%}")
    
    print(f"\nExpected Annual Return: {result.expected_return:.2%}")
    print(f"Annual Volatility: {result.volatility:.2%}")
    print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")

asyncio.run(main())
```

---

## Troubleshooting

### Network Issues

Run the API checker to diagnose connectivity:

```python
from api_checker import quick_check

quick_check()
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `ImportError` | Missing dependency | `pip install <package>` |
| `Empty DataFrame` | Invalid symbol or date range | Check symbol format and dates |
| `OptimizationError` | Insufficient data | Need at least 2 assets and 30+ days |
| `ConnectionError` | Network/proxy issue | Check internet connection |

### Proxy Configuration

If behind a proxy, set environment variables:

```bash
export HTTP_PROXY="http://proxy:port"
export HTTPS_PROXY="http://proxy:port"
```

### Cache Management

```python
from downloader import DataCache

cache = DataCache()

# Clear all cache
cache.clear()

# Clear expired entries only
cache.clear_expired()

# View cache statistics
stats = cache.get_cache_stats()
print(f"Cache size: {stats['total_size_mb']:.2f} MB")
```

---

## Support

For issues or questions:
1. Check this user guide
2. Review the API documentation in `docs/AI_CONTEXT-656c946.md`
3. Run `api_checker.quick_check()` to diagnose network issues
