# api_checker/crypto_checker.py
"""
加密货币 API 检测器
检测 CCXT 支持的交易所 API 连通性
"""

import asyncio
from typing import List, Optional

from .base import APIChecker, CheckResult, CheckStatus


class CryptoAPIChecker(APIChecker):
    """
    加密货币交易所 API 检测器
    
    通过 CCXT 库检测交易所 API 的连通性
    """
    
    # 默认检测的交易所列表
    DEFAULT_EXCHANGES = ['binance', 'okx', 'kraken']
    
    # 检测用的交易对
    TEST_SYMBOL = 'BTC/USDT'
    
    def __init__(
        self, 
        name: str = "Crypto",
        exchanges: Optional[List[str]] = None,
        timeout: float = 10.0
    ):
        """
        初始化加密货币 API 检测器
        
        Args:
            name: 检测器名称
            exchanges: 要检测的交易所列表，默认为 ['binance', 'okx', 'kraken']
            timeout: 超时时间（秒）
        """
        super().__init__(name, timeout)
        self.exchanges = exchanges or self.DEFAULT_EXCHANGES
    
    async def check(self) -> CheckResult:
        """
        检测所有配置的交易所 API
        
        Returns:
            CheckResult: 汇总检测结果
        """
        results = {}
        total_latency = 0.0
        success_count = 0
        
        for exchange_id in self.exchanges:
            result = await self._check_single_exchange(exchange_id)
            results[exchange_id] = result
            if result.is_ok:
                success_count += 1
                total_latency += result.latency_ms or 0
        
        # 计算平均延迟
        avg_latency = total_latency / success_count if success_count > 0 else None
        
        # 构建汇总消息
        if success_count == len(self.exchanges):
            status = CheckStatus.OK
            message = f"All {len(self.exchanges)} exchanges available"
        elif success_count > 0:
            status = CheckStatus.OK
            failed = [ex for ex, r in results.items() if not r.is_ok]
            message = f"{success_count}/{len(self.exchanges)} available. Failed: {', '.join(failed)}"
        else:
            status = CheckStatus.FAIL
            message = "All exchanges unavailable"
        
        return CheckResult(
            name=self.name,
            status=status,
            latency_ms=avg_latency,
            message=message,
            extra={"exchange_results": results}
        )
    
    async def _check_single_exchange(self, exchange_id: str) -> CheckResult:
        """
        检测单个交易所 API
        
        Args:
            exchange_id: 交易所 ID（如 'binance', 'okx'）
            
        Returns:
            CheckResult: 检测结果
        """
        try:
            # 动态导入 ccxt
            import ccxt.async_support as ccxt
            
            exchange_class = getattr(ccxt, exchange_id, None)
            if exchange_class is None:
                return self._create_fail_result(
                    CheckStatus.ERROR,
                    f"Unknown exchange: {exchange_id}"
                )
            
            exchange = exchange_class({
                'enableRateLimit': True,
                'timeout': int(self.timeout * 1000),
            })
            
            try:
                # 使用 fetch_ticker 获取行情作为连通性测试
                with self._measure_time() as timer:
                    ticker = await asyncio.wait_for(
                        exchange.fetch_ticker(self.TEST_SYMBOL),
                        timeout=self.timeout
                    )
                
                # 验证返回数据
                if ticker and 'last' in ticker:
                    price = ticker['last']
                    return self._create_success_result(
                        timer.latency_ms,
                        f"BTC/USDT: ${price:,.2f}"
                    )
                else:
                    return self._create_fail_result(
                        CheckStatus.ERROR,
                        "Invalid response format"
                    )
                    
            except asyncio.TimeoutError:
                return self._create_fail_result(
                    CheckStatus.TIMEOUT,
                    f"Timeout after {self.timeout}s"
                )
            except Exception as e:
                return self._create_fail_result(
                    CheckStatus.FAIL,
                    str(e)[:100]  # 限制错误消息长度
                )
            finally:
                await exchange.close()
                
        except ImportError:
            return self._create_fail_result(
                CheckStatus.ERROR,
                "ccxt library not installed. Run: pip install ccxt"
            )
        except Exception as e:
            return self._create_fail_result(
                CheckStatus.ERROR,
                f"Unexpected error: {str(e)[:100]}"
            )
    
    async def check_exchange(self, exchange_id: str) -> CheckResult:
        """
        检测指定交易所（公开方法）
        
        Args:
            exchange_id: 交易所 ID
            
        Returns:
            CheckResult: 检测结果
        """
        return await self._check_single_exchange(exchange_id)
