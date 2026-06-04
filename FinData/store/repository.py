"""CanonicalStore — wraps MarketDataRepository with QualityGate for validated storage."""

from __future__ import annotations

import logging
from typing import Optional, Sequence

import pandas as pd

_log = logging.getLogger(__name__)

from src.data_foundation import MarketDataRepository

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
        self.gate = QualityGate()

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
            self.repo.save_raw(
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

    def get_prices(
        self,
        assets: Sequence[str],
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Return price matrix (date x asset_id) from canonical storage."""
        return self.repo.get_prices(assets, start=start, end=end)

    def get_returns(
        self,
        assets: Sequence[str],
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Return daily return matrix from canonical storage."""
        return self.repo.get_returns(assets, start=start, end=end)

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
