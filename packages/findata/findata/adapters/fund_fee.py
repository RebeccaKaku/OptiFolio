"""CN fund fee and status fetcher — akshare Xueqiu + EastMoney."""

import time
import logging
from datetime import date
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd

from . import FetcherProtocol, FetchResult

_log = logging.getLogger(__name__)


class FundFeeFetcher(FetcherProtocol):
    """Fetches fund fee structure and subscription/redemption status.

    Uses two akshare APIs:
    - fund_individual_detail_info_xq: Xueqiu fund detail (fees)
    - fund_purchase_em: EastMoney fund subscription status
    """

    PROVIDER = "akshare-cn-fund-fees"

    def fetch(self, symbol: str, start_date: str, end_date: str, **kwargs) -> FetchResult:
        t0 = time.time()
        try:
            fees = self.get_fees(symbol)
            status = self.get_status(symbol)
            result = {"fees": fees, "status": status}
            return FetchResult(
                symbol=symbol, provider=self.PROVIDER, data=result,
                success=True, latency_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            return FetchResult(
                symbol=symbol, provider=self.PROVIDER, data=None,
                success=False, latency_ms=(time.time() - t0) * 1000,
                errors=[str(e)],
            )

    def get_fees(self, fund_code: str) -> Dict[str, Any]:
        """Return fee structure for a fund from Xueqiu (akshare)."""
        try:
            df = ak.fund_individual_detail_info_xq(symbol=fund_code)
            if df.empty:
                return self._empty_fees(fund_code)

            management_fee = 0.0
            custody_fee = 0.0
            sales_service_fee = 0.0
            subscription_tiers = []
            redemption_tiers = []

            fee_col = "费用"
            condition_col = "费用条件"
            type_col = "费用类型"

            for _, row in df.iterrows():
                fee_type = str(row.get(type_col, ""))
                condition = str(row.get(condition_col, ""))
                rate = str(row.get(fee_col, ""))

                if "管理" in fee_type:
                    management_fee = self._parse_rate(rate)
                elif "托管" in fee_type:
                    custody_fee = self._parse_rate(rate)
                elif "销售服务" in fee_type:
                    sales_service_fee = self._parse_rate(rate)
                elif "申购" in fee_type:
                    subscription_tiers.append({
                        "condition": condition,
                        "rate": rate,
                    })
                elif "赎回" in fee_type:
                    redemption_tiers.append({
                        "condition": condition,
                        "rate": rate,
                    })

            return {
                "fund_code": fund_code,
                "management_fee": management_fee,
                "custody_fee": custody_fee,
                "sales_service_fee": sales_service_fee,
                "subscription_tiers": subscription_tiers,
                "redemption_tiers": redemption_tiers,
                "total_annual_fee": round(management_fee + custody_fee + sales_service_fee, 6),
            }
        except Exception as exc:
            _log.debug("Failed to fetch fees for fund %s: %s", fund_code, exc)
            return self._empty_fees(fund_code)

    def get_status(self, fund_code: str) -> Dict[str, Any]:
        """Return subscription/redemption status from EastMoney."""
        try:
            df = ak.fund_purchase_em()
            if df.empty:
                return self._empty_status(fund_code)

            col_code = "基金代码"
            row = df[df[col_code] == fund_code]
            if row.empty:
                return self._empty_status(fund_code)

            r = row.iloc[0]
            purchase_status = str(r.get("申购状态", ""))
            redeem_status = str(r.get("赎回状态", ""))
            next_open = r.get("下一开放日")

            return {
                "fund_code": fund_code,
                "fund_name": str(r.get("基金简称", "")),
                "fund_type": str(r.get("基金类型", "")),
                "nav": float(r.get("最新净值/万份收益", 0) or 0),
                "nav_date": str(r.get("最新净值/万份收益-公布时间", "")),
                "can_buy": "开放" in purchase_status,
                "can_sell": "开放" in redeem_status,
                "next_open_date": pd.Timestamp(next_open).date().isoformat() if pd.notna(next_open) else None,
                "min_purchase_amount": float(r.get("赒购金额", 0) or 0),
                "daily_limit": float(r.get("单日累计申购限额", 0) or float("inf")),
                "purchase_fee_rate": float(r.get("手续费", 0) or 0),
            }
        except Exception as exc:
            _log.debug("Failed to fetch status for fund %s: %s", fund_code, exc)
            return self._empty_status(fund_code)

    def get_all_status(self) -> pd.DataFrame:
        """Return the full fund subscription status table."""
        try:
            return ak.fund_purchase_em()
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def _parse_rate(rate_str: str) -> float:
        s = str(rate_str).replace("%", "").strip()
        try:
            v = float(s)
            return v / 100.0
        except ValueError:
            return 0.0

    @staticmethod
    def _empty_fees(fund_code: str) -> Dict[str, Any]:
        return {
            "fund_code": fund_code,
            "management_fee": 0.0,
            "custody_fee": 0.0,
            "sales_service_fee": 0.0,
            "subscription_tiers": [],
            "redemption_tiers": [],
            "total_annual_fee": 0.0,
        }

    @staticmethod
    def _empty_status(fund_code: str) -> Dict[str, Any]:
        return {
            "fund_code": fund_code,
            "can_buy": True,
            "can_sell": True,
        }
