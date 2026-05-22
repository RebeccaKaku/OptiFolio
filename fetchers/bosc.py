import os
import json
import asyncio
import pandas as pd
import httpx
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from .interfaces import AsyncBaseFetcher

class BoscFetcher(AsyncBaseFetcher):
    """
    Bank of Shanghai (BOSC) Wealth Management Product (理财产品) Fetcher.

    Features:
    - Fetches product list from BOSC's PC API: qryPcFinanceProductZh.
    - Extracts net values and unit rates to create an OHLCV snapshot.
    - Appends daily snapshots to historical files if they exist.
    """

    PRODUCT_LIST_URL = "https://www.bosc.cn/apiQry/apiPCQry/qryPcFinanceProductZh"
    NET_WORTH_URL = "https://ebanks.bankofshanghai.com/pweb/FinanceRateChartQuery.do"

    def __init__(self, data_dir: str = "data/bosc", save_raw: bool = True):
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.save_raw = save_raw

        # Ensure directories exist
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def fetch_all_products(self) -> List[Dict]:
        """
        Query all active wealth management products from BOSC portal across all categories.
        Includes both the generic POST API and the specific GET APIs.
        """
        print("    [BOSC] Discovering all products across categories...")
        get_endpoints = [
            "https://www.bosc.cn/apiQry/apiPCQry/v2/doPcD709QryPage",
            "https://www.bosc.cn/apiQry/apiPCQry/v2/qryMCFinanceNetProHisValueForPersonPage",
            "https://www.bosc.cn/apiQry/apiPCQry/v2/doPcD709CompanyQryPage",
            "https://www.bosc.cn/apiQry/apiPCQry/qryMCFinanceNetProHisValueForCompanyPage"
        ]
        
        all_rows = []
        async with httpx.AsyncClient(verify=False) as client:
            # 1. First fetch using the original comprehensive POST API
            try:
                post_payload = {"current": 1, "size": 1000}
                post_resp = await client.post(self.PRODUCT_LIST_URL, headers=self.headers, json=post_payload, timeout=15)
                post_resp.raise_for_status()
                post_data = post_resp.json()
                if post_data.get("code") == 200 and post_data.get("success"):
                    rows = post_data.get("data", {}).get("records", [])
                    all_rows.extend(rows)
            except Exception as e:
                print(f"    [BOSC] Request error discovering products at POST {self.PRODUCT_LIST_URL}: {e}")

            # 2. Then try the specific GET APIs (which might 502)
            for url in get_endpoints:
                try:
                    params = {"size": 1000, "current": 1}
                    response = await client.get(url, headers=self.headers, params=params, timeout=15)
                    response.raise_for_status()
                    data = response.json()
                    
                    if data.get("code") == 200 and data.get("success"):
                        rows = data.get("data", {}).get("records", [])
                        all_rows.extend(rows)
                except Exception as e:
                    print(f"    [BOSC] Request error discovering products at GET {url}: {e}")

        # Deduplicate by prdCode
        unique_products = {p.get("prdCode"): p for p in all_rows if p.get("prdCode")}.values()
        unique_products_list = list(unique_products)

        if self.save_raw and unique_products_list:
            self._save_raw("bosc_all_products_snapshot", {"data": {"records": unique_products_list}})

        print(f"    [BOSC] Discovered {len(unique_products_list)} unique products across all categories.")
        return unique_products_list

    async def fetch(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        timeframe: str = '1d',
        exchange: Optional[str] = None,
        **kwargs
    ) -> pd.DataFrame:
        """
        Fetch historical net value data from BOSC ebanks system.

        Args:
            symbol: BOSC product code
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            timeframe: Only '1d' supported
            kwargs: Must include 'prdTemplate', 'status', 'isDxFlag'
        """
        print(f"    [BOSC] Fetching history for: {symbol} | {start_date} -> {end_date}")

        payload = {
            "Month": "36",  # Try to grab up to 3 years of data
            "CacheFlag": "0",
            "PrdTemplate": kwargs.get("prdTemplate", ""),
            "PrdCode": symbol,
            "RateFlag": "1",  # 1 for Cumulative/10k yield
            "Status": kwargs.get("status", "0"),
            "IsDxFlag": kwargs.get("isDxFlag", "2")
        }

        # Need form-urlencoded headers for this specific API
        headers = self.headers.copy()
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        async with httpx.AsyncClient(verify=False) as client:
            try:
                response = await client.post(self.NET_WORTH_URL, headers=headers, data=payload, timeout=20)
                response.raise_for_status()
                # Server returns JSON even for form requests
                data = response.json()
                
                dates = data.get("dates", [])
                rates = data.get("rates", [])
                
                if not dates or not rates:
                    print(f"    [BOSC] No historical data returned for {symbol}.")
                    return pd.DataFrame()
                
                # Dates are in YYYY.MM.DD format, convert them
                dates = [d.replace(".", "-") for d in dates]
                
                return self._transform_to_ohlcv(dates, rates, start_date, end_date)
            except Exception as e:
                print(f"    [BOSC] Request error for {symbol} historical data: {e}")
                return pd.DataFrame()

    def _save_raw(self, symbol: str, data: Dict):
        """Save raw JSON data file."""
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"{symbol}_{timestamp}.json"
        filepath = self.raw_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _transform_to_ohlcv(self, dates: List[str], worths: List[Any], start_date: str, end_date: str) -> pd.DataFrame:
        """Transform historical arrays to standardized OHLCV DataFrame."""
        df = pd.DataFrame({
            "timestamp": dates,
            "close": worths
        })

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["close"] = pd.to_numeric(df["close"], errors="coerce")

        # Set open, high, low equal to close, volume to 0.0 for fund net assets
        df["open"] = df["close"]
        df["high"] = df["close"]
        df["low"] = df["close"]
        df["volume"] = 0.0

        df = df.set_index("timestamp").sort_index()

        # Filter by date range (though typically only 1 row)
        return df.loc[start_date:end_date][["open", "high", "low", "close", "volume"]]

    async def sync(self, symbols: Optional[List[str]] = None):
        """Trigger update for BOSC products using the current snapshot."""
        products = await self.fetch_all_products()
        if not products:
            print("    [BOSC] No products to sync.")
            return

        today_str = datetime.now().strftime("%Y-%m-%d")

        # Create a mapping for quick lookup if symbols are specified
        prod_map = {p.get("prdCode"): p for p in products if p.get("prdCode")}

        if symbols is None:
            symbols = list(prod_map.keys())

        print(f"    [BOSC] Syncing {len(symbols)} products.")

        for symbol in symbols:
            product = prod_map.get(symbol)
            if not product:
                continue

            processed_file = self.processed_dir / f"bosc_net_value_{symbol}.parquet"

            # Determine incremental fetch start date
            start_date = "2000-01-01"
            if processed_file.exists():
                try:
                    existing_df = pd.read_parquet(processed_file)
                    if not existing_df.empty:
                        start_date = existing_df.index[-1].strftime("%Y-%m-%d")
                except Exception:
                    pass

            if start_date == today_str:
                print(f"    [BOSC] {symbol} is already up to date ({start_date}).")
                continue

            # Pass necessary metadata to fetch
            kwargs = {
                "prdTemplate": str(product.get("prdTemplate", "")),
                "status": str(product.get("status", "0")),
                "isDxFlag": str(product.get("isDxFlag", "2"))
            }

            df = await self.fetch(symbol, start_date, "2099-12-31", **kwargs)

            if not df.empty:
                if processed_file.exists():
                    existing_df = pd.read_parquet(processed_file)
                    # Merge existing with new using combine_first
                    combined_df = df.combine_first(existing_df).sort_index()
                else:
                    combined_df = df

                combined_df.to_parquet(processed_file, compression='snappy')

        print("    [BOSC] Sync complete.")

if __name__ == "__main__":
    async def main():
        fetcher = BoscFetcher()
        await fetcher.sync()

    asyncio.run(main())
