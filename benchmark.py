import time
from src.core.enhanced_asset_manager import EnhancedAssetManager
import os
import sys

def run_benchmark():
    try:
        manager = EnhancedAssetManager()
        symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META']
        print("Starting batch import benchmark...")
        start_time = time.time()
        result = manager.batch_import(symbols)
        end_time = time.time()
        duration = end_time - start_time
        print(f"Time taken: {duration:.2f} seconds")
        print(f"Results summary: {result['summary']}")
        return duration
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    run_benchmark()
