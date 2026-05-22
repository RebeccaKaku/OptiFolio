#!/usr/bin/env python3
"""
测试数据获取修复效果
"""

import sys
import os
from datetime import datetime, timedelta

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

def test_portfolio_core():
    """测试PortfolioCore的数据获取功能"""
    print("=== 测试PortfolioCore数据获取修复 ===")
    
    try:
        from src.core.portfolio_core import PortfolioCore
        
        # 初始化PortfolioCore
        portfolio_core = PortfolioCore(enable_cache=False)
        
        print(f"[测试] PortfolioCore初始化成功")
        
        # 测试当前持仓
        holdings = portfolio_core.get_current_holdings()
        print(f"[测试] 当前持仓: {holdings}")
        
        # 测试每个持仓的资产映射
        for symbol in holdings.keys():
            debug_info = portfolio_core.debug_asset_mapping(symbol)
            print(f"[调试] {symbol}: {debug_info}")
            
            # 尝试修复资产元数据
            if debug_info["asset_type"] == "未知":
                print(f"[修复] 尝试修复 {symbol} 的资产类型...")
                
                # 根据符号推断资产类型
                if symbol.startswith("sh") or symbol.startswith("sz"):
                    asset_type = "cn_stock"
                    currency = "CNY"
                elif symbol.isdigit() and len(symbol) == 6:
                    asset_type = "cn_fund"
                    currency = "CNY"
                elif symbol.isalpha():
                    asset_type = "us_equity"
                    currency = "USD"
                else:
                    asset_type = "us_equity"
                    currency = "USD"
                
                success = portfolio_core.fix_asset_metadata(symbol, asset_type, currency)
                if success:
                    print(f"[修复] 成功修复 {symbol} -> {asset_type} ({currency})")
                    
                    # 重新测试
                    debug_info = portfolio_core.debug_asset_mapping(symbol)
                    print(f"[调试] 修复后: {debug_info}")
        
        # 测试组合价值计算
        print(f"\n[测试] 测试组合价值计算...")
        portfolio_value = portfolio_core.get_portfolio_value()
        
        print(f"[结果] 组合总价值: {portfolio_value.get('total_value', 0):,.2f}")
        print(f"[结果] 持仓价值: {portfolio_value.get('portfolio_value', 0):,.2f}")
        print(f"[结果] 现金价值: {portfolio_value.get('cash_value', 0):,.2f}")
        
        # 显示成功的资产
        if portfolio_value.get('positions'):
            print(f"\n[成功] 成功获取价格的资产:")
            for symbol, data in portfolio_value['positions'].items():
                print(f"  {symbol}: 价格={data['price']:.2f}, 价值={data['value']:,.2f}")
        
        return True
        
    except Exception as e:
        print(f"[错误] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_individual_assets():
    """测试单个资产的数据获取"""
    print("\n=== 测试单个资产数据获取 ===")
    
    try:
        from src.data_core.fetchers.factory import get_factory
        
        factory = get_factory()
        
        # 测试不同类型的资产
        test_assets = [
            ("AAPL", "us_equity"),
            ("QQQ", "us_equity"),
            ("sh600519", "cn_stock"),
            ("510300", "cn_fund"),
            ("005827", "cn_fund"),
        ]
        
        for symbol, asset_type in test_assets:
            print(f"\n[测试] {symbol} ({asset_type}):")
            
            fetcher = factory.get_fetcher(asset_type)
            if fetcher:
                print(f"  获取到fetcher: {fetcher.__class__.__name__}")
                
                # 测试数据获取
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                
                try:
                    df = fetcher.fetch(symbol, start_date=start_date, end_date=end_date)
                    if df is not None and not df.empty:
                        print(f"  成功获取数据: {len(df)} 条记录")
                        if 'Close' in df.columns:
                            latest_price = df['Close'].iloc[-1]
                            print(f"  最新价格: {latest_price}")
                        else:
                            print(f"  可用列: {list(df.columns)}")
                    else:
                        print(f"  未获取到数据")
                        
                except Exception as e:
                    print(f"  数据获取失败: {e}")
            else:
                print(f"  未找到对应的fetcher")
        
        return True
        
    except Exception as e:
        print(f"[错误] 单个资产测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("开始测试数据获取修复...")
    
    # 测试PortfolioCore
    portfolio_success = test_portfolio_core()
    
    # 测试单个资产
    individual_success = test_individual_assets()
    
    print(f"\n=== 测试结果 ===")
    print(f"PortfolioCore测试: {'通过' if portfolio_success else '失败'}")
    print(f"单个资产测试: {'通过' if individual_success else '失败'}")
    
    if portfolio_success and individual_success:
        print("✅ 所有测试通过！数据获取修复成功。")
    else:
        print("❌ 部分测试失败，需要进一步调试。")

if __name__ == "__main__":
    main()