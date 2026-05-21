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
        Query all active wealth management products from BOSC portal.
        """
        print("    [BOSC] Discovering products...")
        payload = {
            "current": 1,
            "size": 1000
        }

        async with httpx.AsyncClient(verify=False) as client:
            try:
                response = await client.post(self.PRODUCT_LIST_URL, headers=self.headers, json=payload, timeout=15)
                response.raise_for_status()
                data = response.json()

                if data.get("code") != 200 or not data.get("success"):
                    print(f"    [BOSC] Error: Product discovery failed: {data.get('message')}")
                    return []

                rows = data.get("data", {}).get("records", [])

                if self.save_raw:
                    self._save_raw("bosc_products_snapshot", data)

                print(f"    [BOSC] Discovered {len(rows)} products.")
                return rows
            except Exception as e:
                print(f"    [BOSC] Request error during product discovery: {e}")
                return []

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
        Fetch logic implementation for BOSC.
        As BOSC API does not publicly expose historical net values in an easily accessible JSON format,
        this function relies on data passed via kwargs or assumes `sync` handles the accumulation.

        Args:
            symbol: BOSC product code
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            timeframe: Only '1d' supported
        """
        print(f"    [BOSC] Fetching placeholder for: {symbol} | {start_date} -> {end_date}")
        # Note: BOSC's historical net values are difficult to retrieve dynamically without browser emulation or internal APIs.
        # So we process the snapshot in `sync`.
        return pd.DataFrame()

    def _save_raw(self, symbol: str, data: Dict):
        """Save raw JSON data file."""
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"{symbol}_{timestamp}.json"
        filepath = self.raw_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _transform_to_ohlcv(self, timestamp_str: str, close_val: float, start_date: str, end_date: str) -> pd.DataFrame:
        """Transform single snapshot to standardized OHLCV DataFrame."""
        df = pd.DataFrame({
            "timestamp": [timestamp_str],
            "close": [close_val]
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

            # Determine best value to use: nav (净值) or unitRate (份额净值) or yield
            val = product.get("nav")
            if not val or val == "None" or val == "":
                val = product.get("unitRate")

            if not val or val == "None" or val == "":
                # Fallback to rate or yield if no nav is present
                val = product.get("rate") or product.get("yield") or 1.0

            try:
                close_val = float(val)
            except (ValueError, TypeError):
                continue

            # Date field logic
            # Try to get the latest update date if possible. If missing, use today.
            date_val = product.get("currNetCycleBeginDate") or today_str
            if not date_val or date_val.strip() == "":
                date_val = today_str

            try:
                date_obj = pd.to_datetime(date_val).strftime("%Y-%m-%d")
            except Exception:
                date_obj = today_str

            df = self._transform_to_ohlcv(date_obj, close_val, "2000-01-01", "2099-12-31")

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
