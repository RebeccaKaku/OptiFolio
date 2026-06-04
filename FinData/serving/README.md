# FinData Serving — Public Data API

The serving department is the ONLY interface algorithms, risk modules, and APIs
should use. It abstracts all storage and provider details.

## Usage

```python
from FinData import fd

# ---- Raw data ----
fd.prices("AAPL", start="2024-01-01")           # → pd.Series (close prices)
fd.ohlcv("AAPL", start="2024-01-01")             # → pd.DataFrame (full OHLCV)
fd.panel(["AAPL", "QQQ"], start="2024-01-01")    # → pd.DataFrame (pivoted)

# ---- Transforms ----
fd.returns("AAPL", start="2024-01-01")           # → pd.Series (pct_change)
fd.returns("AAPL", frequency="M")                # → monthly returns

# ---- Metrics ----
fd.metrics("AAPL", "sharpe_ratio")               # → float
fd.metrics("AAPL", "all")                        # → dict of 8 metrics:
#   sharpe_ratio, sortino_ratio, calmar_ratio,
#   total_return, annualized_return, volatility,
#   max_drawdown, win_rate

# ---- Rates ----
fd.rate("1y_cn")     # → {"rate_id": "1y_cn", "value": 0.017, "source": "hardcoded_stub", ...}
fd.fx_rate("USD", "CNY")                         # → float (fallback rate)

# ---- Export ----
fd.export("AAPL", format="csv")                  # → CSV string
fd.export("AAPL", format="json")                 # → JSON string
fd.list_assets()                                  # → list of asset_ids
fd.missing_report(["AAPL", "QQQ"])               # → completeness stats

# ---- Modes ----
fd.prices("AAPL", mode="fast")      # default — read from local Parquet (<10ms)
fd.prices("AAPL", mode="live")      # trigger refresh before returning (not yet wired)
fd.prices("AAPL", mode="tolerant")  # return cached, async refresh in background
```

## Important

**`rate()` returns a dict, not float.** It includes `source: "hardcoded_stub"` and
a warning that these are RESEARCH APPROXIMATIONS — never display as live/current
in any UI.

**`mode="live"` is not yet wired.** It currently issues a warning and returns
cached data. Wire it to the orchestrator when the scheduling layer is stable.
