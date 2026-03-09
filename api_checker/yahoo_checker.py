# api_checker/yahoo_checker.py
"""
Yahoo Finance API 检测器
检测 yfinance 库的 API 连通性
"""

import asyncio
from typing import Optional

from .base import APIChecker, CheckResult, CheckStatus


class YahooAPIChecker(APIChecker):
    """
    Yahoo Finance API 检测器
    
    通过 yfinance 库检测 Yahoo Finance API 的连通性
    """
    
    # 检测用的股票代码
    TEST_SYMBOL = 'AAPL'  # 苹果股票，流动性高且稳定
    
    def __init__(self, name: str = "Yahoo Finance", timeout: float = 15.0):
        """
        初始化 Yahoo Finance API 检测器
        
        Args:
            name: 检测器名称
            timeout: 超时时间（秒），Yahoo Finance 可能较慢
        """
        super().__init__(name, timeout)
    
    async def check(self) -> CheckResult:
        """
        检测 Yahoo Finance API 连通性
        
        Returns:
            CheckResult: 检测结果
        """
        try:
            import yfinance as yf
            
            with self._measure_time() as timer:
                # 使用 asyncio.to_thread 将同步调用转为异步
                ticker = await asyncio.wait_for(
                    asyncio.to_thread(yf.Ticker, self.TEST_SYMBOL),
                    timeout=self.timeout
                )
                
                # 获取快速信息（比完整历史数据更快）
                info = await asyncio.wait_for(
                    asyncio.to_thread(lambda: ticker.info),
                    timeout=self.timeout
                )
            
            if info and 'regularMarketPrice' in info:
                price = info['regularMarketPrice']
                currency = info.get('currency', 'USD')
                symbol = info.get('symbol', self.TEST_SYMBOL)
                return self._create_success_result(
                    timer.latency_ms,
                    f"{symbol}: {currency} {price:,.2f}"
                )
            elif info and 'currentPrice' in info:
                price = info['currentPrice']
                return self._create_success_result(
                    timer.latency_ms,
                    f"{self.TEST_SYMBOL}: ${price:,.2f}"
                )
            else:
                # 即使没有价格信息，如果能获取到部分数据也算成功
                if info:
                    return self._create_success_result(
                        timer.latency_ms,
                        f"Connected (partial data)"
                    )
                return self._create_fail_result(
                    CheckStatus.ERROR,
                    "No data returned"
                )
                
        except asyncio.TimeoutError:
            return self._create_fail_result(
                CheckStatus.TIMEOUT,
                f"Timeout after {self.timeout}s"
            )
        except ImportError:
            return self._create_fail_result(
                CheckStatus.ERROR,
                "yfinance library not installed. Run: pip install yfinance"
            )
        except Exception as e:
            error_msg = str(e)
            # 常见错误信息简化
            if "Connection" in error_msg or "network" in error_msg.lower():
                return self._create_fail_result(
                    CheckStatus.FAIL,
                    f"Network error: {error_msg[:80]}"
                )
            elif "rate limit" in error_msg.lower():
                return self._create_fail_result(
                    CheckStatus.FAIL,
                    "Rate limited - try again later"
                )
            return self._create_fail_result(
                CheckStatus.ERROR,
                f"Error: {error_msg[:80]}"
            )
    
    async def check_symbol(self, symbol: str) -> CheckResult:
        """
        检测指定股票代码
        
        Args:
            symbol: 股票代码
            
        Returns:
            CheckResult: 检测结果
        """
        try:
            import yfinance as yf
            
            with self._measure_time() as timer:
                ticker = await asyncio.wait_for(
                    asyncio.to_thread(yf.Ticker, symbol),
                    timeout=self.timeout
                )
                info = await asyncio.wait_for(
                    asyncio.to_thread(lambda: ticker.info),
                    timeout=self.timeout
                )
            
            if info:
                price = info.get('regularMarketPrice') or info.get('currentPrice')
                if price:
                    return self._create_success_result(
                        timer.latency_ms,
                        f"{symbol}: ${price:,.2f}"
                    )
                return self._create_success_result(
                    timer.latency_ms,
                    f"{symbol}: Connected"
                )
            return self._create_fail_result(
                CheckStatus.ERROR,
                f"No data for {symbol}"
            )
            
        except asyncio.TimeoutError:
            return self._create_fail_result(
                CheckStatus.TIMEOUT,
                f"Timeout after {self.timeout}s"
            )
        except Exception as e:
            return self._create_fail_result(
                CheckStatus.FAIL,
                str(e)[:100]
            )
