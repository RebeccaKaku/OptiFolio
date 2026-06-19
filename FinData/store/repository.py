"""CanonicalStore — wraps MarketDataRepository with QualityGate for validated storage."""

from __future__ import annotations

import logging
from typing import Optional, Sequence

import pandas as pd

_log = logging.getLogger(__name__)

from findata.store.market_repo import MarketDataRepository

from .quality import QualityGate, QualityReport


class CanonicalStore:
    """Validated market data storage layer.

    Every incoming DataFrame passes through the QualityGate before
    being normalized and persisted. Rejected data never touches storage.

    Delegates read operations (get_prices, get_returns, list_assets,
    missing_report) directly to MarketDataRepository.
    """

    def __init__(self, root_dir: str | None = None) -> None:
        self.repo = MarketDataRepository(root_dir)
        self.gate = QualityGate(repository=self.repo)

    def accept(
        self,
        df: pd.DataFrame,
        asset_id: str,
        source: str,
        currency: str | None = None,
        timezone: str | None = None,
    ) -> QualityReport:
        """Run quality checks; if passed, normalize and save.

        Args:
            df: Raw provider DataFrame.
            asset_id: Asset identifier (e.g. 'AAPL').
            source: Data source label (e.g. 'yahoo', 'akshare').
            currency: ISO 4217 currency code.
            timezone: IANA timezone for the exchange.

        Returns:
            QualityReport with inspection results.
        """
        # 1. Load existing data for this asset
        existing = self._load_existing(asset_id)

        # 2. Run quality gate
        report = self.gate.inspect(df, existing)

        # 3. If passed, normalize and save
        if report.passed:
            self.repo.save_canonical(
                df,
                asset_id=asset_id,
                source=source,
                currency=currency,
                timezone=timezone,
            )

        return report

    def reject(self, asset_id: str, reason: str) -> None:
        """Log rejection — does NOT write data."""
        _log.warning(f"[FinData] REJECTED {asset_id}: {reason}")

    def _load_existing(self, asset_id: str) -> Optional[pd.DataFrame]:
        """Load previously stored data for an asset, or None if unavailable."""
        try:
            prices = self.repo.get_prices([asset_id])
            return prices if not prices.empty else None
        except Exception:
            return None

    # ── Delegates to MarketDataRepository ───────────────────────────

    @staticmethod
    def _normalize_asset(asset_id: str) -> list[str]:
        """Return candidate forms for *asset_id* (bare + prefixed).

        CN stock symbols may be stored bare (600519) or prefixed (sh600519).
        Try both so lookups don't fail on format mismatches.
        """
        from optifolio_contracts.symbols import normalize_cn_symbol

        return normalize_cn_symbol(asset_id)

    def get_prices(
        self,
        assets: Sequence[str],
        start: str | None = None,
        end: str | None = None,
        fields: Sequence[str] = ("adj_close",),
    ) -> pd.DataFrame:
        """Return price matrix with symbol-normalized lookup."""
        # First try with original symbols
        result = self.repo.get_prices(assets, start=start, end=end, fields=fields)
        # For any missing columns, try normalized forms
        existing = set(result.columns)
        missing = [a for a in assets if a not in existing]
        if missing:
            # Build mapping: normalized form → original asset_id
            norm_map: dict[str, str] = {}
            for a in missing:
                for candidate in self._normalize_asset(a):
                    if candidate != a:
                        norm_map[candidate] = a
            if norm_map:
                extra = self.repo.get_prices(list(norm_map.keys()), start=start, end=end, fields=fields)
                for col in extra.columns:
                    if col in norm_map and norm_map[col] not in result.columns:
                        result[norm_map[col]] = extra[col]
        return result

    def get_returns(
        self,
        assets: Sequence[str],
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Return daily return matrix with symbol-normalized lookup."""
        result = self.repo.get_returns(assets, start=start, end=end)
        existing = set(result.columns)
        missing = [a for a in assets if a not in existing]
        if missing:
            norm_map: dict[str, str] = {}
            for a in missing:
                for candidate in self._normalize_asset(a):
                    if candidate != a:
                        norm_map[candidate] = a
            if norm_map:
                extra = self.repo.get_returns(list(norm_map.keys()), start=start, end=end)
                for col in extra.columns:
                    if col in norm_map and norm_map[col] not in result.columns:
                        result[norm_map[col]] = extra[col]
        return result

    def list_assets(self) -> list[str]:
        """Return all asset IDs currently stored."""
        return self.repo.list_assets()

    def missing_report(
        self,
        assets: Sequence[str],
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Return a DataFrame summarizing data completeness per asset."""
        return self.repo.missing_report(assets, start=start, end=end)
