#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API 检测模块测试脚本

使用方法:
    python -m api_checker.test_api_checker
    或
    python api_checker/test_api_checker.py
"""

import asyncio
import sys
import os

# 确保可以导入父目录的模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_checker import (
    APICheckerRunner,
    CryptoAPIChecker,
    YahooAPIChecker,
    AkshareAPIChecker,
    quick_check,
    run_check
)


async def test_individual_checkers():
    """测试各个独立的检测器"""
    print("\n" + "="*60)
    print("Testing Individual Checkers")
    print("="*60)
    
    # 测试 Crypto 检测器
    print("\n[1] Testing CryptoAPIChecker...")
    crypto_checker = CryptoAPIChecker(exchanges=['binance'])
    result = await crypto_checker.check()
    print(f"  Result: {result}")
    
    # 测试 Yahoo 检测器
    print("\n[2] Testing YahooAPIChecker...")
    yahoo_checker = YahooAPIChecker()
    result = await yahoo_checker.check()
    print(f"  Result: {result}")
    
    # 测试 Akshare 检测器
    print("\n[3] Testing AkshareAPIChecker...")
    akshare_checker = AkshareAPIChecker()
    result = await akshare_checker.check()
    print(f"  Result: {result}")


async def test_runner():
    """测试运行器"""
    print("\n" + "="*60)
    print("Testing APICheckerRunner")
    print("="*60)
    
    runner = APICheckerRunner(log_dir="logs")
    runner.add_default_checkers(crypto_exchanges=['binance', 'okx'])
    
    results = await runner.run_all()
    
    print("\n[Summary Data]")
    summary = runner.get_summary()
    print(f"  Total: {summary['total']}")
    print(f"  Success: {summary['success']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Success Rate: {summary['success_rate']*100:.1f}%")


async def test_quick_check():
    """测试便捷函数"""
    print("\n" + "="*60)
    print("Testing quick_check() function")
    print("="*60)
    
    summary = await quick_check(crypto_exchanges=['binance'])
    print(f"\nResult: {summary['success']}/{summary['total']} APIs available")


def main():
    """主函数"""
    print("\n" + "#"*60)
    print("#  API Checker Module Test")
    print("#"*60)
    
    # 测试模式选择
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode == 'individual':
            asyncio.run(test_individual_checkers())
        elif mode == 'runner':
            asyncio.run(test_runner())
        elif mode == 'quick':
            asyncio.run(test_quick_check())
        else:
            print(f"Unknown mode: {mode}")
            print("Usage: python test_api_checker.py [individual|runner|quick]")
    else:
        # 默认运行所有测试
        asyncio.run(test_individual_checkers())
        asyncio.run(test_runner())
    
    print("\n" + "#"*60)
    print("#  Test Complete!")
    print("#"*60 + "\n")


if __name__ == "__main__":
    main()
