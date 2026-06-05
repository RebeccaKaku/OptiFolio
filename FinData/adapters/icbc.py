import os
import json
import ssl
import asyncio
import pandas as pd
import httpx
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

class IcbcFetcher:
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
        
        # SSL context workaround: ICBC servers utilize legacy TLS renegotiation.
        # Modern OpenSSL versions (3.0+) disable unsafe legacy renegotiation by default,
        # which throws `ssl.SSLError: [SSL: UNSAFE_LEGACY_RENEGOTIATION_DISABLED]` during handshake.
        # Setting OP_LEGACY_SERVER_CONNECT (0x4) enables legacy connections safely.
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        
        self.headers = {
            "Content-Type": "application/json",
            "Origin": "https://www.icbc.com.cn",
            "Referer": "https://www.icbc.com.cn/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def fetch_all_products(self) -> List[str]:
        """
        Query all active wealth management products from ICBC personal banking.
        """
        print("    [ICBC] Discovering all active products via session-less personal banking...")
        url = "https://mybank.icbc.com.cn/servlet/ICBCBaseReqServletNoSession"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        import re
        all_codes = set()
        page = 1
        
        async with httpx.AsyncClient(verify=self.ssl_context) as client:
            while True:
                page_flag = "0" if page == 1 else "2"
                condition = f"$$$$$$$${page_flag}${page}$$1"
                
                payload = {
                    "dse_operationName": "per_FinanceCurProListP3NSOp",
                    "nowPageNum_turn": str(page),
                    "pageFlag_turn": page_flag,
                    "Area_code": "0200",
                    "useFinanceSolrFlag": "1",
                    "financeQueryCondition": condition
                }
                
                try:
                    response = await client.post(url, headers=headers, data=payload, timeout=20)
                    response.raise_for_status()
                    
                    codes = set(re.findall(r"buySubmit\('([^']+)'", response.text))
                    if not codes:
                        break
                        
                    new_codes = codes.difference(all_codes)
                    if not new_codes:
                        break
                        
                    all_codes.update(codes)
                    page += 1
                    await asyncio.sleep(0.1)  # brief delay
                except Exception as e:
                    print(f"    [ICBC] Error during product discovery page {page}: {e}")
                    break
                    
        print(f"    [ICBC] Discovered {len(all_codes)} active product codes.")
        return sorted(list(all_codes))

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
        """Trigger update for a list of products. If None, performs dynamic auto-discovery merged with config and local files."""
        if symbols is None:
            # 1. Try to discover active products dynamically
            discovered_symbols = []
            try:
                discovered_symbols = await self.fetch_all_products()
            except Exception as e:
                print(f"    [ICBC] Dynamic discovery failed: {e}.")

            # 2. Get local processed symbols
            local_symbols = [f.name.replace("icbc_net_value_", "").replace(".parquet", "") for f in self.processed_dir.glob("icbc_net_value_*.parquet")]
            
            # 3. Get config symbols
            config_symbols = []
            config_path = Path("config/icbc_products.yaml")
            if config_path.exists():
                try:
                    import yaml
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = yaml.safe_load(f)
                        if config_data and "symbols" in config_data:
                            config_symbols = config_data["symbols"]
                            print(f"    [ICBC] Loaded product codes from {config_path}: {config_symbols}")
                except Exception as e:
                    print(f"    [ICBC] Error loading {config_path}: {e}.")
            else:
                config_symbols = ["23GS8125", "23GS8123"]

            # Merge all lists
            symbols = list(set(discovered_symbols + local_symbols + config_symbols))
            print(f"    [ICBC] Final list of {len(symbols)} products to sync.")

        if not symbols:
            print("    [ICBC] No products to sync.")
            return

        semaphore = asyncio.Semaphore(5)

        async def sync_symbol(symbol: str):
            async with semaphore:
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
                    return
                    
                df = await self.fetch(symbol, start_date, end_date)
                
                if not df.empty:
                    # Merge and save
                    if processed_file.exists():
                        try:
                            existing_df = pd.read_parquet(processed_file)
                            combined_df = df.combine_first(existing_df).sort_index()
                        except Exception:
                            combined_df = df
                    else:
                        combined_df = df
                        
                    combined_df.to_parquet(processed_file, compression='snappy')
                    print(f"    [ICBC] {symbol} updated. Total rows: {len(combined_df)}")
                else:
                    print(f"    [ICBC] Fetch failed or no data for {symbol}.")

        # Execute updates concurrently with the semaphore
        tasks = [sync_symbol(s) for s in symbols]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    # Test block
    async def main():
        fetcher = IcbcFetcher()
        # symbols = ["23GS8125", "23GS8689", "23GS8123"]
        symbols = ["23GS8125"]
        await fetcher.sync(symbols)
        
    asyncio.run(main())