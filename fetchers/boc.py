import os
import json
import asyncio
import pandas as pd
import httpx
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from .interfaces import AsyncBaseFetcher

class BocFetcher(AsyncBaseFetcher):
    """
    Bank of China Wealth Management Product (理财产品) Fetcher.
    
    Features:
    - Fetches product list from BOCWM queryStaticProducts JSON API (filters USD products).
    - Fetches complete historical net values in one single request via getNetWorthImageByCode API.
    - Supports incremental updates and raw JSON data archiving.
    - Standardizes output to the OHLCV format.
    """
    
    PRODUCT_LIST_URL = "https://www.bocwm.cn/webApi/cms/product/queryStaticProducts"
    NET_WORTH_URL = "https://www.bocwm.cn/webApi/cms/productNetWorth/getNetWorthImageByCode"
    
    def __init__(self, data_dir: str = "data/boc", save_raw: bool = True):
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

    async def fetch_usd_products(self) -> List[str]:
        """
        Query all active USD wealth management products from BOCWM portal.
        """
        print("    [BOC] Discovering active USD products...")
        payload = {
            "pageNo": 1,
            "pageSize": 1000,
            "currency": "美元"
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.PRODUCT_LIST_URL, headers=self.headers, json=payload, timeout=15)
                response.raise_for_status()
                data = response.json()
                
                if not data.get("result"):
                    print("    [BOC] Error: Product discovery failed or API returned result=False.")
                    return []
                    
                rows = data.get("data", {}).get("rows", [])
                product_codes = [r.get("productCode") for r in rows if r.get("productCode")]
                print(f"    [BOC] Discovered {len(product_codes)} active USD products.")
                return product_codes
            except Exception as e:
                print(f"    [BOC] Request error during USD product discovery: {e}")
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
        Fetch net value data for a product code.
        
        Args:
            symbol: BOC product code (e.g., 'AMHQLXTTUSD01B')
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            timeframe: Only '1d' supported
            exchange: Not used
        """
        print(f"    [BOC] Fetching: {symbol} | {start_date} -> {end_date}")
        
        async with httpx.AsyncClient() as client:
            params = {
                "productCode": symbol
            }
            try:
                response = await client.get(self.NET_WORTH_URL, headers=self.headers, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()
                
                if not data.get("result"):
                    print(f"    [BOC] API Error for {symbol}: result flag is False.")
                    return pd.DataFrame()
                    
                if self.save_raw:
                    self._save_raw(symbol, data)
                
                dates = data.get("dateList", [])
                worths = data.get("shareNetWorthList", [])
                
                if not dates or not worths:
                    print(f"    [BOC] No historical data returned for {symbol}.")
                    return pd.DataFrame()
                    
                return self._transform_to_ohlcv(dates, worths, start_date, end_date)
            except Exception as e:
                print(f"    [BOC] Request error for {symbol}: {e}")
                return pd.DataFrame()

    def _save_raw(self, symbol: str, data: Dict):
        """Save raw JSON data file."""
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"{symbol}_{timestamp}.json"
        filepath = self.raw_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _transform_to_ohlcv(self, dates: List[str], worths: List[Any], start_date: str, end_date: str) -> pd.DataFrame:
        """Transform date list and net worth list into standardized OHLCV DataFrame."""
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
        """Trigger update for a list of products. If None, performs auto-discovery."""
        if symbols is None:
            # 1. First, check already processed products in files
            symbols = [f.name.replace("boc_net_value_", "").replace(".parquet", "") 
                       for f in self.processed_dir.glob("boc_net_value_*.parquet")]
            
            # 2. If nothing is in processed_dir, query the API to discover active USD products
            if not symbols:
                symbols = await self.fetch_usd_products()
                
            print(f"    [BOC] Syncing {len(symbols)} products: {symbols}")

        if not symbols:
            print("    [BOC] No products to sync.")
            return

        for symbol in symbols:
            processed_file = self.processed_dir / f"boc_net_value_{symbol}.parquet"
            start_date = "2000-01-01"
            
            # Determine last date from existing file for incremental update
            if processed_file.exists():
                try:
                    existing_df = pd.read_parquet(processed_file)
                    if not existing_df.empty:
                        start_date = existing_df.index[-1].strftime("%Y-%m-%d")
                except Exception:
                    pass
            
            end_date = datetime.now().strftime("%Y-%m-%d")
            
            if start_date == end_date:
                print(f"    [BOC] {symbol} is already up to date ({start_date}).")
                continue
                
            df = await self.fetch(symbol, start_date, end_date)
            
            if not df.empty:
                if processed_file.exists():
                    existing_df = pd.read_parquet(processed_file)
                    # Merge existing with new using combine_first
                    combined_df = df.combine_first(existing_df).sort_index()
                else:
                    combined_df = df
                    
                combined_df.to_parquet(processed_file, compression='snappy')
                print(f"    [BOC] {symbol} updated successfully. Total records: {len(combined_df)}")
            else:
                print(f"    [BOC] Fetch failed or no data for {symbol}.")

if __name__ == "__main__":
    async def main():
        fetcher = BocFetcher()
        await fetcher.sync(["AMHQLXTTUSD01B"])
        
    asyncio.run(main())
