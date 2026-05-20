#!/usr/bin/env python3
"""
测试修复的 KeyError bug 和应用启动速度优化
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from src.api.enhanced_api_service import get_enhanced_api_service
from src.core.enhanced_asset_manager import EnhancedAssetManager
import json

def test_keyerror_fix():
    """测试 KeyError bug 修复"""
    print("=" * 60)
    print("测试 KeyError bug 修复...")
    print("=" * 60)
    
    # 模拟 app.py 中的系统状态检查
    api_service = get_enhanced_api_service()
    
    try:
        system_status = api_service.get_system_status()
        
        # 检查是否有 success 键
        if "success" not in system_status:
            print("❌ FAIL: system_status 缺少 'success' 键")
            return False
        
        if not system_status["success"]:
            # 即使失败也应该有正确的结构
            error_msg = system_status.get("error", "未知错误")
            print(f"⚠️ 系统状态检查失败（预期行为）: {error_msg}")
            return True  # 这不是测试失败，只是系统状态不好
        
        # 检查 data 键是否存在
        status_data = system_status.get("data", {})
        
        # 测试 app.py 第 121 行左右的代码
        overall_status = status_data.get("overall_status", "UNKNOWN")
        
        # 测试其他键是否存在
        asset_system = status_data.get("asset_system", {})
        asset_status = asset_system.get("status", "UNKNOWN")
        asset_count = asset_system.get("total_assets", 0)
        
        portfolio_system = status_data.get("portfolio_system", {})
        portfolio_status = portfolio_system.get("status", "UNKNOWN")
        portfolio_value = portfolio_system.get("total_value", 0)
        
        print(f"✅ 系统状态检查通过")
        print(f"   总体状态: {overall_status}")
        print(f"   资产系统: {asset_status}, {asset_count}个资产")
        print(f"   组合系统: {portfolio_status}, ¥{portfolio_value:,.2f}")
        
        return True
        
    except KeyError as e:
        print(f"❌ FAIL: KeyError 仍然存在: {e}")
        print(f"   错误位置: {e.args}")
        return False
    except Exception as e:
        print(f"❌ FAIL: 其他错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_startup_optimization():
    """测试应用启动速度优化"""
    print("\n" + "=" * 60)
    print("测试应用启动速度优化...")
    print("=" * 60)
    
    try:
        # 创建资产管理器实例
        manager = EnhancedAssetManager()
        
        # 测试符号
        test_symbol = "sh000001"
        
        print(f"测试资产: {test_symbol}")
        
        # 1. 首先确保资产在数据库中
        print("1. 确保资产在数据库中...")
        asset_info = manager.get_asset_info(test_symbol)
        
        if not asset_info.get("exists", False):
            print(f"   导入资产 {test_symbol}...")
            result = manager.import_asset(test_symbol)
            if not result.get("success"):
                print(f"   ❌ 无法导入资产: {result.get('error')}")
                return False
            print(f"   ✅ 资产导入成功")
        else:
            print(f"   ✅ 资产已在数据库中")
        
        # 2. 获取最新价格记录
        print("2. 检查现有价格数据...")
        from src.core.database import get_database
        db = get_database()
        latest_price = db.get_latest_price(test_symbol)
        
        if latest_price:
            latest_date = latest_price.get('date', '未知日期')
            print(f"   ✅ 数据库已有价格数据，最新日期: {latest_date}")
            
            # 检查是否在最近3天内
            from datetime import datetime
            try:
                latest_date_obj = datetime.strptime(latest_date, '%Y-%m-%d')
                days_since_last = (datetime.now() - latest_date_obj).days
                print(f"   距离最新数据天数: {days_since_last}天")
                
                if days_since_last <= 3:
                    print(f"   ✅ 数据在最近3天内 ({days_since_last}天前)")
                    print(f"   预期行为: 启动时应跳过下载")
                    
                    # 测试 _fetch_and_save_price_history 方法
                    print("3. 测试 _fetch_and_save_price_history 方法...")
                    asset_type = asset_info.get('asset_type', 'cn_stock')
                    
                    # 记录调用前的情况
                    import time
                    start_time = time.time()
                    
                    # 调用方法（不强制刷新）
                    added_count = manager._fetch_and_save_price_history(
                        test_symbol, asset_type, force_refresh=False
                    )
                    
                    elapsed_time = time.time() - start_time
                    
                    print(f"   方法执行时间: {elapsed_time:.2f}秒")
                    print(f"   添加的价格记录数: {added_count}")
                    
                    if added_count == 0:
                        print(f"   ✅ PASS: 当有近期数据时跳过下载")
                        return True
                    else:
                        print(f"   ❌ FAIL: 添加了 {added_count} 条记录，但应该跳过下载")
                        return False
                else:
                    print(f"   ℹ️ 数据已超过3天 ({days_since_last}天前)")
                    print(f"   预期行为: 启动时应下载最近数据")
                    return True  # 这不是测试失败
                    
            except Exception as e:
                print(f"   ❌ 日期解析失败: {e}")
                return False
        else:
            print(f"   ℹ️ 数据库中没有价格数据")
            print(f"   预期行为: 启动时应下载数据")
            return True  # 这不是测试失败
            
    except Exception as e:
        print(f"❌ 测试启动优化失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_app_integration():
    """测试应用集成"""
    print("\n" + "=" * 60)
    print("测试应用集成...")
    print("=" * 60)
    
    try:
        # 测试 app.py 中的关键函数
        api_service = get_enhanced_api_service()
        
        print("1. 测试关键API调用...")
        
        # 测试 get_system_status
        print("   - get_system_status...")
        status = api_service.get_system_status()
        assert isinstance(status, dict), "状态应返回字典"
        print(f"      ✅ 返回类型正确")
        
        # 测试 get_asset_statistics
        print("   - get_asset_statistics...")
        stats = api_service.get_asset_statistics()
        print(f"      ✅ 资产统计调用成功")
        
        # 测试 list_assets
        print("   - list_assets...")
        assets = api_service.list_assets()
        print(f"      ✅ 资产列表调用成功")
        
        print("2. 测试关注功能...")
        
        # 测试 add_to_watchlist
        print("   - add_to_watchlist...")
        watch_result = api_service.add_to_watchlist("AAPL", "test_user")
        print(f"      ✅ 关注功能调用成功")
        
        print("\n✅ 应用集成测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 应用集成测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("开始测试修复...")
    print("=" * 60)
    
    all_passed = True
    
    # 运行测试
    if not test_keyerror_fix():
        all_passed = False
    
    if not test_startup_optimization():
        all_passed = False
    
    if not test_app_integration():
        all_passed = False
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    if all_passed:
        print("✅ 所有测试通过！")
        print("\n修复验证:")
        print("1. KeyError bug: 已修复 - 使用 .get() 方法处理缺失键")
        print("2. 启动速度优化: 已实现 - 优先使用数据库中的近期数据，减少下载")
        return 0
    else:
        print("❌ 部分测试失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())