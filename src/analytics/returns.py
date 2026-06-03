"""FX return decomposition — split base-currency returns into local-asset + FX components.

Formula::

    (1 + r_base) = (1 + r_local) × (1 + r_fx)
    r_base = r_local + r_fx + r_local × r_fx

where:

- r_base  = total return measured in the portfolio's base (reporting) currency
- r_local = return of the underlying asset measured in its local currency
- r_fx    = return of the FX rate (base per local) over the same period
- interaction = r_local × r_fx  (cross term, typically small)

This decomposition is useful for understanding how much of a portfolio's
performance comes from asset selection vs. currency movements.

For multi-currency portfolios the module uses a **value-weighted effective
FX rate** so the multiplicative identity holds exactly for the aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# ── Standard columns from PortfolioHistoryTracker, not currency columns ──────
_STANDARD_COLS = frozenset({
    "date", "total_value", "holdings_value", "cash_value",
    "base_currency", "num_positions",
})


@dataclass(frozen=True)
class FxDecomposition:
    """Decomposition of a single-period return into local + FX components.

    Attributes:
        period_start: Start date of the period.
        period_end: End date of the period.
        base_return: Total return in base currency (decimal, e.g. 0.05 = 5%).
        local_return: Return in local currency (asset-only, no FX effect).
        fx_return: FX contribution (currency movement only).
        interaction: Cross term r_local × r_fx.
        base_currency: The reporting currency (e.g. "CNY").
    """

    period_start: date
    period_end: date
    base_return: float
    local_return: float
    fx_return: float
    interaction: float
    base_currency: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "base_return": round(self.base_return, 6),
            "local_return": round(self.local_return, 6),
            "fx_return": round(self.fx_return, 6),
            "interaction": round(self.interaction, 6),
            "base_currency": self.base_currency,
        }


class ReturnAnalyzer:
    """Compute portfolio returns with optional FX decomposition.

    Usage::

        analyzer = ReturnAnalyzer()

        # 1) Single-period decomposition for one currency slice
        decomp = analyzer.decompose_fx(
            start_value=100_000, end_value=105_000,
            start_fx=7.20, end_fx=7.00,
            period_start=date(2025, 1, 1), period_end=date(2025, 1, 31),
            base_currency="CNY",
        )

        # 2) Multi-period, multi-currency returns from an equity curve
        returns_df = analyzer.compute_returns(
            equity_curve=history_df,
            fx_rates={"USD": usd_cny_series, "EUR": eur_cny_series},
        )
    """

    # ── single-period decomposition ─────────────────────────────────────

    @staticmethod
    def decompose_fx(
        start_value: float,
        end_value: float,
        start_fx: float,
        end_fx: float,
        period_start: date,
        period_end: date,
        base_currency: str = "CNY",
    ) -> FxDecomposition:
        """Decompose a single-period base-currency return into local + FX.

        Args:
            start_value: Portfolio (or slice) value in **base** currency at start.
            end_value: Portfolio (or slice) value in **base** currency at end.
            start_fx: FX rate (base per local) at period start.
            end_fx: FX rate (base per local) at period end.
            period_start: Start date.
            period_end: End date.
            base_currency: Reporting currency code.

        Returns:
            FxDecomposition with base, local, FX, and interaction returns.

        Raises:
            ValueError: If ``start_value`` or ``start_fx`` is non-positive.

        Formula
        -------
        Let ``V`` be value in base currency, ``F`` be the FX rate (base/local)::

            local_value = V / F                    # value in local currency
            r_base  = V_end / V_start - 1
            r_local = local_end / local_start - 1
            r_fx    = F_end / F_start - 1
            interaction = r_local × r_fx

            r_base = r_local + r_fx + interaction   (identity)
            (1+r_base) = (1+r_local) × (1+r_fx)
        """
        if start_value <= 0:
            raise ValueError(
                f"start_value must be positive, got {start_value}"
            )
        if start_fx <= 0:
            raise ValueError(
                f"start_fx must be positive, got {start_fx}"
            )

        # Base-currency return
        base_return = end_value / start_value - 1.0

        # Local-currency return — strip out the FX
        start_local = start_value / start_fx
        end_local = end_value / end_fx
        local_return = end_local / start_local - 1.0

        # FX return
        fx_return = end_fx / start_fx - 1.0

        # Interaction (cross) term
        interaction = local_return * fx_return

        return FxDecomposition(
            period_start=period_start,
            period_end=period_end,
            base_return=base_return,
            local_return=local_return,
            fx_return=fx_return,
            interaction=interaction,
            base_currency=base_currency,
        )

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _compute_effective_fx(
        df: pd.DataFrame,
        fx_rates: Dict[str, pd.Series],
        currency_cols: List[str],
        start_total: float,
        t0: pd.Timestamp,
        t1: pd.Timestamp,
    ) -> tuple[float, float] | None:
        """Compute value-weighted effective FX rates for a period.

        Returns ``(start_fx, end_fx)`` or ``None`` if no usable data.
        """
        weighted_start_fx = 0.0
        weighted_end_fx = 0.0
        total_weight = 0.0

        for cur in currency_cols:
            if cur not in fx_rates:
                continue
            fx_series = fx_rates[cur]

            try:
                if t0 not in fx_series.index or t1 not in fx_series.index:
                    continue
                fx0 = float(fx_series.loc[t0])
                fx1 = float(fx_series.loc[t1])
            except (KeyError, TypeError):
                continue

            if fx0 <= 0:
                continue

            val0 = df.loc[t0, cur]
            if pd.isna(val0):
                continue
            val0_base = float(val0)

            if val0_base <= 0:
                continue

            weight = val0_base / start_total
            total_weight += weight
            weighted_start_fx += weight * fx0
            weighted_end_fx += weight * fx1

        if total_weight > 0:
            return (weighted_start_fx / total_weight,
                    weighted_end_fx / total_weight)
        return None

    # ── multi-period returns ────────────────────────────────────────────

    @staticmethod
    def compute_returns(
        equity_curve: pd.DataFrame,
        fx_rates: Optional[Dict[str, pd.Series]] = None,
        base_currency: str = "CNY",
        period: str = "D",
    ) -> pd.DataFrame:
        """Compute periodic returns from an equity curve, optionally with FX breakdown.

        The equity curve must contain at minimum a ``total_value`` column and
        date information (either a ``date`` column or a DatetimeIndex).

        If the equity curve contains per-currency value columns (any column
        named with a 3-letter currency code like ``USD``, ``EUR``) **and**
        ``fx_rates`` is provided for those currencies, the method computes
        a value-weighted effective FX rate and uses it to decompose each
        period's return via :meth:`decompose_fx`.  This guarantees the
        multiplicative identity holds exactly.

        Args:
            equity_curve: DataFrame with date index (or ``date`` column) and
                at minimum a ``total_value`` column in base currency.
                Optional per-currency value columns (e.g. ``USD``, ``EUR``)
                should contain values already converted to base currency.
            fx_rates: Dict mapping currency code to ``pd.Series`` of FX rates
                (base per local, e.g. CNY/USD). Each series is indexed by date.
                If ``None`` or empty, ``local_return = base_return`` and
                ``fx_return = 0``.
            base_currency: Reporting currency code (default ``"CNY"``).
            period: Resampling label for returns — ``"D"`` (daily, default),
                ``"W"`` (weekly), ``"M"`` (monthly), ``"Q"`` (quarterly),
                ``"Y"`` (yearly).  Only applied when the index is DatetimeIndex.

        Returns:
            DataFrame with columns: ``date``, ``base_return``, ``local_return``,
            ``fx_return``, ``interaction``.  Returns are in decimal form
            (0.05 = 5%).

        Raises:
            ValueError: If ``equity_curve`` is missing a ``total_value`` column.
        """
        empty_result = pd.DataFrame(columns=[
            "date", "base_return", "local_return", "fx_return", "interaction",
        ])

        if equity_curve.empty:
            return empty_result

        df = equity_curve.copy()

        # Normalise date handling
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
            df.index.name = "date"

        if df.empty:
            return empty_result

        # Validate required column early (before length check)
        if "total_value" not in df.columns:
            raise ValueError(
                "equity_curve must contain a 'total_value' column"
            )

        # Resample if requested
        if period != "D":
            df = df.resample(period).last().dropna(how="all")

        if len(df) < 2:
            return empty_result

        # Detect per-currency value columns
        currency_cols = [
            c for c in df.columns if c not in _STANDARD_COLS
        ]
        has_fx_data = bool(fx_rates and currency_cols)

        result_rows: List[Dict[str, Any]] = []
        dates = df.index

        for i in range(1, len(dates)):
            t0, t1 = dates[i - 1], dates[i]
            row: Dict[str, Any] = {"date": t1}

            start_total = float(df.loc[t0, "total_value"])
            end_total = float(df.loc[t1, "total_value"])

            if start_total <= 0 or pd.isna(start_total) or pd.isna(end_total):
                row.update({
                    "base_return": np.nan,
                    "local_return": np.nan,
                    "fx_return": np.nan,
                    "interaction": np.nan,
                })
                result_rows.append(row)
                continue

            base_return = end_total / start_total - 1.0
            row["base_return"] = base_return

            if has_fx_data:
                effective = ReturnAnalyzer._compute_effective_fx(
                    df, fx_rates, currency_cols, start_total, t0, t1,  # type: ignore[arg-type]
                )
                if effective is not None:
                    start_fx, end_fx = effective
                    start_local = start_total / start_fx
                    end_local = end_total / end_fx
                    local_return = end_local / start_local - 1.0
                    fx_return = end_fx / start_fx - 1.0
                    interaction = local_return * fx_return
                else:
                    local_return = base_return
                    fx_return = 0.0
                    interaction = 0.0
            else:
                # No currency breakdown — treat as single-currency
                local_return = base_return
                fx_return = 0.0
                interaction = 0.0

            row["local_return"] = local_return
            row["fx_return"] = fx_return
            row["interaction"] = interaction
            result_rows.append(row)

        result = pd.DataFrame(result_rows)
        if not result.empty:
            result["date"] = pd.to_datetime(result["date"])
        return result

    # ── aggregate decomposition ─────────────────────────────────────────

    @staticmethod
    def decompose_period(
        equity_curve: pd.DataFrame,
        fx_rates: Dict[str, pd.Series],
        period_start: date,
        period_end: date,
        base_currency: str = "CNY",
    ) -> FxDecomposition:
        """Convenience: total-return decomposition for a single date range.

        Looks up the equity curve values at ``period_start`` and ``period_end``
        and computes the decomposition using the value-weighted effective
        FX rate (if per-currency columns and FX rates are available).

        When the exact dates are not present in the equity curve the nearest
        available dates are used (backward for start, forward for end).

        Args:
            equity_curve: Same format as for :meth:`compute_returns`.
            fx_rates: Dict mapping currency to FX rate series.
            period_start: Start date.
            period_end: End date.
            base_currency: Reporting currency code.

        Returns:
            FxDecomposition for the full period.
        """
        df = equity_curve.copy()
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")

        t0 = pd.Timestamp(period_start)
        t1 = pd.Timestamp(period_end)
        available = df.index.sort_values()

        # Snap start: latest date <= period_start; fallback to earliest
        earlier = available[available <= t0]
        if len(earlier) > 0:
            t0 = earlier[-1]
        else:
            t0 = available[0]

        # Snap end: earliest date >= period_end; fallback to latest
        later = available[available >= t1]
        if len(later) > 0:
            t1 = later[0]
        else:
            t1 = available[-1]

        start_total = float(df.loc[t0, "total_value"])
        end_total = float(df.loc[t1, "total_value"])

        # Detect currency columns and compute weighted FX
        currency_cols = [c for c in df.columns if c not in _STANDARD_COLS]

        if currency_cols and fx_rates:
            effective = ReturnAnalyzer._compute_effective_fx(
                df, fx_rates, currency_cols, start_total, t0, t1,
            )
            if effective is not None:
                start_fx, end_fx = effective
            else:
                start_fx = 1.0
                end_fx = 1.0
        else:
            start_fx = 1.0
            end_fx = 1.0

        return ReturnAnalyzer.decompose_fx(
            start_value=start_total,
            end_value=end_total,
            start_fx=start_fx,
            end_fx=end_fx,
            period_start=t0.date(),
            period_end=t1.date(),
            base_currency=base_currency,
        )
