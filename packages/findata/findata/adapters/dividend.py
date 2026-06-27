"""CN A-share dividend fetcher — akshare stock_fhps_em."""

import time
import logging
from datetime import date
from typing import Any, Dict, List, Optional

import akshare as ak
import pandas as pd

from . import FetcherProtocol, FetchResult

_log = logging.getLogger(__name__)


class DividendFetcher(FetcherProtocol):
    """Fetches dividend/split distribution events for CN A-share stocks.

    Uses akshare's ``stock_fhps_em`` (EastMoney dividend distribution plans).
    Returns a DataFrame with parsed dividend fields per stock per year.
    """

    PROVIDER = "akshare-cn-dividend"

    def fetch(self, symbol: str, start_date: str, end_date: str, **kwargs) -> FetchResult:
        t0 = time.time()
        try:
            report_year = kwargs.get("report_year", str(date.today().year))
            df = self._fetch_dividends(report_year)
            if df.empty:
                return FetchResult(
                    symbol=symbol, provider=self.PROVIDER, data=pd.DataFrame(),
                    success=True, latency_ms=(time.time() - t0) * 1000,
                )
            return FetchResult(
                symbol=symbol, provider=self.PROVIDER, data=df,
                success=True, latency_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            return FetchResult(
                symbol=symbol, provider=self.PROVIDER, data=None,
                success=False, latency_ms=(time.time() - t0) * 1000,
                errors=[str(e)],
            )

    def _fetch_dividends(self, report_year: str) -> pd.DataFrame:
        date_str = report_year.replace("-", "") + "31" if len(report_year) == 4 else report_year
        try:
            df = ak.stock_fhps_em(date=date_str)
            if df.empty:
                return pd.DataFrame()
            df = self._standardize_columns(df)
            return df
        except Exception as exc:
            _log.warning("stock_fhps_em fetch failed for year %s: %s", report_year, exc)
            return pd.DataFrame()

    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        col_map = {
            "代码": "stock_code",
            "名称": "stock_name",
            "送转股份-送转总比例": "total_stock_div_per_10",
            "送转股份-送股比例": "stock_div_per_10",
            "送转股份-转增比例": "transfer_per_10",
            "现金分红-现金分红比例": "cash_per_10",
            "现金分红-股息率": "dividend_yield",
            "每股收益": "eps",
            "每股净资产": "nav_per_share",
            "每股公积金": "capital_reserve_per_share",
            "预案公告日": "report_date",
            "股权登记日": "record_date",
            "除权除息日": "ex_rights_date",
            "红利发放日": "payment_date",
            "进度": "progress",
            "最新公告日期": "latest_announce_date",
        }
        rename = {k: v for k, v in col_map.items() if k in df.columns}
        df = df.rename(columns=rename)
        return df

    def get_dividends_for_year(self, report_year: int = 2025) -> List[Dict[str, Any]]:
        """Return parsed dividend events for a given fiscal year.

        Convenience method for the dividend service.
        """
        df = self._fetch_dividends(str(report_year))
        if df.empty:
            return []
        results = []
        for _, row in df.iterrows():
            code = str(row.get("stock_code", ""))
            if not code:
                continue
            ex_date = self._parse_date(row.get("ex_rights_date"))
            record_date = self._parse_date(row.get("record_date"))
            report_date = self._parse_date(row.get("report_date"))
            results.append({
                "stock_code": code,
                "stock_name": str(row.get("stock_name", "")),
                "report_date": report_date or date.today(),
                "ex_rights_date": ex_date,
                "record_date": record_date,
                "cash_per_10": float(row.get("cash_per_10", 0) or 0),
                "stock_div_per_10": float(row.get("stock_div_per_10", 0) or 0),
                "transfer_per_10": float(row.get("transfer_per_10", 0) or 0),
                "dividend_yield": float(row.get("dividend_yield", 0) or 0),
                "progress": str(row.get("progress", "")),
                "eps": float(row.get("eps", 0) or 0),
                "nav_per_share": float(row.get("nav_per_share", 0) or 0),
            })
        return results

    @staticmethod
    def _parse_date(val: Any) -> Optional[date]:
        if val is None:
            return None
        if isinstance(val, date):
            return val
        if isinstance(val, pd.Timestamp):
            if pd.isna(val):
                return None
            return val.date()
        if isinstance(val, str):
            try:
                return date.fromisoformat(val)
            except (ValueError, TypeError):
                return None
        return None
