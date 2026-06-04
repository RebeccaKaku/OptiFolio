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
    METADATA_PATH = Path("data/boc/product_metadata.json")
    
    def __init__(self, data_dir: str = "data/boc", save_raw: bool = True):
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.save_raw = save_raw
        self._metadata_index: Optional[Dict[str, Any]] = None  # lazy loaded
        
        # Ensure directories exist
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def load_metadata_index(self) -> Dict[str, Any]:
        """
        Load (and cache) the BOC product metadata JSON into a dict keyed by product_code.
        Call scripts/fetch_boc_metadata.py first to generate the file.
        """
        if self._metadata_index is not None:
            return self._metadata_index
        if not self.METADATA_PATH.exists():
            print(f"    [BOC] Metadata file not found: {self.METADATA_PATH}. Run scripts/fetch_boc_metadata.py first.")
            self._metadata_index = {}
            return self._metadata_index
        with open(self.METADATA_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self._metadata_index = {
            p["product_code"]: p
            for p in raw.get("products", [])
            if p.get("product_code")
        }
        print(f"    [BOC] Loaded metadata for {len(self._metadata_index)} products.")
        return self._metadata_index

    def get_product_metadata(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Return the enriched metadata dict for a product code, or None if not found.
        Fields available:
          product_name, currency, currency_source,
          establishment_date, maturity_date, subscription_period,
          next_open_date, min_purchase_amount, term, min_hold_period,
          risk_level, detail_url, prospectus_pdfs, fetched_at
        """
        return self.load_metadata_index().get(code)


    async def fetch_all_products(self) -> List[str]:
        """
        Query all active wealth management products (RMB & Foreign currencies) from BOCWM portal.
        """
        print("    [BOC] Discovering all active products...")
        payload = {
            "pageNo": 1,
            "pageSize": 5000
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
                # Only include products that have shareNetWorth published to avoid useless requests
                product_codes = [r.get("productCode") for r in rows if r.get("productCode") and r.get("shareNetWorth") is not None]
                print(f"    [BOC] Discovered {len(product_codes)} active products with net worth.")
                return product_codes
            except Exception as e:
                print(f"    [BOC] Request error during product discovery: {e}")
                return []

    async def fetch_structural_deposits(self) -> List[str]:
        """
        Fetch BOC structural deposits data by scraping the public pages.
        Includes both RMB and Foreign Currency.
        """
        print("    [BOC] Fetching structural deposits from bill page...")
        url = "https://www.boc.cn/sdbapp/pbsd4/"
        struct_codes = []
        try:
            from bs4 import BeautifulSoup
            async with httpx.AsyncClient(follow_redirects=True) as client:
                try:
                    res = await client.get(url, headers=self.headers, timeout=15)
                    res.raise_for_status()
                except httpx.ConnectError:
                    # Fallback: some BOC servers use legacy SSL
                    async with httpx.AsyncClient(follow_redirects=True, verify=False) as fallback:
                        res = await fallback.get(url, headers=self.headers, timeout=15)
                        res.raise_for_status()
                soup = BeautifulSoup(res.text, "html.parser")
                for link in soup.find_all("a"):
                    text = link.text.strip()
                    # A valid structural deposit code is uppercase alphanumeric, usually starting with CS, GR, etc.
                    # We can use a regex to be strict.
                    import re
                    if re.match(r'^[A-Z0-9]{8,15}$', text) and text.isupper():
                        struct_codes.append(text)
        except Exception as e:
            print(f"    [BOC] Error fetching structural deposits: {e}")

        print(f"    [BOC] Discovered {len(struct_codes)} structural deposits.")
        return list(set(struct_codes))

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
            # 1. Query the API to discover all active products
            symbols = await self.fetch_all_products()
            
            # 2. Add structural deposits codes
            struct_codes = await self.fetch_structural_deposits()
            symbols.extend(struct_codes)
            symbols = list(set(symbols))

            print(f"    [BOC] Auto-discovered {len(symbols)} products to sync.")

        if not symbols:
            print("    [BOC] No products to sync.")
            return

        semaphore = asyncio.Semaphore(5)

        async def sync_symbol(symbol: str):
            async with semaphore:
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
                    return
                    
                df = await self.fetch(symbol, start_date, end_date)
                
                if not df.empty:
                    if processed_file.exists():
                        try:
                            existing_df = pd.read_parquet(processed_file)
                            combined_df = df.combine_first(existing_df).sort_index()
                        except Exception:
                            combined_df = df
                    else:
                        combined_df = df
                        
                    combined_df.to_parquet(processed_file, compression='snappy')
                    print(f"    [BOC] {symbol} updated successfully. Total records: {len(combined_df)}")
                else:
                    print(f"    [BOC] Fetch failed or no data for {symbol}.")

        # Execute updates concurrently with the semaphore
        tasks = [sync_symbol(s) for s in symbols]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    async def main():
        fetcher = BocFetcher()
        await fetcher.sync(["AMHQLXTTUSD01B"])
        
    asyncio.run(main())
