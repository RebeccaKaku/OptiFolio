"""DataProvider — fast data serving with optional live refresh."""

from __future__ import annotations

from typing import Optional, List, Dict, Any
import pandas as pd
import numpy as np


class DataProvider:
    """Serves financial data to algorithms, risk, and APIs.

    All methods default to mode='fast' (read from local Parquet, <10ms).
    mode='live' triggers a refresh via the orchestrator before returning.
    mode='tolerant' returns cached data immediately and triggers background refresh.
    """

    def __init__(self, store=None):
        from FinData.storage_dept.store import CanonicalStore
        self._store = store or CanonicalStore()

    # ── raw data ──

    def prices(self, symbol: str, start: str = None, end: str = None,
               mode: str = "fast") -> Optional[pd.Series]:
        """Close price series for one asset."""
        if mode == "live":
            self._trigger_refresh([symbol])
        panel = self._store.get_prices([symbol], start=start, end=end)
        if panel.empty or symbol not in panel.columns:
            return None
        return panel[symbol].dropna()

    def ohlcv(self, symbol: str, start: str = None, end: str = None,
              mode: str = "fast") -> pd.DataFrame:
        """Full OHLCV for one asset."""
        if mode == "live":
            self._trigger_refresh([symbol])
        return self._store.get_prices([symbol], start=start, end=end)

    def panel(self, symbols: List[str], start: str = None, end: str = None,
              mode: str = "fast") -> pd.DataFrame:
        """Multi-asset pivoted price matrix."""
        if mode == "live":
            self._trigger_refresh(symbols)
        return self._store.get_prices(symbols, start=start, end=end)

    # ── derived transforms ──

    def returns(self, symbol: str, start: str = None, end: str = None,
                frequency: str = "D") -> pd.Series:
        """Percentage returns for one asset."""
        prices = self.prices(symbol, start=start, end=end)
        if prices is None or len(prices) < 2:
            return pd.Series(dtype=float)
        if frequency.upper() not in ("D", "1D"):
            prices = prices.resample(frequency).last()
        return prices.pct_change().dropna()

    def metrics(self, symbol: str, metric: str | List[str] = "all",
                start: str = None, end: str = None,
                risk_free_rate: float = 0.0) -> Dict[str, float]:
        """Compute standard financial metrics.

        Available: total_return, annualized_return, volatility, sharpe_ratio,
                  max_drawdown, sortino_ratio, calmar_ratio, win_rate
        """
        METRIC_FUNCS = {
            "sharpe_ratio": self._calc_sharpe,
            "total_return": self._calc_total_return,
            "annualized_return": self._calc_annualized_return,
            "volatility": self._calc_volatility,
            "max_drawdown": self._calc_max_drawdown,
            "sortino_ratio": self._calc_sortino,
            "calmar_ratio": self._calc_calmar,
            "win_rate": self._calc_win_rate,
        }

        if metric == "all":
            keys = list(METRIC_FUNCS.keys())
        elif isinstance(metric, str):
            keys = [metric]
        else:
            keys = metric

        prices = self.prices(symbol, start=start, end=end)
        if prices is None or len(prices) < 2:
            return {k: 0.0 for k in keys}

        result = {}
        for k in keys:
            if k in METRIC_FUNCS:
                result[k] = METRIC_FUNCS[k](prices, risk_free_rate)
        return result

    # ── rates ──

    # ── IMPORTANT ──────────────────────────────────────────────────────
    # These rates are HARDCODED RESEARCH APPROXIMATIONS.
    # They are NOT real-time market data and should NEVER be displayed
    # as "current" or "live" in any UI.
    # _RATE_SOURCE = "hardcoded_stub"
    # TODO: replace with actual macro data pipeline (PBOC, FRED, SHIBOR)

    def rate(self, rate_id: str = "1y_cn") -> Dict[str, Any]:
        RATE_STUBS = {
            "1y_cn": 0.017, "5y_cn": 0.036, "10y_cn": 0.028,
        }
        value = RATE_STUBS.get(rate_id, 0.0)
        return {
            "rate_id": rate_id,
            "value": value,
            "source": "hardcoded_stub",
            "as_of": None,
            "warning": "RESEARCH APPROXIMATION — NOT real-time market data. Do not display as live/current in UI.",
        }

    def fx_rate(self, from_currency: str, to_currency: str,
                date_str: str = None) -> float:
        """Get FX rate. Uses stored FX data if available, else fallback."""
        from src.core.valuation import FxRateProvider
        fx = FxRateProvider()
        if date_str:
            try:
                return fx.get_rate_from_repository(from_currency, to_currency,
                                                   pd.Timestamp(date_str).date())
            except Exception:
                pass
        return fx.get_rate(from_currency, to_currency)

    # ── export ──

    def export(self, symbol: str, start: str = None, end: str = None,
               format: str = "csv") -> str:
        """Export price data to CSV or JSON string."""
        prices = self.prices(symbol, start=start, end=end)
        if prices is None:
            return "" if format == "csv" else "[]"

        if format == "csv":
            return prices.to_csv()
        elif format == "json":
            import json
            return json.dumps({
                "symbol": symbol,
                "data": {str(k): float(v) for k, v in prices.items()},
            })
        else:
            raise ValueError(f"Unknown format: {format}")

    # ── metric calculators ──
    def _calc_sharpe(self, prices, rfr):
        r = prices.pct_change().dropna()
        if len(r) < 2:
            return 0.0
        ann_ret = (1 + r.mean())**252 - 1
        vol = r.std() * np.sqrt(252)
        return float((ann_ret - rfr) / vol) if vol > 0 else 0.0

    def _calc_total_return(self, prices, _):
        return float(prices.iloc[-1] / prices.iloc[0] - 1)

    def _calc_annualized_return(self, prices, _):
        total = prices.iloc[-1] / prices.iloc[0] - 1
        days = (prices.index[-1] - prices.index[0]).days
        days = max(days, 1)
        return float((1 + total) ** (365.0 / days) - 1)

    def _calc_volatility(self, prices, _):
        r = prices.pct_change().dropna()
        return float(r.std() * np.sqrt(252))

    def _calc_max_drawdown(self, prices, _):
        dd = prices / prices.cummax() - 1
        return float(dd.min())

    def _calc_sortino(self, prices, rfr):
        r = prices.pct_change().dropna()
        neg = r[r < 0]
        if len(neg) < 2:
            return 0.0
        ann_ret = (1 + r.mean())**252 - 1
        dd = neg.std() * np.sqrt(252)
        return float((ann_ret - rfr) / dd) if dd > 0 else 0.0

    def _calc_calmar(self, prices, _):
        ann = self._calc_annualized_return(prices, 0)
        dd = abs(self._calc_max_drawdown(prices, 0))
        return float(ann / dd) if dd > 0 else 0.0

    def _calc_win_rate(self, prices, _):
        r = prices.pct_change().dropna()
        return float((r > 0).sum() / len(r)) if len(r) > 0 else 0.0

    def _trigger_refresh(self, symbols):
        """Trigger live refresh via orchestrator. Stub — Phase 3 wires this."""
        # TODO: wire to FinData.orchestrator.Orchestrator when orchestrator is stable
        import warnings
        warnings.warn(f"Live refresh not yet wired — using cached data for {symbols}")
