import os
import json
import ssl
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
    - Fetches complete historical net values recursively via qryMCFinanceNetProHisValueForPersonPage.
    - Supports incremental updates and raw JSON data archiving.
    - Standardizes output to the OHLCV format.
    """

    PRODUCT_LIST_URL = "https://www.bosc.cn/apiQry/apiPCQry/qryPcFinanceProductZh"
    NET_WORTH_HIST_URL = "https://www.bosc.cn/apiQry/apiPCQry/v2/qryMCFinanceNetProHisValueForPersonPage"

    def __init__(self, data_dir: str = "data/bosc", save_raw: bool = True, verify_ssl: bool = True):
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.save_raw = save_raw
        self.verify_ssl = verify_ssl

        # Ensure directories exist
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def fetch_all_products(self) -> List[Dict]:
        """
        Query all active wealth management products from BOSC portal.
        """
        print("    [BOSC] Discovering all products from portal...")
        all_rows = []
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
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

        # Deduplicate by prdCode
        unique_products = {p.get("prdCode"): p for p in all_rows if p.get("prdCode")}.values()
        unique_products_list = list(unique_products)

        if self.save_raw and unique_products_list:
            self._save_raw("bosc_all_products_snapshot", {"data": {"records": unique_products_list}})

        print(f"    [BOSC] Discovered {len(unique_products_list)} unique products.")
        return unique_products_list

    def _get_product_metadata(self, symbol: str) -> Dict[str, Any]:
        """Try to load product metadata from local raw snapshot files to resolve taCode and prodSeries."""
        snapshot_files = sorted(self.raw_dir.glob("bosc_all_products_snapshot_*.json"))
        if snapshot_files:
            try:
                with open(snapshot_files[-1], "r", encoding="utf-8") as f:
                    data = json.load(f)
                    records = data.get("data", {}).get("records", [])
                    for r in records:
                        if r.get("prdCode") == symbol:
                            return r
            except Exception as e:
                print(f"    [BOSC] Error loading local product snapshot for metadata: {e}")
        return {}

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
        Fetch historical net value data from BOSC public GET API.

        Args:
            symbol: BOSC product code (e.g. 'WPXK24M1203A')
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            timeframe: Only '1d' supported
            kwargs: Can explicitly include 'taCode', 'prodSeries'. Fallbacks to local snapshot lookup.
        """
        print(f"    [BOSC] Fetching history for: {symbol} | {start_date} -> {end_date}")

        # Resolve manager/series codes
        ta_code = kwargs.get("taCode") or kwargs.get("tacode")
        prod_series = kwargs.get("prodSeries")
        if not ta_code or prod_series is None:
            meta = self._get_product_metadata(symbol)
            if not ta_code:
                ta_code = meta.get("tacode") or "Y58"
            if prod_series is None:
                prod_series = meta.get("prodSeries") or ""

        all_records = []
        page_index = 1
        page_size = 20  # Strict bank WAF rule: size must be <= 20
        total_pages = 1

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        async def make_request(client_to_use, current_page):
            params = {
                "prdCode": symbol,
                "taCode": ta_code,
                "prodSeries": prod_series,
                "size": page_size,
                "current": current_page
            }
            response = await client_to_use.get(self.NET_WORTH_HIST_URL, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            return response.json()

        # Run with initial verify_ssl context
        verify_flag = self.verify_ssl
        async with httpx.AsyncClient(verify=verify_flag) as client:
            try:
                # 1. Fetch first page
                try:
                    data = await make_request(client, page_index)
                except (httpx.ConnectError, httpx.SSLError, ssl.SSLError) as ssl_err:
                    if verify_flag:
                        print(f"    [BOSC] SSL verification failed for {symbol}. Retrying with verify=False... Error: {ssl_err}")
                        async with httpx.AsyncClient(verify=False) as fallback_client:
                            data = await make_request(fallback_client, page_index)
                            verify_flag = False  # Keep using False for next requests
                    else:
                        raise ssl_err

                if data.get("code") == 200 and data.get("success"):
                    records = data.get("data", {}).get("records", [])
                    all_records.extend(records)
                    total_pages = data.get("data", {}).get("pages", 1)

                    # 2. Fetch subsequent pages
                    for page in range(2, total_pages + 1):
                        # Optimization: if earliest date in all_records is already earlier than start_date, we can stop
                        if all_records:
                            earliest_date_str = all_records[-1].get("navDate")
                            if earliest_date_str:
                                earliest_date_clean = earliest_date_str.replace("/", "-")
                                if earliest_date_clean < start_date:
                                    break

                        # Request next page
                        try:
                            if verify_flag:
                                page_data = await make_request(client, page)
                            else:
                                async with httpx.AsyncClient(verify=False) as fallback_client:
                                    page_data = await make_request(fallback_client, page)
                        except Exception:
                            # Final fallback
                            async with httpx.AsyncClient(verify=False) as fallback_client:
                                page_data = await make_request(fallback_client, page)

                        if page_data.get("code") == 200 and page_data.get("success"):
                            records = page_data.get("data", {}).get("records", [])
                            if not records:
                                break
                            all_records.extend(records)
                        else:
                            break
            except Exception as e:
                print(f"    [BOSC] Request error fetching historical net values for {symbol}: {e}")

        if not all_records:
            print(f"    [BOSC] No historical records found for {symbol}.")
            return pd.DataFrame()

        # Extract dates and worths, sort in ascending order (earliest first)
        all_records_sorted = sorted(all_records, key=lambda x: x.get("navDate", ""))
        dates = [r.get("navDate").replace("/", "-") for r in all_records_sorted if r.get("navDate")]
        worths = [r.get("nav") for r in all_records_sorted if r.get("navDate")]

        if self.save_raw:
            self._save_raw(symbol + "_history", {"records": all_records})

        return self._transform_to_ohlcv(dates, worths, start_date, end_date)

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

        # Filter by date range
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
                # If product not found in active list, try to lookup local metadata
                product = self._get_product_metadata(symbol)
                if not product:
                    print(f"    [BOSC] Warning: metadata for {symbol} not found. Skipping.")
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
                "tacode": str(product.get("tacode", "Y58")),
                "prodSeries": str(product.get("prodSeries", ""))
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
                print(f"    [BOSC] {symbol} sync complete. Total rows: {len(combined_df)}")

        print("    [BOSC] Sync complete.")

if __name__ == "__main__":
    async def main():
        fetcher = BoscFetcher()
        await fetcher.sync()

    asyncio.run(main())
