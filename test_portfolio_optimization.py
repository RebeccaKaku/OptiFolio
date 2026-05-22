#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test Portfolio Optimization with Chinese Funds

This script demonstrates the full workflow:
1. Fetch data for representative Chinese funds using CnFundFetcher
2. Process and align data using the processor module
3. Run portfolio optimization (Mean-Variance and Black-Litterman)
4. Output optimal allocation and risk metrics
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

# Data fetching
from fetchers import CnFundFetcher

# Data processing
from processor import (
    ProcessingPipeline,
    DataCleaner,
    DataAligner,
    DataStandardizer,
)

# Portfolio optimization
from portfolio import (
    PortfolioOptimizer,
    RiskCalculator,
    OptimizationResult,
    RiskMetrics,
)


# =============================================================================
# Configuration
# =============================================================================

# Representative Chinese funds
FUND_CODES = {
    '110022': '易方达消费行业 (Consumer)',
    '161725': '招商中证白酒 (Baijiu/Liquor)',
    '510300': '沪深300ETF (CSI 300 ETF)',
    '510500': '中证500ETF (CSI 500 ETF)',
    '159915': '创业板ETF (ChiNext ETF)',
}

# Date range: last 2 years
END_DATE = datetime.now().strftime('%Y-%m-%d')
START_DATE = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')

# Risk-free rate (China 10-year treasury approximately)
RISK_FREE_RATE = 0.025


# =============================================================================
# Data Fetching
# =============================================================================

async def fetch_fund_data(
    fetcher: CnFundFetcher,
    fund_codes: Dict[str, str],
    start_date: str,
    end_date: str,
) -> Dict[str, pd.DataFrame]:
    """
    Fetch data for multiple funds.
    
    Args:
        fetcher: CnFundFetcher instance
        fund_codes: Dictionary mapping fund code to fund name
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
    
    Returns:
        Dictionary mapping fund code to DataFrame
    """
    print("\n" + "=" * 60)
    print("STEP 1: Fetching Fund Data")
    print("=" * 60)
    print(f"Date Range: {start_date} to {end_date}")
    print(f"Funds to fetch: {len(fund_codes)}")
    print()
    
    data = {}
    
    async def fetch_single(code: str, name: str):
        print(f"\nFetching {code} - {name}...")
        try:
            df = await fetcher.fetch(
                symbol=code,
                start_date=start_date,
                end_date=end_date,
                timeframe='1d',
            )
            
            if df.empty:
                print(f"  [!] No data returned for {code}")
                return code, None
            
            print(f"  [OK] Successfully fetched {len(df)} records for {code}")
            print(f"       Date range: {df.index.min().date()} to {df.index.max().date()}")
            return code, df
            
        except Exception as e:
            print(f"  [ERROR] Error fetching {code}: {e}")
            return code, None

    # Run fetches concurrently
    tasks = [fetch_single(code, name) for code, name in fund_codes.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for res in results:
        if isinstance(res, Exception):
            print(f"  [ERROR] Unexpected exception during fetch: {res}")
            continue

        code, df = res
        if df is not None:
            data[code] = df

    print(f"\n[OK] Successfully fetched data for {len(data)}/{len(fund_codes)} funds")
    return data


# =============================================================================
# Data Processing
# =============================================================================

def process_data(
    raw_data: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Process and align data from multiple funds.
    
    Args:
        raw_data: Dictionary mapping fund code to DataFrame
    
    Returns:
        DataFrame with aligned close prices for all funds
    """
    print("\n" + "=" * 60)
    print("STEP 2: Processing and Aligning Data")
    print("=" * 60)
    
    if not raw_data:
        print("[ERROR] No data to process")
        return pd.DataFrame()
    
    # Create processing pipeline
    pipeline = ProcessingPipeline()
    pipeline.add_step(DataCleaner())
    pipeline.add_step(DataAligner(target_tz='Asia/Shanghai', calendar='SSE'))
    pipeline.add_step(DataStandardizer())
    
    # Process each fund's data
    processed_data = {}
    for code, df in raw_data.items():
        print(f"\nProcessing {code}...")
        try:
            processed_df = pipeline.run(df)
            if not processed_df.empty:
                processed_data[code] = processed_df
                print(f"  [OK] Processed {len(processed_df)} records")
            else:
                print(f"  [!] Empty result after processing")
        except Exception as e:
            print(f"  [ERROR] Error processing {code}: {e}")
    
    if not processed_data:
        print("\n[ERROR] No data remaining after processing")
        return pd.DataFrame()
    
    # Align all funds to common dates
    print("\nAligning all funds to common dates...")
    
    # Find common date range
    all_dates = None
    for code, df in processed_data.items():
        dates = set(df.index)
        if all_dates is None:
            all_dates = dates
        else:
            all_dates = all_dates.intersection(dates)
    
    if not all_dates:
        print("[ERROR] No common dates found")
        return pd.DataFrame()
    
    common_dates = sorted(all_dates)
    print(f"  Common dates: {len(common_dates)} trading days")
    
    # Build aligned price DataFrame
    prices = pd.DataFrame(index=common_dates)
    for code, df in processed_data.items():
        prices[code] = df.loc[common_dates, 'close']
    
    # Remove any rows with NaN values
    prices = prices.dropna()
    
    print(f"\n[OK] Final aligned dataset: {len(prices)} records for {len(prices.columns)} funds")
    print(f"     Date range: {prices.index.min().date()} to {prices.index.max().date()}")
    
    return prices


# =============================================================================
# Portfolio Optimization
# =============================================================================

def run_mean_variance_optimization(prices: pd.DataFrame) -> Optional[OptimizationResult]:
    """
    Run Mean-Variance portfolio optimization.
    
    Args:
        prices: DataFrame with close prices
    
    Returns:
        OptimizationResult or None if optimization fails
    """
    print("\n" + "=" * 60)
    print("STEP 3a: Mean-Variance Optimization")
    print("=" * 60)
    
    try:
        optimizer = PortfolioOptimizer(
            method='mean_variance',
            risk_free_rate=RISK_FREE_RATE,
            long_only=True,
            weight_bounds=(0, 1),
        )
        
        # Run optimization for maximum Sharpe ratio
        result = optimizer.run(prices, optimization_method='max_sharpe')
        
        print(f"\n[OK] Optimization completed successfully")
        return result
        
    except Exception as e:
        print(f"\n[ERROR] Mean-Variance optimization failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_black_litterman_optimization(
    prices: pd.DataFrame,
    fund_names: Dict[str, str],
) -> Optional[OptimizationResult]:
    """
    Run Black-Litterman portfolio optimization with example views.
    
    Args:
        prices: DataFrame with close prices
        fund_names: Dictionary mapping fund code to name
    
    Returns:
        OptimizationResult or None if optimization fails
    """
    print("\n" + "=" * 60)
    print("STEP 3b: Black-Litterman Optimization")
    print("=" * 60)
    
    try:
        optimizer = PortfolioOptimizer(
            method='black_litterman',
            risk_free_rate=RISK_FREE_RATE,
        )
        
        # Add investor views (example: bullish on consumer sector)
        # Views format: {symbol: (expected_annual_return, confidence)}
        views = {}
        
        # Consumer sector - bullish view
        if '110022' in prices.columns:
            views['110022'] = (0.15, 0.7)  # 15% expected return, 70% confidence
            print(f"  Adding view: 110022 (Consumer) - 15% return, 70% confidence")
        
        # Baijiu/Liquor sector - slightly bullish
        if '161725' in prices.columns:
            views['161725'] = (0.12, 0.6)  # 12% expected return, 60% confidence
            print(f"  Adding view: 161725 (Baijiu) - 12% return, 60% confidence")
        
        # ChiNext - neutral to slightly bearish
        if '159915' in prices.columns:
            views['159915'] = (0.05, 0.5)  # 5% expected return, 50% confidence
            print(f"  Adding view: 159915 (ChiNext) - 5% return, 50% confidence")
        
        if views:
            optimizer.add_views(views)
        
        # Set equal market caps as approximation (in real scenario, use actual market caps)
        market_caps = {code: 1.0 for code in prices.columns}
        optimizer.set_market_caps(market_caps)
        
        # Run optimization
        result = optimizer.run(prices, optimization_method='max_sharpe')
        
        print(f"\n[OK] Black-Litterman optimization completed successfully")
        return result
        
    except Exception as e:
        print(f"\n[ERROR] Black-Litterman optimization failed: {e}")
        import traceback
        traceback.print_exc()
        return None


# =============================================================================
# Results Display
# =============================================================================

def display_optimization_result(
    result: OptimizationResult,
    fund_names: Dict[str, str],
    method_name: str,
):
    """
    Display optimization results in a formatted way.
    
    Args:
        result: OptimizationResult to display
        fund_names: Dictionary mapping fund code to name
        method_name: Name of the optimization method
    """
    print(f"\n{'=' * 60}")
    print(f"{method_name} Results")
    print("=" * 60)
    
    # Portfolio metrics
    print("\n[Portfolio Metrics]:")
    print(f"  Expected Annual Return: {result.expected_return:.2%}")
    print(f"  Annual Volatility:      {result.volatility:.2%}")
    print(f"  Sharpe Ratio:           {result.sharpe_ratio:.4f}")
    
    # Optimal allocation
    print("\n[Optimal Allocation]:")
    sorted_weights = result.sorted_weights
    
    for code, weight in sorted_weights:
        if weight > 0.001:  # Only show weights > 0.1%
            name = fund_names.get(code, code)
            print(f"  {code} - {name}")
            print(f"      Weight: {weight:.2%}")
    
    # Non-zero weights summary
    non_zero = result.non_zero_weights
    print(f"\n  Total positions: {len(non_zero)}")
    print(f"  Weights sum:     {sum(result.weights.values()):.4f}")


def calculate_and_display_risk_metrics(
    prices: pd.DataFrame,
    weights: Dict[str, float],
):
    """
    Calculate and display risk metrics for the portfolio.
    
    Args:
        prices: DataFrame with close prices
        weights: Portfolio weights
    """
    print(f"\n{'=' * 60}")
    print("Risk Metrics Analysis")
    print("=" * 60)
    
    # Calculate daily returns
    returns = prices.pct_change().dropna()
    
    # Calculate portfolio returns
    weight_array = np.array([weights.get(code, 0) for code in prices.columns])
    portfolio_returns = (returns * weight_array).sum(axis=1)
    
    # Calculate various risk metrics
    print("\n[Risk Metrics]:")
    
    # VaR
    var_95 = RiskCalculator.calculate_var(portfolio_returns, confidence=0.95)
    var_99 = RiskCalculator.calculate_var(portfolio_returns, confidence=0.99)
    print(f"  VaR (95%): {var_95:.2%}")
    print(f"  VaR (99%): {var_99:.2%}")
    
    # CVaR
    cvar_95 = RiskCalculator.calculate_cvar(portfolio_returns, confidence=0.95)
    print(f"  CVaR (95%): {cvar_95:.2%}")
    
    # Maximum Drawdown
    cumulative = (1 + portfolio_returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()
    print(f"  Max Drawdown: {max_drawdown:.2%}")
    
    # Sharpe and Sortino
    sharpe = RiskCalculator.calculate_sharpe(
        portfolio_returns, 
        risk_free_rate=RISK_FREE_RATE
    )
    sortino = RiskCalculator.calculate_sortino(
        portfolio_returns, 
        risk_free_rate=RISK_FREE_RATE
    )
    print(f"  Sharpe Ratio:  {sharpe:.4f}")
    print(f"  Sortino Ratio: {sortino:.4f}")
    
    # Volatility
    annual_vol = portfolio_returns.std() * np.sqrt(252)
    print(f"  Annual Volatility: {annual_vol:.2%}")
    
    # Additional statistics
    print("\n[Return Statistics]:")
    print(f"  Mean Daily Return:    {portfolio_returns.mean():.4%}")
    print(f"  Std Daily Return:     {portfolio_returns.std():.4%}")
    print(f"  Min Daily Return:     {portfolio_returns.min():.4%}")
    print(f"  Max Daily Return:     {portfolio_returns.max():.4%}")
    print(f"  Skewness:             {portfolio_returns.skew():.4f}")
    print(f"  Kurtosis:             {portfolio_returns.kurtosis():.4f}")


# =============================================================================
# Main Function
# =============================================================================

async def main():
    """
    Main function to run the complete portfolio optimization workflow.
    """
    print("\n" + "=" * 60)
    print("Chinese Fund Portfolio Optimization Test")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Step 1: Fetch data
    fetcher = CnFundFetcher(cache_dir=".cache")
    raw_data = await fetch_fund_data(
        fetcher=fetcher,
        fund_codes=FUND_CODES,
        start_date=START_DATE,
        end_date=END_DATE,
    )
    
    if not raw_data:
        print("\n[ERROR] No data fetched. Exiting.")
        return
    
    # Step 2: Process data
    prices = process_data(raw_data)
    
    if prices.empty:
        print("\n[ERROR] No processed data. Exiting.")
        return
    
    # Step 3a: Mean-Variance Optimization
    mv_result = run_mean_variance_optimization(prices)
    
    if mv_result:
        display_optimization_result(mv_result, FUND_CODES, "Mean-Variance Optimization")
        calculate_and_display_risk_metrics(prices, mv_result.weights)
    
    # Step 3b: Black-Litterman Optimization
    bl_result = run_black_litterman_optimization(prices, FUND_CODES)
    
    if bl_result:
        display_optimization_result(bl_result, FUND_CODES, "Black-Litterman Optimization")
        calculate_and_display_risk_metrics(prices, bl_result.weights)
    
    # Comparison
    if mv_result and bl_result:
        print(f"\n{'=' * 60}")
        print("Comparison: Mean-Variance vs Black-Litterman")
        print("=" * 60)
        print(f"\n{'Metric':<25} {'Mean-Variance':<20} {'Black-Litterman':<20}")
        print("-" * 65)
        print(f"{'Expected Return':<25} {mv_result.expected_return:>18.2%} {bl_result.expected_return:>18.2%}")
        print(f"{'Volatility':<25} {mv_result.volatility:>18.2%} {bl_result.volatility:>18.2%}")
        print(f"{'Sharpe Ratio':<25} {mv_result.sharpe_ratio:>18.4f} {bl_result.sharpe_ratio:>18.4f}")
    
    print(f"\n{'=' * 60}")
    print("Test Completed Successfully!")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
