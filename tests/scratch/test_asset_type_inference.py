#!/usr/bin/env python3
"""
测试资产类型推断功能
"""

import sys
sys.path.insert(0, '.')

from src.asset_importer import AssetImporter

def test_infer_asset_type():
    """测试_asset_type推断"""
    importer = AssetImporter()
    
    test_cases = [
        # (symbol, expected_type)
        ("sh000001", "cn_stock"),
        ("sz000001", "cn_stock"),
        ("600519", "cn_stock"),
        ("000001", "cn_stock"),
        ("002892", "cn_fund"),
        ("AAPL", "us_equity"),
        ("MSFT", "us_equity"),
        ("EUR/USD", "currency"),
        ("USDCAD", "currency"),
        ("CNYUSD", "currency"),
        ("USDCNY", "currency"),
        ("sh600519", "cn_stock"),
        ("sz300750", "cn_stock"),
        ("123456", "cn_fund"),  # 6位数字可能是基金
        ("000300", "cn_fund"),  # 沪深300指数基金
    ]
    
    print("=== 资产类型推断测试 ===")
    for symbol, expected in test_cases:
        try:
            # 调用私有方法（通过反射）
            method = importer._infer_asset_type
            result = method(symbol)
            status = "✓" if result == expected else "✗"
            print(f"{status} {symbol:15} -> {result:10} (期望: {expected})")
        except Exception as e:
            print(f"✗ {symbol:15} -> 错误: {e}")

def test_import_asset():
    """测试资产导入"""
    print("\n=== 资产导入测试 ===")
    
    importer = AssetImporter()
    
    # 测试sh000001
    print("\n1. 测试 sh000001:")
    try:
        asset = importer.import_asset("sh000001", asset_type=None)
        if asset:
            print(f"   成功: {asset.name}")
        else:
            print(f"   失败: 返回None")
    except Exception as e:
        print(f"   异常: {e}")
    
    # 测试EUR/USD
    print("\n2. 测试 EUR/USD:")
    try:
        asset = importer.import_asset("EUR/USD", asset_type=None)
        if asset:
            print(f"   成功: {asset.name}")
        else:
            print(f"   失败: 返回None")
    except Exception as e:
        print(f"   异常: {e}")
    
    # 测试AAPL
    print("\n3. 测试 AAPL:")
    try:
        asset = importer.import_asset("AAPL", asset_type=None)
        if asset:
            print(f"   成功: {asset.name}")
        else:
            print(f"   失败: 返回None")
    except Exception as e:
        print(f"   异常: {e}")

def test_normalize_symbol():
    """测试符号标准化"""
    print("\n=== 符号标准化测试 ===")
    
    importer = AssetImporter()
    
    test_cases = [
        ("sh000001", "cn_stock", "sh000001"),
        ("600519", "cn_stock", "sh600519"),
        ("000001", "cn_stock", "sz000001"),
        ("300750", "cn_stock", "sz300750"),
        ("AAPL", "us_equity", "AAPL"),
        ("msft", "us_equity", "MSFT"),
        ("EUR/USD", "currency", "EUR/USD"),
    ]
    
    for symbol, asset_type, expected in test_cases:
        try:
            result = importer._normalize_symbol(symbol, asset_type)
            status = "✓" if result == expected else "✗"
            print(f"{status} ({symbol}, {asset_type}) -> {result} (期望: {expected})")
        except Exception as e:
            print(f"✗ ({symbol}, {asset_type}) -> 错误: {e}")

if __name__ == "__main__":
    test_infer_asset_type()
    test_normalize_symbol()
    test_import_asset()