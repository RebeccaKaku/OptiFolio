import asyncio
import sys
from fetchers.icbc import IcbcFetcher

async def main():
    fetcher = IcbcFetcher()
    
    # Get symbols from command line if any
    symbols = sys.argv[1:] if len(sys.argv) > 1 else None
    
    print("=== ICBC Data Sync Trigger ===")
    await fetcher.sync(symbols)
    print("=== Sync Complete ===")

if __name__ == "__main__":
    asyncio.run(main())
