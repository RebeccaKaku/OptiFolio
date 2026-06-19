"""DataProvider — fast data serving with optional live refresh."""

from __future__ import annotations

from datetime import date
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
        from FinData.store.repository import CanonicalStore
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
        """Full OHLCV for one asset.

        Returns a DataFrame with columns: open, high, low, close, adj_close, volume.
        """
        if mode == "live":
            self._trigger_refresh([symbol])
        return self._store.get_prices(
            [symbol], start=start, end=end,
            fields=("open", "high", "low", "close", "adj_close", "volume"),
        )

    def panel(self, symbols: List[str], start: str = None, end: str = None,
              mode: str = "fast") -> pd.DataFrame:
        """Multi-asset pivoted price matrix."""
        if mode == "live":
            self._trigger_refresh(symbols)
        return self._store.get_prices(symbols, start=start, end=end)

    def get_metadata(self, symbol: str, asset_type: str = None) -> Optional[Dict[str, Any]]:
        """Return metadata for an asset from its designated fetcher."""
        from FinData.adapters import get_fetcher

        # If type not provided, try to infer or probe common types
        types_to_try = [asset_type] if asset_type else ["bank_wmp", "cn_fund", "us_equity"]

        for t in types_to_try:
            fetcher = get_fetcher(t)
            if fetcher and hasattr(fetcher, "get_metadata"):
                meta = fetcher.get_metadata(symbol)
                if meta:
                    return meta
        return None

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
            result = {k: 0.0 for k in keys}
            if "max_drawdown" in result:
                result["max_drawdown"] = None  # None = no data, distinguish from zero drawdown
            return result

        prices = prices.dropna()
        if len(prices) < 2:
            result = {k: 0.0 for k in keys}
            if "max_drawdown" in result:
                result["max_drawdown"] = None
            return result

        result = {}
        for k in keys:
            if k in METRIC_FUNCS:
                result[k] = METRIC_FUNCS[k](prices, risk_free_rate)
        return result

    # ── rates ──

    # Mapping from user-facing rate_id → stored observation series_id.
    # When a rate_id is not listed here, the legacy heuristic
    # ``RATE_{rate_id.upper()}`` is tried as a final fallback.
    _RATE_OBSERVATION_MAP: dict[str, str] = {
        "1y_cn":  "RATE_SHIBOR_CNY_1Y",
        "5y_cn":  "RATE_SHIBOR_CNY_1Y",   # no CGB yield stored yet — closest proxy
        "10y_cn": "RATE_SHIBOR_CNY_1Y",   # no CGB yield stored yet — closest proxy
        "1y_us":  "RATE_SOFR_USD_ON",
    }

    # Tenors for which the proxy is a tenor mismatch (SHIBOR 1Y used for
    # 5Y/10Y risk-free rate).  These are surfaced as warnings.
    _TENOR_MISMATCH_RATE_IDS: frozenset[str] = frozenset({"5y_cn", "10y_cn"})

    # Absolute last-resort hardcoded values — used ONLY when the repository
    # is completely unavailable (no observation store at all).
    _RATE_EMERGENCY_FALLBACKS: dict[str, float] = {
        "1y_cn":  0.0146,   # SHIBOR 1Y ≈ 2026-06-10
        "5y_cn":  0.0146,   # no CGB 5Y stored; use SHIBOR 1Y proxy
        "10y_cn": 0.0146,   # no CGB 10Y stored; use SHIBOR 1Y proxy
        "1y_us":  0.0360,   # SOFR ≈ 2026-06-09
    }

    @staticmethod
    def _rate_series_id(rate_id: str) -> str:
        """Resolve a user-facing rate_id to a stored observation series_id."""
        return DataProvider._RATE_OBSERVATION_MAP.get(
            rate_id, f"RATE_{rate_id.upper()}"
        )

    def rate(self, rate_id: str = "1y_cn", date_str: str = None) -> Dict[str, Any]:
        """Get an interest-rate or macro-rate observation.

        Resolution order:
        1. Stored canonical observations (authoritative).
        2. Peer-series proxy with explicit warning (e.g. SHIBOR 1Y for 5Y CGB).
        3. Emergency hardcoded fallback (repo unavailable entirely).
        """
        series_id = self._rate_series_id(rate_id)
        as_of = pd.Timestamp(date_str).date() if date_str else None
        repo = getattr(self._store, "repo", None)
        warning: str | None = None

        # ── 1. Stored observation (authoritative) ──
        if repo is not None and hasattr(repo, "latest_observation"):
            row = repo.latest_observation(series_id, as_of=as_of)
            if row is not None:
                effective = pd.Timestamp(row["effective_date"]).date().isoformat()
                known_at = row.get("known_at")
                if rate_id in self._TENOR_MISMATCH_RATE_IDS:
                    warning = (
                        f"TENOR MISMATCH: using {series_id} as proxy for {rate_id}. "
                        "No government bond yield series stored yet."
                    )
                return {
                    "rate_id": rate_id,
                    "series_id": series_id,
                    "value": float(row["value"]),
                    "source": row.get("source") or "canonical_observation",
                    "as_of": effective,
                    "known_at": pd.Timestamp(known_at).isoformat() if pd.notna(known_at) else None,
                    "unit": row.get("unit"),
                    "currency": row.get("currency"),
                    "warning": warning,
                }

        # ── 2. Repo exists but no observation for this series ──
        if repo is not None and hasattr(repo, "latest_observation"):
            # Repo is available but the specific series is missing.
            # This is a data gap, not a hardcoded-stub situation.
            return {
                "rate_id": rate_id,
                "series_id": series_id,
                "value": 0.0,
                "source": "missing_observation",
                "as_of": None,
                "warning": (
                    f"No stored observation for {series_id}. "
                    "Run tools/sync_macro_rates.py to populate."
                ),
            }

        # ── 3. Emergency fallback (repo entirely unavailable) ──
        value = self._RATE_EMERGENCY_FALLBACKS.get(rate_id, 0.0)
        return {
            "rate_id": rate_id,
            "series_id": series_id,
            "value": value,
            "source": "emergency_fallback",
            "as_of": None,
            "warning": (
                "EMERGENCY FALLBACK — repository unavailable. "
                "Do not use for valuation or risk decisions."
            ),
        }

    def fx_rate(self, from_currency: str, to_currency: str,
                date_str: str = None, mode: str = "fast") -> float:
        """Get FX rate. Uses stored FX data if available, else fallback."""
        from findata.fx import FindataFxProvider
        repo = getattr(self._store, "repo", None)
        fx = FindataFxProvider(market_data=repo)
        as_of_date = pd.Timestamp(date_str).date() if date_str else date.today()

        # 1. Repository lookup
        rate = fx.get_rate(from_currency, to_currency, as_of=as_of_date)
        if rate is not None and rate > 0:
            return rate

        # 2. Fall back to OptiFolio's hardcoded table (lazy import)
        try_live = mode in ("live", "tolerant")
        from src.core.valuation import FxRateProvider
        ofx = FxRateProvider()
        return ofx.get_rate(from_currency, to_currency, try_live=try_live)

    def observations(self, series_ids: List[str], start: str = None, end: str = None,
                     known_at: str = None) -> pd.DataFrame:
        """Canonical non-price observations for macro/rate/index/signal series."""
        repo = getattr(self._store, "repo", None)
        if repo is None or not hasattr(repo, "get_observations"):
            return pd.DataFrame()
        return repo.get_observations(series_ids, start=start, end=end, known_at=known_at)

    def latest_observation(self, series_id: str, as_of: str = None,
                           known_at: str = None) -> Optional[Dict[str, Any]]:
        """Latest usable observation for one non-price series."""
        repo = getattr(self._store, "repo", None)
        if repo is None or not hasattr(repo, "latest_observation"):
            return None
        as_of_date = pd.Timestamp(as_of).date() if as_of else None
        row = repo.latest_observation(series_id, as_of=as_of_date, known_at=known_at)
        if row is None:
            return None
        return self._observation_record(row)

    def observation_series(self) -> pd.DataFrame:
        """Stored observation series summary."""
        repo = getattr(self._store, "repo", None)
        if repo is None or not hasattr(repo, "list_observation_series"):
            return pd.DataFrame()
        return repo.list_observation_series()

    def observation_coverage(self, series_ids: List[str] = None,
                             expected_stale_days: int = None,
                             as_of: str = None) -> pd.DataFrame:
        """Coverage/staleness summary for non-price observations."""
        repo = getattr(self._store, "repo", None)
        if repo is None or not hasattr(repo, "observation_coverage"):
            return pd.DataFrame()
        return repo.observation_coverage(
            series_ids=series_ids,
            expected_stale_days=expected_stale_days,
            as_of=as_of,
        )

    @staticmethod
    def _observation_record(row: Dict[str, Any]) -> Dict[str, Any]:
        record = dict(row)
        for key in ("effective_date", "known_at", "released_at", "observed_at"):
            value = record.get(key)
            if pd.isna(value):
                record[key] = None
            elif key == "effective_date":
                record[key] = pd.Timestamp(value).date().isoformat()
            else:
                record[key] = pd.Timestamp(value).isoformat()
        if record.get("value") is not None:
            record["value"] = float(record["value"])
        return record

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
        if len(prices) < 10:
            return 0.0
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
        """Trigger live refresh via orchestrator for the given symbols.

        Schedules and dispatches only the requested symbols (ignoring
        cadence — the caller explicitly asked for live data).  Falls
        back silently when the orchestrator or any fetcher fails.
        """
        try:
            from FinData.orchestration.orchestrator import Orchestrator

            orch = Orchestrator(store=self._store)
            tasks = orch.schedule(asset_ids=list(symbols))
            if tasks:
                orch.dispatch(tasks)
        except Exception:
            import warnings
            warnings.warn(
                f"Live refresh failed for {symbols} — using cached data",
                stacklevel=2,
            )
