"""CN A-share stock fetcher using akshare (EastMoney → Sina → Tencent fallback)."""

import re
import time
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

from optifolio_contracts.identifiers import normalize_instrument_id

from . import FetcherProtocol, FetchResult


class CnStockFetcher(FetcherProtocol):
    """CN A-share data fetcher with multi-source fallback cascade.

    Supports prefixed symbols (sh600519, sz000001) and bare 6-digit codes.
    Returns OHLCV data via EastMoney → Sina → Tencent fallback chain.
    """

    PROVIDER = "akshare-cn-stock"

    # ── FetcherProtocol ──────────────────────────────────────────────────

    def fetch(self, symbol: str, start_date: str, end_date: str, **kwargs) -> FetchResult:
        t0 = time.time()
        try:
            # Normalize to canonical instrument ID (equity.cn.<exchange>.<code>)
            code, full = self._parse_symbol(symbol)
            canonical = normalize_instrument_id(full, asset_type="cn_stock")
            period = kwargs.get("period", "daily")
            adjust = kwargs.get("adjust", "qfq")
            df = self._fetch_raw(symbol, start_date, end_date, period, adjust)
            return FetchResult(
                symbol=canonical, provider=self.PROVIDER, data=df,
                success=True, latency_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            return FetchResult(
                symbol=symbol, provider=self.PROVIDER, data=None,
                success=False, latency_ms=(time.time() - t0) * 1000,
                errors=[str(e)],
            )

    # ── Core fetch logic (migrated from src/data_core) ───────────────────

    def _fetch_raw(self, symbol: str, start_date: str, end_date: str,
                   period: str = "daily", adjust: str = "qfq") -> pd.DataFrame:
        code, full_symbol = self._parse_symbol(symbol)

        start_str = start_date.replace("-", "")
        end_str = end_date.replace("-", "")

        # 1. EastMoney (bare numeric code)
        df = self._try_eastmoney(code, start_str, end_str, period, adjust)

        # 2. Sina (prefixed code)
        if len(df) == 0:
            df = self._try_sina(full_symbol, start_str, end_str, period)

        # 3. Tencent (bare numeric code, max 60 days)
        if len(df) == 0:
            df = self._try_tencent(code, start_str, end_str, period)

        # 4. Sina ETF (works around corp firewall DPI blocking EastMoney)
        if len(df) == 0:
            df = self._try_sina_etf(full_symbol, start_date, end_date)

        if len(df) == 0:
            return pd.DataFrame()

        df = self._standardize_columns(df)
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        if not isinstance(df.index, pd.DatetimeIndex):
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date").sort_index()
        return df.loc[start_dt:end_dt]

    def _parse_symbol(self, symbol: str) -> tuple[str, str]:
        from optifolio_contracts.symbols import _infer_exchange_prefix

        symbol = symbol.strip().lower()
        code_match = re.search(r"\d{6}", symbol)
        if not code_match:
            return symbol, symbol
        code = code_match.group(0)
        if symbol.startswith(("sh", "sz")):
            return code, symbol
        prefix = _infer_exchange_prefix(code)
        return code, f"{prefix}{code}"

    @staticmethod
    def _infer_exchange_prefix(code: str) -> str:
        from optifolio_contracts.symbols import _infer_exchange_prefix as _shared_prefix

        return _shared_prefix(code)

    def _try_eastmoney(self, code, start_date, end_date, period, adjust) -> pd.DataFrame:
        try:
            df = ak.stock_zh_a_hist(
                symbol=code, period=period,
                start_date=start_date, end_date=end_date, adjust=adjust,
            )
            if len(df) == 0:
                return pd.DataFrame()
            column_map = {
                "日期": "Date", "开盘": "Open", "收盘": "Close",
                "最高": "High", "最低": "Low", "成交量": "Volume",
                "成交额": "Amount", "振幅": "Amplitude",
                "涨跌幅": "ChangePercent", "涨跌额": "Change",
                "换手率": "Turnover",
            }
            df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date").sort_index()
            return df
        except Exception:
            return pd.DataFrame()

    def _try_sina(self, full_symbol, start_date, end_date, _period) -> pd.DataFrame:
        try:
            df = ak.stock_zh_a_daily(
                symbol=full_symbol, start_date=start_date,
                end_date=end_date, adjust="qfq",
            )
            if len(df) == 0:
                return pd.DataFrame()
            column_map = {
                "date": "Date", "open": "Open", "close": "Close",
                "high": "High", "low": "Low", "volume": "Volume",
            }
            df = df.rename(columns=column_map)
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date").sort_index()
            return df
        except Exception:
            return pd.DataFrame()

    def _try_tencent(self, code, start_date, end_date, period) -> pd.DataFrame:
        try:
            start_dt = datetime.strptime(start_date, "%Y%m%d")
            end_dt = datetime.strptime(end_date, "%Y%m%d")
            if (end_dt - start_dt).days > 60:
                start_dt = end_dt - timedelta(days=60)
                start_date = start_dt.strftime("%Y%m%d")
            df = ak.stock_zh_a_hist_min_em(
                symbol=code, period=period,
                start_date=start_date, end_date=end_date, adjust="qfq",
            )
            if len(df) == 0:
                return pd.DataFrame()
            column_map = {
                "时间": "Date", "开盘": "Open", "收盘": "Close",
                "最高": "High", "最低": "Low", "成交量": "Volume",
            }
            df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date").sort_index()
            return df
        except Exception:
            return pd.DataFrame()

    def _try_sina_etf(self, full_symbol, start_date, end_date) -> pd.DataFrame:
        """Sina ETF daily data — survives corp firewalls that DPI-block EastMoney."""
        try:
            df = ak.fund_etf_hist_sina(symbol=full_symbol)
            if len(df) == 0:
                return pd.DataFrame()
            column_map = {
                "date": "Date", "open": "Open", "close": "Close",
                "high": "High", "low": "Low", "volume": "Volume",
            }
            df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date").sort_index()
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            return df.loc[start_dt:end_dt]
        except Exception:
            return pd.DataFrame()

    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(df.index, pd.DatetimeIndex):
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date").sort_index()
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df.columns:
                df[col] = df.get("Close", pd.NA) if col != "Volume" else 0.0
        available = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        return df[available]

    def get_realtime_quote(self, symbol: str) -> dict:
        code, full_symbol = self._parse_symbol(symbol)
        try:
            df = ak.stock_zh_a_spot_em()
            if len(df) == 0:
                return {}
            stock_data = df[df["代码"] == code]
            if len(stock_data) > 0:
                row = stock_data.iloc[0]
                return {
                    "symbol": full_symbol, "name": row.get("名称", ""),
                    "latest": row.get("最新价", 0), "change": row.get("涨跌额", 0),
                    "change_percent": row.get("涨跌幅", 0), "volume": row.get("成交量", 0),
                    "amount": row.get("成交额", 0), "high": row.get("最高", 0),
                    "low": row.get("最低", 0), "open": row.get("今开", 0),
                    "prev_close": row.get("昨收", 0),
                }
            return {}
        except Exception:
            return {}
