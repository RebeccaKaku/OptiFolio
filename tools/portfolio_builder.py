#!/usr/bin/env python
"""Portfolio Builder — Backtest-Driven Allocation

1. Pull 2yr price data for all priceable assets
2. Calculate risk/return metrics
3. Optimize allocation (Mean-Variance + Risk Parity)
4. Backtest and compare strategies
5. Output recommended portfolio
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from findata import fd

# ── Portfolio Universe ─────────────────────────────────────────────────
# Assets we can actually price (from market data)
UNIVERSE = {
    # US Equities
    "equity.us.aapl":  "Apple (Technology)",
    "equity.us.qqq":   "NASDAQ 100 ETF (Growth)",
    "equity.us.msft":  "Microsoft (Technology)",
    "equity.us.googl": "Alphabet (Technology)",
    # Defensive / Hedges
    "equity.us.gld":   "Gold Trust (Inflation Hedge)",
    "equity.us.tlt":   "20Y Treasury Bond (Rate Hedge)",
    # China Equities
    "equity.cn.sh.600519": "Kweichow Moutai (Consumer)",
    "equity.cn.sh.601398": "ICBC (Financial)",
    "equity.cn.sh.601899": "Zijin Mining (Gold/Copper)",
    "equity.cn.sh.600028": "Sinopec (Energy)",
    "equity.cn.sz.000001": "Ping An Bank (Financial)",
    # China ETFs
    "fund.cn.etf.sh.510300": "CSI 300 ETF (Broad Market)",
}

# Cash-like (no backtest needed, used for liquidity buffer)
CASH_PRODUCTS = {
    "fund.cn.money.000198": "Tianhong YuEBao (Money Mkt)",
    "fund.cn.money.004502": "BOC Ruyibao (Money Mkt)",
}

BENCHMARK = "fund.cn.etf.sh.510300"  # CSI 300 ETF as benchmark

# ── Data Pull ──────────────────────────────────────────────────────────

def pull_prices(assets: List[str], years: int = 2) -> pd.DataFrame:
    """Pull daily close prices for *assets* over the past *years*."""
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=years * 365)).isoformat()

    frames = []
    for asset in assets:
        try:
            series = fd.prices(asset, start=start, end=end)
            if not series.empty:
                frames.append(series.rename(asset))
        except Exception:
            pass

    if not frames:
        raise RuntimeError("No price data available")

    df = pd.concat(frames, axis=1).dropna(how="all")
    df.index = pd.to_datetime(df.index)
    return df


# ── Metrics ────────────────────────────────────────────────────────────

def calculate_metrics(prices: pd.DataFrame) -> pd.DataFrame:
    """Per-asset risk/return metrics from daily prices."""
    returns = prices.pct_change().dropna()

    metrics = pd.DataFrame(index=prices.columns)
    metrics["annual_return"] = returns.mean() * 252
    metrics["volatility"] = returns.std() * np.sqrt(252)
    metrics["sharpe"] = metrics["annual_return"] / metrics["volatility"]
    metrics["max_drawdown"] = (prices / prices.cummax() - 1).min()
    metrics["win_rate"] = (returns > 0).mean()

    return metrics


# ── Allocation Strategies ──────────────────────────────────────────────

def equal_weight(prices: pd.DataFrame) -> Dict[str, float]:
    n = len(prices.columns)
    return {c: 1.0 / n for c in prices.columns}


def risk_parity(prices: pd.DataFrame) -> Dict[str, float]:
    """Inverse-volatility weighted allocation."""
    returns = prices.pct_change().dropna()
    vols = returns.std()
    inv_vol = 1.0 / vols
    total = inv_vol.sum()
    return {c: inv_vol[c] / total for c in prices.columns}


def minimum_variance(prices: pd.DataFrame) -> Dict[str, float]:
    """Minimum variance portfolio (no return estimation needed)."""
    returns = prices.pct_change().dropna()
    cov = returns.cov() * 252
    n = len(cov)

    try:
        inv_cov = np.linalg.inv(cov.values)
        ones = np.ones(n)
        w = inv_cov @ ones / (ones @ inv_cov @ ones)
        return {col: max(0, float(w[i])) for i, col in enumerate(prices.columns)}
    except np.linalg.LinAlgError:
        return risk_parity(prices)


def max_sharpe(prices: pd.DataFrame, risk_free: float = 0.02) -> Dict[str, float]:
    """Maximum Sharpe ratio (tangency portfolio)."""
    returns = prices.pct_change().dropna()
    excess = returns.mean() * 252 - risk_free
    cov = returns.cov() * 252

    try:
        inv_cov = np.linalg.inv(cov.values)
        w = inv_cov @ excess.values
        w = np.maximum(w, 0)  # long-only
        if w.sum() == 0:
            return equal_weight(prices)
        w = w / w.sum()
        return {col: float(w[i]) for i, col in enumerate(prices.columns)}
    except np.linalg.LinAlgError:
        return risk_parity(prices)


# ── Backtest ───────────────────────────────────────────────────────────

def backtest(prices: pd.DataFrame, weights: Dict[str, float],
             initial: float = 100_000, name: str = "") -> Dict:
    """Simple daily-rebalanced backtest."""
    returns = prices.pct_change().dropna()

    # Align
    common_cols = [c for c in weights if c in returns.columns]
    w = pd.Series({c: weights[c] for c in common_cols})
    w = w / w.sum()

    port_returns = (returns[common_cols] * w).sum(axis=1)
    equity = (1 + port_returns).cumprod() * initial

    total_ret = (equity.iloc[-1] / initial - 1)
    years = len(equity) / 252
    ann_ret = (1 + total_ret) ** (1 / years) - 1 if years > 0 else 0
    vol = port_returns.std() * np.sqrt(252)
    sharpe = (ann_ret - 0.02) / vol if vol > 0 else 0
    max_dd = (equity / equity.cummax() - 1).min()

    return {
        "name": name,
        "final_value": float(equity.iloc[-1]),
        "total_return": float(total_ret),
        "annual_return": float(ann_ret),
        "volatility": float(vol),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_dd),
        "equity_curve": equity,
        "weights": {c: round(float(w[c]) * 100, 1) for c in common_cols},
    }


# ── Main ───────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("OptiFolio Portfolio Builder — Backtest-Driven Allocation")
    print("=" * 70)

    # 1. Pull data
    assets = list(UNIVERSE.keys())
    print(f"\n[1/5] Pulling price data for {len(assets)} assets (2yr lookback)...")
    prices = pull_prices(assets)
    print(f"  Data: {prices.index[0].date()} → {prices.index[-1].date()}, "
          f"{len(prices)} trading days, {len(prices.columns)} assets")

    # 2. Metrics
    print("\n[2/5] Calculating risk/return metrics...")
    metrics = calculate_metrics(prices)
    print("\n  Top by Sharpe ratio:")
    top = metrics.sort_values("sharpe", ascending=False).head(8)
    for asset, row in top.iterrows():
        name = UNIVERSE.get(asset, asset)
        print(f"    {asset:35s} Sharpe={row['sharpe']:.2f}  "
              f"Return={row['annual_return']:.1%}  Vol={row['volatility']:.1%}  "
              f"MaxDD={row['max_drawdown']:.1%}  ─ {name}")

    # 3. Allocations
    print("\n[3/5] Computing allocations...")
    strategies = {
        "Equal Weight": equal_weight(prices),
        "Risk Parity": risk_parity(prices),
        "Min Variance": minimum_variance(prices),
        "Max Sharpe": max_sharpe(prices),
    }

    # 4. Backtest
    print("\n[4/5] Backtesting strategies (initial $100,000)...")
    results = []
    for name, weights in strategies.items():
        r = backtest(prices, weights, name=name)
        results.append(r)
        print(f"  {name:15s}: ${r['final_value']:,.0f}  "
              f"AnnRet={r['annual_return']:.1%}  Vol={r['volatility']:.1%}  "
              f"Sharpe={r['sharpe']:.2f}  MaxDD={r['max_drawdown']:.1%}")

    # Also benchmark CSI 300
    bench_w = {BENCHMARK: 1.0}
    bench_r = backtest(prices, bench_w, name="CSI 300 (Benchmark)")
    print(f"  {'CSI 300 (Bench)':15s}: ${bench_r['final_value']:,.0f}  "
          f"AnnRet={bench_r['annual_return']:.1%}  Vol={bench_r['volatility']:.1%}  "
          f"Sharpe={bench_r['sharpe']:.2f}  MaxDD={bench_r['max_drawdown']:.1%}")

    # 5. Recommendation
    print("\n[5/5] Recommended Portfolio:")
    best = max(results, key=lambda r: r["sharpe"])

    print(f"\n  Strategy: {best['name']}")
    print(f"  Expected Return: {best['annual_return']:.1%}/yr")
    print(f"  Expected Volatility: {best['volatility']:.1%}/yr")
    print(f"  Sharpe Ratio: {best['sharpe']:.2f}")
    print(f"\n  Allocation:")
    for asset, pct in sorted(best["weights"].items(), key=lambda x: -x[1]):
        name = UNIVERSE.get(asset, asset)
        bar = "█" * int(pct / 2)
        print(f"    {asset:35s} {pct:5.1f}%  {bar}  {name}")

    # Cash buffer recommendation
    print(f"\n  [Cash] Liquidity Buffer (10-15% of portfolio):")
    for pid, name in CASH_PRODUCTS.items():
        print(f"    {pid:35s}  {name}")

    # Risk notes
    print(f"\n  [!]  Risk Notes:")
    corr = prices.pct_change().corr()
    # Check gold-equity correlation
    if "equity.us.gld" in corr.columns and "equity.us.qqq" in corr.columns:
        gld_qqq_corr = corr.loc["equity.us.gld", "equity.us.qqq"]
        print(f"    Gold/QQQ correlation: {gld_qqq_corr:.2f} "
              f"{'OK: Good hedge' if gld_qqq_corr < 0.3 else '--: Moderate hedge' if gld_qqq_corr < 0.5 else '!!: Poor hedge'}")
    if "equity.us.tlt" in corr.columns and "equity.us.qqq" in corr.columns:
        tlt_qqq_corr = corr.loc["equity.us.tlt", "equity.us.qqq"]
        print(f"    TLT/QQQ correlation: {tlt_qqq_corr:.2f} "
              f"{'OK: Good hedge' if tlt_qqq_corr < 0.1 else '[!]  Moderate' if tlt_qqq_corr < 0.3 else '!!: Poor hedge'}")

    # Bank WMP notes
    print(f"\n  [Bank] WMP Products (valued by NAV, not market price):")
    print(f"    Your SQLite book contains 18 bank WMP products from ICBC/BOSC/BOC.")
    print(f"    These are not backtestable (no daily market price).")
    print(f"    Recommendation: review each product's latest NAV and fee structure.")
    print(f"    For the backtest, we focus on market-priceable assets above.")

    print("\n" + "=" * 70)
    print("Done. Run with: python tools/portfolio_builder.py")
    print("=" * 70)


if __name__ == "__main__":
    main()
