"""Fund friction data service.

Fetches fund fees (subscription/redemption/management/custody) from Xueqiu,
and fund subscription/redemption status from East Money (akshare).

Usage::

    svc = FundFrictionService()
    fees = svc.get_fund_fees("005827")
    # → {"management_fee": 0.012, "custody_fee": 0.002, ...}

    status = svc.get_fund_status("005827")
    # → {"can_buy": True, "can_sell": True, "min_amount": 10.0, ...}
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class FundFeeInfo:
    """Fund fee structure for a single fund."""

    fund_code: str
    fund_name: str = ""
    # Subscription fees (申购费) — tiered by amount
    subscription_tiers: List[Dict[str, Any]] = field(default_factory=list)
    # Redemption fees (赎回费) — tiered by holding days
    redemption_tiers: List[Dict[str, Any]] = field(default_factory=list)
    # Annual fees charged daily from NAV
    management_fee: float = 0.0   # 管理费 (e.g. 0.012 = 1.2%)
    custody_fee: float = 0.0       # 托管费 (e.g. 0.002 = 0.2%)
    sales_service_fee: float = 0.0  # 销售服务费 (C类份额)

    @property
    def total_annual_fee(self) -> float:
        return round(self.management_fee + self.custody_fee + self.sales_service_fee, 6)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fund_code": self.fund_code,
            "fund_name": self.fund_name,
            "subscription_tiers": self.subscription_tiers,
            "redemption_tiers": self.redemption_tiers,
            "management_fee": self.management_fee,
            "custody_fee": self.custody_fee,
            "sales_service_fee": self.sales_service_fee,
            "total_annual_fee": self.total_annual_fee,
        }


@dataclass
class FundStatusInfo:
    """Fund subscription/redemption status."""

    fund_code: str
    fund_name: str = ""
    fund_type: str = ""
    nav: float = 0.0
    nav_date: str = ""
    can_buy: bool = True         # 申购状态: 开放申购
    can_sell: bool = True         # 赎回状态: 开放赎回
    next_open_date: Optional[date] = None  # 下一开放日 (NaT = 每日开放)
    min_purchase_amount: float = 0.0  # 起购金额
    daily_limit: float = float("inf")  # 单日累计申购限额
    purchase_fee_rate: float = 0.0  # 申购手续费率

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fund_code": self.fund_code,
            "fund_name": self.fund_name,
            "fund_type": self.fund_type,
            "nav": self.nav,
            "nav_date": self.nav_date,
            "can_buy": self.can_buy,
            "can_sell": self.can_sell,
            "next_open_date": self.next_open_date.isoformat() if self.next_open_date else None,
            "min_purchase_amount": self.min_purchase_amount,
            "daily_limit": self.daily_limit,
            "purchase_fee_rate": self.purchase_fee_rate,
        }


class FundFrictionService:
    """Fetches fund fees and status via findata facade."""

    def __init__(self, cache_ttl: int = 3600):
        self._cache_ttl = cache_ttl
        self._fee_cache: Dict[str, tuple[float, FundFeeInfo]] = {}
        self._status_df: Optional[pd.DataFrame] = None
        self._status_ts: float = 0.0

    # ── Fund fees (Xueqiu) ─────────────────────────────────────────────

    def get_fund_fees(self, fund_code: str) -> FundFeeInfo:
        """Get fee structure for a fund via findata facade.

        Returns management_fee, custody_fee, and tiered subscription/
        redemption fees.
        """
        now = time.time()
        if fund_code in self._fee_cache:
            ts, info = self._fee_cache[fund_code]
            if now - ts < self._cache_ttl:
                return info

        from findata import fd

        try:
            fees_dict = fd.fund_fees(fund_code)
            info = FundFeeInfo(
                fund_code=fund_code,
                fund_name=fees_dict.get("fund_name", ""),
                subscription_tiers=fees_dict.get("subscription_tiers", []),
                redemption_tiers=fees_dict.get("redemption_tiers", []),
                management_fee=fees_dict.get("management_fee", 0.0),
                custody_fee=fees_dict.get("custody_fee", 0.0),
                sales_service_fee=fees_dict.get("sales_service_fee", 0.0),
            )
        except Exception:
            info = FundFeeInfo(fund_code=fund_code, fund_name="")

        self._fee_cache[fund_code] = (now, info)
        return info

    def get_redemption_fee(self, fund_code: str, holding_days: int) -> float:
        """Get the applicable redemption fee rate for a given holding period."""
        info = self.get_fund_fees(fund_code)
        if not info.redemption_tiers:
            return 0.0

        # Parse tier conditions like "0.0天<持有时间<7.0天"
        # and find the matching tier
        # For now, return the highest rate (conservative)
        for tier in info.redemption_tiers:
            rate_str = tier.get("rate", "0.00%")
            rate = self._parse_pct(rate_str)
            condition = tier.get("condition", "")
            days_match = self._parse_holding_days_range(condition)
            if days_match and days_match[0] <= holding_days < days_match[1]:
                return rate

        return 0.0

    # ── Fund status (East Money) ────────────────────────────────────────

    def _ensure_status_loaded(self):
        """Lazy-load the full fund status table (cached) via findata facade."""
        now = time.time()
        if self._status_df is not None and now - self._status_ts < self._cache_ttl:
            return

        from findata.adapters.fund_fee import FundFeeFetcher

        try:
            fetcher = FundFeeFetcher()
            self._status_df = fetcher.get_all_status()
        except Exception:
            self._status_df = pd.DataFrame()
        self._status_ts = now

    def get_fund_status(self, fund_code: str) -> FundStatusInfo:
        """Get subscription/redemption status for a fund."""
        self._ensure_status_loaded()

        if self._status_df is None:
            return FundStatusInfo(fund_code=fund_code)

        row = self._status_df[self._status_df["基金代码"] == fund_code]
        if row.empty:
            return FundStatusInfo(fund_code=fund_code)

        r = row.iloc[0]
        purchase_status = str(r.get("申购状态", "开放申购"))
        redeem_status = str(r.get("赎回状态", "开放赎回"))
        next_open = r.get("下一开放日")

        return FundStatusInfo(
            fund_code=fund_code,
            fund_name=str(r.get("基金简称", "")),
            fund_type=str(r.get("基金类型", "")),
            nav=float(r.get("最新净值/万份收益", 0) or 0),
            nav_date=str(r.get("最新净值/万份收益-公布时间", "")),
            can_buy="开放" in purchase_status,
            can_sell="开放" in redeem_status,
            next_open_date=pd.Timestamp(next_open).date() if pd.notna(next_open) else None,
            min_purchase_amount=float(r.get("起购金额", 0) or 0),
            daily_limit=float(r.get("单日累计申购限额", float("inf")) or float("inf")),
            purchase_fee_rate=float(r.get("手续费", 0) or 0),
        )

    def get_all_fund_status(self) -> pd.DataFrame:
        """Get the full fund status table."""
        self._ensure_status_loaded()
        return self._status_df if self._status_df is not None else pd.DataFrame()

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_pct(value_str: str, source: str = "xueqiu") -> float:
        """Parse a percentage or numeric string.

        Args:
            value_str: e.g. '1.20', '1.50%', '0.15'.
            source: 'xueqiu' (values are always percentages, e.g. 1.2 = 1.2%)
                    or 'eastmoney' (values may already be decimals, e.g. 0.15 = 0.15%).
        """
        s = str(value_str).replace("%", "").strip()
        try:
            v = float(s)
        except ValueError:
            return 0.0

        if source == "xueqiu":
            # Xueqiu always returns values as percentages
            # 1.2 → 1.2% → 0.012; 0.2 → 0.2% → 0.002
            return v / 100.0
        else:
            # East Money: value already represents percentage points
            # 0.15 → 0.15%; 1.50 → 1.50%
            if v >= 1:
                return v / 100.0
            return v

    @staticmethod
    def _parse_holding_days_range(condition: str) -> Optional[tuple[float, float]]:
        """Parse a holding period condition string.

        e.g. '7.0天<=持有时间<30.0天' → (7.0, 30.0)
        e.g. '2.0年<=持有时间' → (730.0, float('inf'))
        """
        import re
        low = 0.0
        high = float("inf")

        # Match patterns like "7.0天", "2.0年"
        # Lower bound
        low_match = re.search(r"(\d+\.?\d*)(天|年)\s*<=", condition)
        if low_match:
            low = float(low_match.group(1))
            if low_match.group(2) == "年":
                low *= 365

        # Upper bound
        high_match = re.search(r"<\s*(\d+\.?\d*)(天|年)", condition)
        if high_match:
            high = float(high_match.group(1))
            if high_match.group(2) == "年":
                high *= 365

        return (low, high)

    @staticmethod
    def _extract_value(df: pd.DataFrame, item_name: str) -> str:
        """Extract a value from Xueqiu basic info DataFrame."""
        row = df[df["item"] == item_name]
        if row.empty:
            return ""
        return str(row.iloc[0]["value"])
