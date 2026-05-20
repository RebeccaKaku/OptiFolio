#!/usr/bin/env python3
"""
测试增强版系统 - 验证数据库集成和关注机制

测试步骤：
1. 测试数据库初始化
2. 测试资产自动导入
3. 测试关注机制
4. 测试价格曲线获取
5. 测试波动率计算
6. 测试用户友好交互
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.enhanced_asset_manager import get_enhanced_asset_manager
from src.core.database import get_database, close_database
from datetime import datetime
import pandas as pd


def print_header(title):
    """打印测试标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_database_initialization():
    """测试数据库初始化"""
    print_header("测试数据库初始化")
    
    try:
        db = get_database()
        print("[OK] 数据库连接成功")
        
        # 获取数据库统计
        stats = db.get_database_stats()
        print(f"数据库统计:")
        print(f"  - 资产总数: {stats.get('total_assets', 0)}")
        print(f"  - 关注资产数: {stats.get('total_watchlist', 0)}")
        print(f"  - 价格记录数: {stats.get('total_price_records', 0)}")
        print(f"  - 数据库大小: {stats.get('db_file_size_mb', 0):.2f} MB")
        
        return True
    except Exception as e:
        print(f"[FAIL] 数据库初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_asset_auto_import():
    """测试资产自动导入功能"""
    print_header("测试资产自动导入")
    
    try:
        manager = get_enhanced_asset_manager()
        
        # 测试股票
        print("测试中国股票 (sh600519):")
        result = manager.get_asset_info("sh600519")
        if result.get("exists"):
            print(f"[OK] 自动导入成功: {result.get('name')}")
            print(f"   类型: {result.get('asset_type')}")
            print(f"   货币: {result.get('currency')}")
            print(f"   最新价格: {result.get('price_info', {}).get('latest', 'N/A')}")
        else:
            print(f"[FAIL] 导入失败: {result.get('error', '未知错误')}")
        
        # 测试美股
        print("\n测试美股 (AAPL):")
        result = manager.get_asset_info("AAPL")
        if result.get("exists"):
            print(f"[OK] 自动导入成功: {result.get('name')}")
            print(f"   类型: {result.get('asset_type')}")
            print(f"   货币: {result.get('currency')}")
            print(f"   最新价格: {result.get('price_info', {}).get('latest', 'N/A')}")
        else:
            print(f"[FAIL] 导入失败: {result.get('error', '未知错误')}")
        
        # 测试基金
        print("\n测试中国基金 (000001):")
        result = manager.get_asset_info("000001")
        if result.get("exists"):
            print(f"[OK] 自动导入成功: {result.get('name')}")
            print(f"   类型: {result.get('asset_type')}")
            print(f"   货币: {result.get('currency')}")
            print(f"   最新价格: {result.get('price_info', {}).get('latest', 'N/A')}")
        else:
            print(f"[FAIL] 导入失败: {result.get('error', '未知错误')}")
        
        return True
    except Exception as e:
        print(f"[FAIL] 资产自动导入测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_watchlist_mechanism():
    """测试关注机制"""
    print_header("测试关注机制")
    
    try:
        manager = get_enhanced_asset_manager()
        
        # 1. 添加资产到关注列表
        print("1. 添加资产到关注列表:")
        result = manager.add_to_watchlist("sh600519", notes="贵州茅台测试")
        if result.get("success"):
            print(f"[OK] 关注成功: {result.get('message')}")
        else:
            print(f"[FAIL] 关注失败: {result.get('error')}")
        
        result = manager.add_to_watchlist("AAPL", notes="苹果公司测试")
        if result.get("success"):
            print(f"✅ 关注成功: {result.get('message')}")
        else:
            print(f"❌ 关注失败: {result.get('error')}")
        
        # 2. 检查关注状态
        print("\n2. 检查关注状态:")
        in_watchlist = manager.is_in_watchlist("sh600519")
        print(f"   sh600519 在关注列表中: {'[OK]' if in_watchlist else '[FAIL]'}")
        
        in_watchlist = manager.is_in_watchlist("AAPL")
        print(f"   AAPL 在关注列表中: {'[OK]' if in_watchlist else '[FAIL]'}")
        
        in_watchlist = manager.is_in_watchlist("GOOGL")
        print(f"   GOOGL 在关注列表中: {'[OK]' if in_watchlist else '[FAIL]'} (应为False)")
        
        # 3. 获取关注列表
        print("\n3. 获取关注列表:")
        watchlist = manager.get_watchlist_with_metrics()
        print(f"   关注列表数量: {len(watchlist)}")
        
        for item in watchlist:
            print(f"   - {item['symbol']}: {item.get('name', 'N/A')}")
            if 'price_info' in item:
                print(f"     最新价格: {item['price_info'].get('latest', 'N/A')}")
            if 'volatility_30d' in item:
                print(f"     30日波动率: {item['volatility_30d']:.2%}")
        
        # 4. 移除关注
        print("\n4. 移除资产从关注列表:")
        result = manager.remove_from_watchlist("AAPL")
        if result.get("success"):
            print(f"✅ 移除成功: {result.get('message')}")
        else:
            print(f"❌ 移除失败: {result.get('error')}")
        
        # 验证已移除
        in_watchlist = manager.is_in_watchlist("AAPL")
        print(f"   AAPL 仍在关注列表中: {'❌' if not in_watchlist else '✅ (应为False)'}")
        
        return True
    except Exception as e:
        print(f"❌ 关注机制测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_price_curves_and_volatility():
    """测试价格曲线和波动率计算"""
    print_header("测试价格曲线和波动率计算")
    
    try:
        manager = get_enhanced_asset_manager()
        
        # 1. 获取价格历史分析
        print("1. 获取价格历史分析 (sh600519, 30天):")
        result = manager.get_price_history_with_analysis("sh600519", days=30)
        
        if result.get("success"):
            print(f"✅ 获取成功")
            print(f"   数据点数: {result.get('data_points')}")
            print(f"   日期范围: {result.get('date_range', {}).get('start')} 至 {result.get('date_range', {}).get('end')}")
            
            # 波动率信息
            volatility_info = result.get('volatility', {})
            print(f"   年化波动率: {volatility_info.get('annualized', 0):.2%}")
            
            # 性能信息
            performance = result.get('performance', {})
            print(f"   总收益率: {performance.get('total_return', 0):.2%}")
            print(f"   最大回撤: {performance.get('max_drawdown', 0):.2%}")
            
            # 检查技术指标
            analysis = result.get('analysis', {})
            if 'moving_averages' in analysis:
                ma_data = analysis['moving_averages']
                print(f"   移动平均线已计算: MA20({len(ma_data.get('ma20', []))}), MA50({len(ma_data.get('ma50', []))}), MA200({len(ma_data.get('ma200', []))})")
        else:
            print(f"❌ 获取失败: {result.get('error')}")
        
        # 2. 获取资产指标仪表板
        print("\n2. 获取资产指标仪表板:")
        dashboard = manager.get_asset_metrics_dashboard("sh600519")
        
        print(f"   基本信息:")
        basic_info = dashboard.get('basic_info', {})
        print(f"     - 名称: {basic_info.get('name')}")
        print(f"     - 类型: {basic_info.get('asset_type')}")
        print(f"     - 货币: {basic_info.get('currency')}")
        
        print(f"   关注状态: {'已关注' if dashboard.get('watchlist_status') else '未关注'}")
        
        # 价格信息
        price_info = dashboard.get('price_info', {})
        if price_info:
            print(f"   价格信息:")
            print(f"     - 最新价格: {price_info.get('latest', 'N/A')}")
            print(f"     - 日期: {price_info.get('date', 'N/A')}")
            print(f"     - 30日收益: {price_info.get('returns_30d', 'N/A'):.2%}" if price_info.get('returns_30d') else "     - 30日收益: N/A")
            print(f"     - 30日波动率: {price_info.get('volatility_30d', 'N/A'):.2%}" if price_info.get('volatility_30d') else "     - 30日波动率: N/A")
        
        # 计算指标
        metrics = dashboard.get('calculated_metrics', {})
        if metrics:
            print(f"   计算指标:")
            for key, value in metrics.items():
                if 'volatility' in key:
                    print(f"     - {key}: {value:.2%}")
        
        # 投资建议
        recommendations = dashboard.get('recommendations', [])
        if recommendations:
            print(f"   投资建议:")
            for rec in recommendations:
                print(f"     - {rec}")
        
        return True
    except Exception as e:
        print(f"❌ 价格曲线测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_user_friendly_interaction():
    """测试用户友好交互"""
    print_header("测试用户友好交互")
    
    try:
        manager = get_enhanced_asset_manager()
        
        # 1. 测试搜索功能
        print("1. 测试资产搜索:")
        results = manager.search_assets("600", limit=5)
        print(f"   搜索 '600' 结果: {len(results)} 个")
        for asset in results[:3]:
            print(f"   - {asset['symbol']}: {asset.get('name', 'N/A')} ({asset.get('asset_type', 'N/A')})")
        
        # 2. 测试列表功能
        print("\n2. 测试资产列表:")
        assets = manager.list_assets(filter_type="cn_stock")
        print(f"   中国股票数量: {len(assets)}")
        if assets:
            print(f"   示例: {assets[0]['symbol']} - {assets[0].get('name', 'N/A')}")
        
        # 3. 测试批量操作
        print("\n3. 测试批量操作:")
        db = get_database()
        stats = db.get_database_stats()
        print(f"   当前数据库状态:")
        print(f"     - 总资产数: {stats.get('total_assets', 0)}")
        print(f"     - 价格记录数: {stats.get('total_price_records', 0)}")
        
        # 4. 测试手动导入（增强现有资产）
        print("\n4. 测试手动导入:")
        result = manager.import_asset("GOOGL", "us_equity", refresh=True)
        if result.get("success"):
            print(f"✅ 手动导入成功: {result.get('message')}")
            db_data = result.get('database', {})
            print(f"   数据库操作:")
            print(f"     - 资产ID: {db_data.get('asset_id')}")
            print(f"     - 价格记录添加: {db_data.get('price_records_added', 0)}")
            print(f"     - 指标计算: {db_data.get('metrics_calculated', {})}")
        else:
            print(f"❌ 手动导入失败: {result.get('error')}")
        
        return True
    except Exception as e:
        print(f"❌ 用户交互测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_comprehensive_test():
    """运行全面测试"""
    print_header("增强版金融管理系统 - 全面测试")
    print(f"测试开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    test_results = []
    
    # 运行各项测试
    test_results.append(("数据库初始化", test_database_initialization()))
    test_results.append(("资产自动导入", test_asset_auto_import()))
    test_results.append(("关注机制", test_watchlist_mechanism()))
    test_results.append(("价格曲线", test_price_curves_and_volatility()))
    test_results.append(("用户交互", test_user_friendly_interaction()))
    
    # 打印测试总结
    print_header("测试总结")
    passed = sum(1 for _, result in test_results if result)
    total = len(test_results)
    
    print(f"通过测试: {passed}/{total}")
    print()
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
    
    # 最终数据库统计
    try:
        print_header("最终数据库统计")
        db = get_database()
        stats = db.get_database_stats()
        
        print(f"资产统计:")
        print(f"  - 总资产数: {stats.get('total_assets', 0)}")
        print(f"  - 关注资产数: {stats.get('total_watchlist', 0)}")
        print(f"  - 价格记录数: {stats.get('total_price_records', 0)}")
        
        if 'assets_by_type' in stats and stats['assets_by_type']:
            print(f"  - 按类型分布:")
            for asset_type, count in stats['assets_by_type'].items():
                print(f"    * {asset_type}: {count}")
        
        if 'recently_updated' in stats and stats['recently_updated']:
            print(f"  - 最近更新:")
            for asset in stats['recently_updated'][:3]:
                print(f"    * {asset['symbol']}: {asset.get('name', 'N/A')} ({asset.get('last_updated', 'N/A')})")
        
        print(f"数据库文件大小: {stats.get('db_file_size_mb', 0):.2f} MB")
        
    except Exception as e:
        print(f"获取数据库统计失败: {e}")
    
    # 清理资源
    close_database()
    
    return all(result for _, result in test_results)


if __name__ == "__main__":
    print("注意: 此测试需要网络连接以获取资产数据")
    print("首次运行可能需要较长时间（需要下载历史价格数据）")
    print("正在启动测试...")
    
    success = run_comprehensive_test()
    
    if success:
        print("\n🎉 所有测试通过！增强版系统运行正常。")
    else:
        print("\n⚠️ 部分测试失败，请检查日志。")
    
    sys.exit(0 if success else 1)