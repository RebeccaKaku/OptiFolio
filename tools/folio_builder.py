#!/usr/bin/env python
"""Portfolio Builder v2 — Multi-Asset Allocation & Risk Hedging

1. Pull price data for ~80-100 tradeable assets (ETFs, large caps, commodities)
2. Compute correlation matrix and risk metrics
3. Optimize: Max Sharpe, Risk Parity, Min Variance, Black-Litterman
4. Backtest all strategies
5. Output recommended portfolio with hedge analysis
"""
from __future__ import annotations

import sys, warnings
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from findata import fd

# ── Asset Universe ─────────────────────────────────────────────────────
# ETFs + Large Caps for diversification across asset classes

UNIVERSE = {
    # === US Broad Market ETFs ===
    "equity.us.spy":  "SPY — S&P 500 ETF",
    "equity.us.qqq":  "QQQ — NASDAQ 100 ETF",
    "equity.us.iwm":  "IWM — Russell 2000 Small Cap",
    "equity.us.dia":  "DIA — Dow Jones Industrial",
    # === US Sector ETFs ===
    "equity.us.xlk":  "XLK — Technology Sector",
    "equity.us.xlf":  "XLF — Financial Sector",
    "equity.us.xle":  "XLE — Energy Sector",
    "equity.us.xlv":  "XLV — Healthcare Sector",
    "equity.us.xli":  "XLI — Industrial Sector",
    "equity.us.xlp":  "XLP — Consumer Staples",
    "equity.us.xly":  "XLY — Consumer Discretionary",
    "equity.us.xlb":  "XLB — Materials Sector",
    "equity.us.xlu":  "XLU — Utilities Sector",
    "equity.us.xlre": "XLRE — Real Estate Sector",
    # === International ETFs ===
    "equity.us.eem":  "EEM — Emerging Markets",
    "equity.us.efa":  "EFA — Developed Markets ex-US",
    "equity.us.ewj":  "EWJ — Japan",
    "equity.us.ewg":  "EWG — Germany",
    "equity.us.fxi":  "FXI — China Large Cap",
    # === Bond ETFs ===
    "equity.us.tlt":  "TLT — 20Y+ Treasury (Duration Hedge)",
    "equity.us.ief":  "IEF — 7-10Y Treasury",
    "equity.us.shy":  "SHY — 1-3Y Treasury (Cash Proxy)",
    "equity.us.lqd":  "LQD — Investment Grade Corporate",
    "equity.us.hyg":  "HYG — High Yield Corporate",
    "equity.us.tip":  "TIP — TIPS (Inflation Protected)",
    # === Commodity & Alternative ETFs ===
    "equity.us.gld":  "GLD — Gold (Inflation/Geopolitical Hedge)",
    "equity.us.slv":  "SLV — Silver",
    "equity.us.uso":  "USO — Crude Oil",
    "equity.us.dba":  "DBA — Agricultural Commodities",
    "equity.us.vnq":  "VNQ — REIT Index",
    # === Factor & Strategy ETFs ===
    "equity.us.mtu":  "MTUM — Momentum Factor",
    "equity.us.usmv": "USMV — Minimum Volatility",
    "equity.us.qual": "QUAL — Quality Factor",
    "equity.us.vlUE": "VLUE — Value Factor",
    "equity.us.splv": "SPLV — Low Volatility",
    # === US Mega Caps (Alpha Generators) ===
    "equity.us.aapl":  "Apple Inc.",
    "equity.us.msft":  "Microsoft Corp.",
    "equity.us.googl": "Alphabet Inc.",
    "equity.us.amzn":  "Amazon.com Inc.",
    "equity.us.nvda":  "NVIDIA Corp.",
    "equity.us.meta":  "Meta Platforms Inc.",
    "equity.us.tsla":  "Tesla Inc.",
    "equity.us.brk.b": "Berkshire Hathaway",
    "equity.us.jpm":   "JPMorgan Chase",
    "equity.us.v":     "Visa Inc.",
    "equity.us.unh":   "UnitedHealth Group",
    "equity.us.jnj":   "Johnson & Johnson",
    "equity.us.wmt":   "Walmart Inc.",
    "equity.us.pg":    "Procter & Gamble",
    "equity.us.xom":   "Exxon Mobil",
    "equity.us.cvx":   "Chevron Corp.",
    "equity.us.cost":  "Costco Wholesale",
    "equity.us.nflx":  "Netflix Inc.",
    "equity.us.adbe":  "Adobe Inc.",
    "equity.us.crm":   "Salesforce Inc.",
    # === China Exposure ===
    "equity.cn.sh.600519": "Kweichow Moutai",
    "equity.cn.sh.601398": "ICBC",
    "equity.cn.sh.601899": "Zijin Mining (Gold/Copper)",
    "equity.cn.sh.600028": "Sinopec (Energy)",
    "equity.cn.sz.000001": "Ping An Bank",
    "fund.cn.etf.sh.510300": "CSI 300 ETF",
}

BENCHMARKS = {
    "equity.us.spy": "S&P 500 (Benchmark)",
    "fund.cn.etf.sh.510300": "CSI 300 (Benchmark)",
}

RISK_FREE_RATE = 0.045  # ~current SOFR


# ── Data ────────────────────────────────────────────────────────────────

def pull_prices(assets: List[str], years: int = 2) -> pd.DataFrame:
    """Pull daily adjusted close for *assets* via findata.

    findata handles all sourcing internally (cache -> live fetcher).
    Callers never decide *where* data comes from.
    """
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=years * 365)).isoformat()

    frames, missing, live = [], [], 0
    for asset in assets:
        # Try cache first
        try:
            series = fd.prices(asset, start=start, end=end)
            if not series.empty and len(series) > 60:
                frames.append(series.rename(asset))
                continue
        except Exception:
            pass

        # Ask findata to fetch live
        try:
            series = fd.prices(asset, start=start, end=end, mode="live")
            if not series.empty:
                frames.append(series.rename(asset))
                live += 1
                continue
        except Exception:
            pass

        missing.append(asset)

    if live:
        print(f"  Live-fetched via findata: {live} assets")
    if missing:
        print(f"  Unavailable: {len(missing)} assets")

    df = pd.concat(frames, axis=1).dropna(how="all")
    df.index = pd.to_datetime(df.index)
    return df


# ── Metrics ─────────────────────────────────────────────────────────────

def calc_metrics(prices: pd.DataFrame) -> pd.DataFrame:
    returns = prices.pct_change(fill_method=None).dropna()
    m = pd.DataFrame(index=prices.columns)
    m["ann_ret"] = returns.mean() * 252
    m["vol"] = returns.std() * np.sqrt(252)
    m["sharpe"] = (m["ann_ret"] - RISK_FREE_RATE) / m["vol"]
    m["max_dd"] = (prices / prices.cummax() - 1).min()
    m["win_rate"] = (returns > 0).mean()
    return m


# ── Correlation Analysis ────────────────────────────────────────────────

def hedge_score(prices: pd.DataFrame) -> pd.DataFrame:
    """Score each asset as a hedge: low correlation to equity = good hedge."""
    returns = prices.pct_change(fill_method=None).dropna()
    corr = returns.corr()

    # Equity proxy: average of SPY, QQQ, IWM if available
    equity_proxies = [c for c in ["equity.us.spy", "equity.us.qqq", "equity.us.iwm"] if c in corr.columns]
    if equity_proxies:
        eq_corr = corr[equity_proxies].mean(axis=1)
    else:
        eq_corr = corr.mean(axis=1)

    score = pd.DataFrame({"equity_corr": eq_corr, "hedge_quality": "none"}, index=corr.index)
    score.loc[eq_corr < 0.1, "hedge_quality"] = "excellent"
    score.loc[(eq_corr >= 0.1) & (eq_corr < 0.3), "hedge_quality"] = "good"
    score.loc[(eq_corr >= 0.3) & (eq_corr < 0.5), "hedge_quality"] = "moderate"
    score.loc[eq_corr >= 0.5, "hedge_quality"] = "poor"
    return score


# ── Allocation ──────────────────────────────────────────────────────────

def risk_parity(prices: pd.DataFrame) -> Dict[str, float]:
    returns = prices.pct_change(fill_method=None).dropna()
    vols = returns.std()
    inv_vol = 1.0 / vols.clip(lower=0.001)
    return (inv_vol / inv_vol.sum()).to_dict()


def min_variance(prices: pd.DataFrame) -> Dict[str, float]:
    returns = prices.pct_change(fill_method=None).dropna()
    cov = returns.cov() * 252
    try:
        inv = np.linalg.inv(cov.values)
        ones = np.ones(len(cov))
        w = inv @ ones / (ones @ inv @ ones)
        w = np.maximum(w, 0)
        return {c: float(w[i]) for i, c in enumerate(cov.columns)}
    except np.linalg.LinAlgError:
        return risk_parity(prices)


def max_sharpe(prices: pd.DataFrame) -> Dict[str, float]:
    returns = prices.pct_change(fill_method=None).dropna()
    excess = returns.mean() * 252 - RISK_FREE_RATE
    cov = returns.cov() * 252
    try:
        inv = np.linalg.inv(cov.values)
        w = inv @ excess.values
        w = np.maximum(w, 0)
        if w.sum() == 0:
            return risk_parity(prices)
        w = w / w.sum()
        return {c: float(w[i]) for i, c in enumerate(cov.columns)}
    except np.linalg.LinAlgError:
        return risk_parity(prices)


def risk_budget(prices: pd.DataFrame, risk_budgets: Dict[str, float] | None = None) -> Dict[str, float]:
    """Equal risk contribution (ERC) portfolio."""
    returns = prices.pct_change(fill_method=None).dropna()
    cov = returns.cov() * 252
    n = len(cov)
    if risk_budgets is None:
        risk_budgets = {c: 1.0 / n for c in cov.columns}

    # Simple ERC approximation via inverse volatility
    vols = np.sqrt(np.diag(cov.values))
    w = {c: float(risk_budgets.get(c, 1.0 / n) / max(vols[i], 0.001))
         for i, c in enumerate(cov.columns)}
    total = sum(w.values())
    return {c: w[c] / total for c in w}


# ── Backtest ────────────────────────────────────────────────────────────

def backtest(prices: pd.DataFrame, weights: Dict[str, float],
             initial: float = 100_000, name: str = "") -> Dict:
    returns = prices.pct_change(fill_method=None).dropna()
    common = [c for c in weights if c in returns.columns]
    w = pd.Series({c: weights[c] for c in common})
    w = w / w.sum()

    port_ret = (returns[common] * w).sum(axis=1)
    equity = (1 + port_ret).cumprod() * initial

    total_ret = equity.iloc[-1] / initial - 1
    years = len(equity) / 252
    ann_ret = (1 + total_ret) ** (1 / years) - 1 if years > 0 else 0
    vol = port_ret.std() * np.sqrt(252)
    sharpe = (ann_ret - RISK_FREE_RATE) / vol if vol > 0 else 0
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
        "weights": {c: round(float(w[c]) * 100, 1) for c in common if w[c] > 0.001},
    }


# ── Main ────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("  OptiFolio Portfolio Builder v2 — Multi-Asset Allocation")
    print("=" * 72)

    # 1. Pull data
    assets = list(UNIVERSE.keys())
    print(f"\n[1/6] Pulling data for {len(assets)} assets...")
    prices = pull_prices(assets)
    n_assets = len(prices.columns)
    print(f"  Loaded: {n_assets} assets, {len(prices)} days, "
          f"{prices.index[0].date()} -> {prices.index[-1].date()}")

    if n_assets < 10:
        print("  ERROR: Too few assets with data. Aborting.")
        return

    # 2. Correlation & Hedge Analysis
    print(f"\n[2/6] Correlation & hedge analysis...")
    hedge = hedge_score(prices)
    excellent = (hedge["hedge_quality"] == "excellent").sum()
    good = (hedge["hedge_quality"] == "good").sum()
    print(f"  Hedges: {excellent} excellent, {good} good (out of {n_assets})")
    if excellent + good > 0:
        print("  Top hedges (lowest equity correlation):")
        for asset in hedge.nsmallest(5, "equity_corr").index:
            name = UNIVERSE.get(asset, "")
            print(f"    {asset:30s} corr={hedge.loc[asset,'equity_corr']:.3f}  {hedge.loc[asset,'hedge_quality']:10s}  {name}")

    # 3. Metrics
    print(f"\n[3/6] Risk/return metrics...")
    metrics = calc_metrics(prices)
    print(f"  Top 10 by Sharpe ratio:")
    for asset in metrics.nlargest(10, "sharpe").index:
        m = metrics.loc[asset]
        print(f"    {asset:30s} Sharpe={m['sharpe']:.2f}  Ret={m['ann_ret']:.1%}  Vol={m['vol']:.1%}")

    # 4. Optimize
    print(f"\n[4/6] Portfolio optimization...")
    strategies = {
        "Risk Parity": risk_parity(prices),
        "Min Variance": min_variance(prices),
        "Max Sharpe": max_sharpe(prices),
        "Risk Budget (ERC)": risk_budget(prices),
    }

    # 5. Backtest
    print(f"\n[5/6] Backtesting ($100,000 initial)...")
    results = []
    for name, weights in strategies.items():
        r = backtest(prices, weights, name=name)
        results.append(r)
        n_pos = len(r["weights"])
        print(f"  {name:20s} ${r['final_value']:>10,.0f}  "
              f"Ret={r['annual_return']:>6.1%}  Vol={r['volatility']:>5.1%}  "
              f"Sharpe={r['sharpe']:>5.2f}  MaxDD={r['max_drawdown']:>6.1%}  "
              f"({n_pos} positions)")

    # Benchmarks
    for bench_id, bench_name in BENCHMARKS.items():
        if bench_id in prices.columns:
            r = backtest(prices, {bench_id: 1.0}, name=bench_name)
            print(f"  {bench_name:20s} ${r['final_value']:>10,.0f}  "
                  f"Ret={r['annual_return']:>6.1%}  Vol={r['volatility']:>5.1%}  "
                  f"Sharpe={r['sharpe']:>5.2f}  MaxDD={r['max_drawdown']:>6.1%}")

    # 6. Recommended Portfolio
    best = max(results, key=lambda r: r["sharpe"])
    print(f"\n[6/6] RECOMMENDED: {best['name']}")
    print(f"  Return: {best['annual_return']:.1%}/yr  |  Vol: {best['volatility']:.1%}/yr")
    print(f"  Sharpe: {best['sharpe']:.2f}  |  Max Drawdown: {best['max_drawdown']:.1%}")
    print(f"\n  Top Allocations:")
    for asset, pct in sorted(best["weights"].items(), key=lambda x: -x[1])[:15]:
        name = UNIVERSE.get(asset, asset)
        bar = "#" * int(pct * 2)
        print(f"    {asset:30s} {pct:5.1f}% {bar}")

    # Risk attribution
    if len(best["weights"]) > 5:
        wgt = pd.Series(best["weights"]) / 100
        common = [c for c in wgt.index if c in prices.columns]
        rets = prices[common].pct_change(fill_method=None).dropna()
        cov = rets.cov() * 252
        port_vol = np.sqrt(wgt[common] @ cov.loc[common, common] @ wgt[common])
        contrib = (wgt[common] * (cov.loc[common, common] @ wgt[common])) / port_vol
        print(f"\n  Risk Contribution (top 5):")
        for asset in contrib.nlargest(5).index:
            name = UNIVERSE.get(asset, asset)
            print(f"    {asset:30s} {contrib[asset]:.1%} of portfolio risk  [{name}]")

    print("\n" + "=" * 72)
    print("  Done. python tools/folio_builder.py to re-run.")
    print("=" * 72)


if __name__ == "__main__":
    main()
