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

class IcbcFetcher(AsyncBaseFetcher):
    """
    ICBC Wealth Management Product (理财产品) Fetcher.
    
    Features:
    - Fetches data from ICBC internal JSON API.
    - Supports incremental updates and raw data storage.
    - Standardizes output to OHLCV format.
    """
    
    BASE_URL = "https://papi.icbc.com.cn/finance/deposit/consignment/getNetValueList"
    
    def __init__(self, data_dir: str = "data/icbc", save_raw: bool = True):
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.save_raw = save_raw
        
        # Ensure directories exist
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        # SSL context to allow legacy renegotiation for ICBC servers
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        
        self.headers = {
            "Content-Type": "application/json",
            "Origin": "https://www.icbc.com.cn",
            "Referer": "https://www.icbc.com.cn/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

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
        Fetch net value data for a product ID.
        
        Args:
            symbol: ICBC product ID (e.g., '23GS8125')
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            timeframe: Only '1d' supported
            exchange: Not used
        """
        print(f"    [ICBC] Fetching: {symbol} | {start_date} -> {end_date}")
        
        all_items = []
        page_index = 1
        page_size = 50
        
        async with httpx.AsyncClient(verify=self.ssl_context) as client:
            while True:
                payload = {
                    "prodId": symbol,
                    "pageIndex": page_index,
                    "pageSize": page_size
                }
                
                try:
                    response = await client.post(self.BASE_URL, headers=self.headers, json=payload, timeout=15)
                    response.raise_for_status()
                    data = response.json()
                    
                    if data.get("code") != 0:
                        print(f"    [ICBC] API Error: {data.get('message')}")
                        break
                        
                    items = data.get("data", {}).get("list", [])
                    if not items:
                        break
                    
                    if self.save_raw:
                        self._save_raw_page(symbol, page_index, items)
                    
                    all_items.extend(items)
                    
                    # Check if we've reached the start_date or end of data
                    # ICBC API returns data sorted by date descending
                    last_date_str = items[-1].get("workDate")
                    if last_date_str and last_date_str < start_date:
                        break
                        
                    # Check if we have more pages
                    total = data.get("data", {}).get("total", 0)
                    if len(all_items) >= total:
                        break
                        
                    page_index += 1
                except Exception as e:
                    print(f"    [ICBC] Request error for {symbol}: {e}")
                    break
        
        if not all_items:
            return pd.DataFrame()
            
        return self._transform_to_ohlcv(all_items, start_date, end_date)

    def _save_raw_page(self, symbol: str, page_index: int, items: List[Dict]):
        """Save raw JSON items for a specific page."""
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"{symbol}_{timestamp}_p{page_index}.json"
        filepath = self.raw_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    def _transform_to_ohlcv(self, items: List[Dict], start_date: str, end_date: str) -> pd.DataFrame:
        """Transform ICBC API items to standardized OHLCV DataFrame."""
        df = pd.DataFrame(items)
        
        # Rename columns to standardized names
        # ICBC fields: workDate, value (net value), totValue (accumulated)
        df = df.rename(columns={
            "workDate": "timestamp",
            "value": "close"
        })
        
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        
        # Set other OHLC values to close for funds
        df["open"] = df["close"]
        df["high"] = df["close"]
        df["low"] = df["close"]
        df["volume"] = 0.0

        df = df.set_index("timestamp").sort_index()
        
        # Filter by date range
        return df.loc[start_date:end_date][["open", "high", "low", "close", "volume"]]

    async def sync(self, symbols: Optional[List[str]] = None):
        """Trigger update for a list of products. If None, syncs all found in processed_dir and some default codes."""
        if symbols is None:
            # Auto-discover from processed_dir
            symbols = [f.name.replace("icbc_net_value_", "").replace(".parquet", "") for f in self.processed_dir.glob("icbc_net_value_*.parquet")]

            # Since no public discovery API is available without login, we append some default test codes covering RMB and Foreign Currency products
            default_codes = ["23GS8125", "23GS8123"]
            symbols.extend(default_codes)
            symbols = list(set(symbols))

            print(f"    [ICBC] Auto-discovered {len(symbols)} products: {symbols}")

        if not symbols:
            print("    [ICBC] No products to sync.")
            return

        for symbol in symbols:
            # Check last date in existing processed file to determine start_date
            processed_file = self.processed_dir / f"icbc_net_value_{symbol}.parquet"
            start_date = "2000-01-01"
            
            if processed_file.exists():
                try:
                    existing_df = pd.read_parquet(processed_file)
                    if not existing_df.empty:
                        start_date = existing_df.index[-1].strftime("%Y-%m-%d")
                except Exception:
                    pass
            
            end_date = datetime.now().strftime("%Y-%m-%d")
            
            if start_date == end_date:
                print(f"    [ICBC] {symbol} is already up to date ({start_date}).")
                continue
                
            df = await self.fetch(symbol, start_date, end_date)
            
            if not df.empty:
                # Merge and save
                if processed_file.exists():
                    existing_df = pd.read_parquet(processed_file)
                    # Use combine_first to avoid duplicates and update with new data
                    combined_df = df.combine_first(existing_df).sort_index()
                else:
                    combined_df = df
                    
                combined_df.to_parquet(processed_file, compression='snappy')
                print(f"    [ICBC] {symbol} updated. Total rows: {len(combined_df)}")

if __name__ == "__main__":
    # Test block
    async def main():
        fetcher = IcbcFetcher()
        # symbols = ["23GS8125", "23GS8689", "23GS8123"]
        symbols = ["23GS8125"]
        await fetcher.sync(symbols)
        
    asyncio.run(main())