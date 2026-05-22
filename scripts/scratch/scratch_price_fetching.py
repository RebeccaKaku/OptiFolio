#!/usr/bin/env python3
"""
测试价格获取功能
"""

import sys
sys.path.insert(0, '.')

from datetime import datetime, timedelta
import pandas as pd

def test_us_equity_fetcher():
    """测试美股价格获取"""
    print("=== 测试美股价格获取 ===")
    
    try:
        from src.data_core.fetchers.us_equity import UsEquityFetcher
        fetcher = UsEquityFetcher()
        
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        print(f"获取 AAPL 价格数据: {start_date} 至 {end_date}")
        df = fetcher.fetch("AAPL", start_date, end_date)
        
        if df is None:
            print("  结果: None")
        elif df.empty:
            print("  结果: 空DataFrame")
            print(f"  列: {df.columns.tolist() if hasattr(df, 'columns') else 'N/A'}")
        else:
            print(f"  成功: {len(df)} 条记录")
            print(f"  列: {df.columns.tolist()}")
            print(f"  数据类型: {type(df)}")
            print(f"  示例数据:")
            print(df.head())
            
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()

def test_cn_stock_fetcher():
    """测试中国股票价格获取"""
    print("\n=== 测试中国股票价格获取 ===")
    
    try:
        from src.data_core.fetchers.cn_stock import CnStockFetcher
        fetcher = CnStockFetcher()
        
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        print(f"获取 sh000001 价格数据: {start_date} 至 {end_date}")
        df = fetcher.fetch("sh000001", start_date, end_date)
        
        if df is None:
            print("  结果: None")
        elif df.empty:
            print("  结果: 空DataFrame")
            print(f"  列: {df.columns.tolist() if hasattr(df, 'columns') else 'N/A'}")
        else:
            print(f"  成功: {len(df)} 条记录")
            print(f"  列: {df.columns.tolist()}")
            print(f"  数据类型: {type(df)}")
            print(f"  示例数据:")
            print(df.head())
            
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()

def test_database_price_history():
    """测试数据库价格历史获取"""
    print("\n=== 测试数据库价格历史 ===")
    
    try:
        from src.core.database import get_database
        db = get_database()
        
        # 检查AAPL是否在数据库中
        print("1. 检查AAPL资产信息:")
        asset = db.get_asset("AAPL")
        if asset:
            print(f"   找到资产: {asset['name']}")
        else:
            print("   AAPL资产不存在")
            
        # 获取价格历史
        print("\n2. 获取AAPL价格历史:")
        price_df = db.get_price_history("AAPL", days=30)
        if price_df is None:
            print("   结果: None")
        elif price_df.empty:
            print("   结果: 空DataFrame")
            print(f"   形状: {price_df.shape}")
        else:
            print(f"   成功: {len(price_df)} 条记录")
            print(f"   列: {price_df.columns.tolist()}")
            print(f"   示例数据:")
            print(price_df.head())
            
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()

def test_enhanced_asset_manager_price():
    """测试增强资产管理器价格获取"""
    print("\n=== 测试增强资产管理器价格获取 ===")
    
    try:
        from src.core.enhanced_asset_manager import EnhancedAssetManager
        manager = EnhancedAssetManager()
        
        print("1. 测试_fetch_and_save_price_history方法:")
        result = manager._fetch_and_save_price_history("AAPL", "us_equity", days=30)
        print(f"   保存价格记录数量: {result}")
        
        print("\n2. 测试_get_enhanced_price_info方法:")
        price_info = manager._get_enhanced_price_info("AAPL")
        if price_info:
            print(f"   价格信息: {price_info}")
        else:
            print("   无价格信息")
            
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()

def test_fetcher_factory():
    """测试Fetcher工厂"""
    print("\n=== 测试Fetcher工厂 ===")
    
    try:
        from src.data_core.fetchers.factory import get_factory
        factory = get_factory()
        
        print("支持的资产类型:")
        types = factory.get_supported_asset_types()
        for asset_type in types:
            fetcher = factory.get_fetcher(asset_type)
            if fetcher:
                print(f"  {asset_type}: {fetcher.__class__.__name__}")
            else:
                print(f"  {asset_type}: 无fetcher")
                
        print("\n获取us_equity fetcher:")
        fetcher = factory.get_fetcher("us_equity")
        if fetcher:
            print(f"  成功获取: {fetcher.__class__.__name__}")
        else:
            print("  获取失败")
            
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fetcher_factory()
    test_us_equity_fetcher()
    test_cn_stock_fetcher()
    test_database_price_history()
    test_enhanced_asset_manager_price()