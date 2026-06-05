"""Dividend detection service.

Scans akshare's stock_fhps_em for dividend/split events that match
the portfolio's A-share holdings, and generates CorporateAction records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from src.core.corporate_actions import CorporateActionProcessor
from src.domain.corporate_actions import CorporateAction


@dataclass
class DividendEvent:
    """Parsed dividend/split event from akshare."""

    stock_code: str
    stock_name: str
    report_date: date          # 预案公告日
    ex_rights_date: Optional[date]  # 除权除息日
    record_date: Optional[date]     # 股权登记日
    cash_per_10: float = 0.0   # 每10股现金分红
    stock_div_per_10: float = 0.0   # 每10股送股
    transfer_per_10: float = 0.0    # 每10股转增
    dividend_yield: float = 0.0     # 股息率
    progress: str = ""          # 进度: 实施分配/董事会预案/股东大会通过
    eps: float = 0.0
    nav_per_share: float = 0.0

    @property
    def total_stock_per_10(self) -> float:
        """Total stock distribution per 10 shares (送股 + 转增)."""
        return self.stock_div_per_10 + self.transfer_per_10

    @property
    def is_implemented(self) -> bool:
        return "实施" in self.progress

    def to_corporate_action(self) -> Optional[CorporateAction]:
        """Convert to a DividendAction if this is a dividend event."""
        if not self.is_implemented:
            return None
        if not self.ex_rights_date:
            return None

        from src.domain.corporate_actions import DividendAction, StockSplitAction

        # Stock dividend / transfer = similar to a split
        if self.total_stock_per_10 > 0:
            # ratio: 10 → 10 + total_stock_per_10
            ratio = (10 + self.total_stock_per_10) / 10.0
            return StockSplitAction(
                asset_id=self.stock_code,
                ex_date=self.ex_rights_date,
                effective_date=self.ex_rights_date,
                split_ratio=ratio,
            )

        # Cash dividend
        if self.cash_per_10 > 0:
            dividend_per_share = self.cash_per_10 / 10.0
            return DividendAction(
                asset_id=self.stock_code,
                ex_date=self.ex_rights_date,
                effective_date=self.ex_rights_date,
                dividend_per_share=dividend_per_share,
                dividend_currency="CNY",
                withholding_tax_rate=0.0,  # 分红税由 FeeRule 处理
            )

        return None


class DividendDetectionService:
    """Scans akshare for dividend events matching portfolio holdings."""

    def __init__(self, processor: Optional[CorporateActionProcessor] = None):
        self.processor = processor or CorporateActionProcessor()

    def scan_year(self, report_year: int = 2025) -> List[DividendEvent]:
        """Scan all A-share dividend events for a given report year.

        Args:
            report_year: The fiscal year to scan (e.g. 2025 for FY2025 dividends).

        Returns:
            List of all DividendEvent objects found.
        """
        import akshare as ak

        date_str = f"{report_year}1231"
        try:
            df = ak.stock_fhps_em(date=date_str)
        except Exception:
            return []

        events: List[DividendEvent] = []
        for _, row in df.iterrows():
            try:
                event = self._parse_row(row)
                if event:
                    events.append(event)
            except Exception:
                continue

        return events

    def detect_for_portfolio(
        self,
        holdings: Dict[str, float],
        report_year: int = 2025,
    ) -> List[DividendEvent]:
        """Scan and filter for events matching current portfolio holdings.

        Only returns events that:
        - Match a holding in the portfolio
        - Are in '实施分配' status
        - Have a valid ex_rights_date
        """
        all_events = self.scan_year(report_year)
        portfolio_codes = set(holdings.keys())

        matched = [
            e for e in all_events
            if e.stock_code in portfolio_codes
            and e.is_implemented
            and e.ex_rights_date is not None
        ]
        return matched

    def auto_record(self, holdings: Dict[str, float], report_year: int = 2025) -> int:
        """Detect and automatically record dividend events.

        Returns the number of new events recorded.
        """
        events = self.detect_for_portfolio(holdings, report_year)
        recorded = 0
        for event in events:
            action = event.to_corporate_action()
            if action is None:
                continue

            # Check if already recorded
            existing = self.processor.get_actions(
                asset_id=event.stock_code,
                from_date=event.ex_rights_date,
                to_date=event.ex_rights_date,
            )
            # Simple dedup: skip if any action exists on the same date for this asset
            if existing:
                continue

            # Record the action
            if event.cash_per_10 > 0 and event.total_stock_per_10 == 0:
                self.processor.record_dividend(
                    asset_id=event.stock_code,
                    ex_date=event.ex_rights_date,
                    amount_per_share=event.cash_per_10 / 10.0,
                    currency="CNY",
                )
            elif event.total_stock_per_10 > 0:
                ratio = (10 + event.total_stock_per_10) / 10.0
                self.processor.record_split(
                    asset_id=event.stock_code,
                    ex_date=event.ex_rights_date,
                    ratio=ratio,
                )
            recorded += 1

        return recorded

    @staticmethod
    def _parse_row(row: pd.Series) -> Optional[DividendEvent]:
        """Parse a single row from stock_fhps_em into a DividendEvent."""
        code = str(row.get("代码", ""))
        if not code:
            return None

        ex_date = DividendDetectionService._parse_date(row.get("除权除息日"))
        record_date = DividendDetectionService._parse_date(row.get("股权登记日"))

        return DividendEvent(
            stock_code=code,
            stock_name=str(row.get("名称", "")),
            report_date=DividendDetectionService._parse_date(row.get("预案公告日")) or date.today(),
            ex_rights_date=ex_date,
            record_date=record_date,
            cash_per_10=float(row.get("现金分红-现金分红比例", 0) or 0),
            stock_div_per_10=float(row.get("送转股份-送股比例", 0) or 0),
            transfer_per_10=float(row.get("送转股份-转股比例", 0) or 0),
            dividend_yield=float(row.get("现金分红-股息率", 0) or 0),
            progress=str(row.get("进度", "")),
            eps=float(row.get("每股收益", 0) or 0),
            nav_per_share=float(row.get("每股净资产", 0) or 0),
        )

    @staticmethod
    def _parse_date(val: Any) -> Optional[date]:
        if val is None:
            return None
        if isinstance(val, date):
            return val
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, pd.Timestamp):
            if pd.isna(val):
                return None
            return val.date()
        return None
