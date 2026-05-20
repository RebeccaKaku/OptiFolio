# api_checker/akshare_checker.py
"""
Akshare API 检测器
检测 Akshare 数据源的 API 连通性
"""

import asyncio
from typing import Optional

from .base import APIChecker, CheckResult, CheckStatus


class AkshareAPIChecker(APIChecker):
    """
    Akshare 数据源 API 检测器
    
    检测 Akshare 库的中国金融数据 API 连通性
    """
    
    def __init__(self, name: str = "Akshare", timeout: float = 20.0):
        """
        初始化 Akshare API 检测器
        
        Args:
            name: 检测器名称
            timeout: 超时时间（秒），Akshare 可能较慢
        """
        super().__init__(name, timeout)
    
    async def check(self) -> CheckResult:
        """
        检测 Akshare API 连通性
        
        通过获取实时指数数据来验证连通性
        
        Returns:
            CheckResult: 检测结果
        """
        try:
            import akshare as ak
            
            with self._measure_time() as timer:
                # 使用实时指数数据作为连通性测试（较快）
                # 获取上证指数实时行情
                df = await asyncio.wait_for(
                    asyncio.to_thread(ak.stock_zh_index_spot_em, symbol="上证系列指数"),
                    timeout=self.timeout
                )
            
            if df is not None and not df.empty:
                # 尝试获取上证指数的最新价格
                try:
                    sh_index = df[df['代码'] == '000001']
                    if not sh_index.empty:
                        price = sh_index['最新价'].values[0]
                        change = sh_index['涨跌幅'].values[0]
                        return self._create_success_result(
                            timer.latency_ms,
                            f"上证指数: {price} ({change}%)"
                        )
                except (KeyError, IndexError):
                    pass
                
                # 即使没有解析出具体价格，有数据返回就算成功
                return self._create_success_result(
                    timer.latency_ms,
                    f"Connected ({len(df)} indices available)"
                )
            else:
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
                "akshare library not installed. Run: pip install akshare"
            )
        except Exception as e:
            error_msg = str(e)
            # 常见错误信息简化
            if "网络" in error_msg or "连接" in error_msg or "connection" in error_msg.lower():
                return self._create_fail_result(
                    CheckStatus.FAIL,
                    f"Network error: {error_msg[:80]}"
                )
            elif "timeout" in error_msg.lower():
                return self._create_fail_result(
                    CheckStatus.TIMEOUT,
                    "Request timeout"
                )
            return self._create_fail_result(
                CheckStatus.ERROR,
                f"Error: {error_msg[:80]}"
            )
    
    async def check_fund_list(self) -> CheckResult:
        """
        检测基金名录获取功能
        
        Returns:
            CheckResult: 检测结果
        """
        try:
            import akshare as ak
            
            with self._measure_time() as timer:
                df = await asyncio.wait_for(
                    asyncio.to_thread(ak.fund_name_em),
                    timeout=self.timeout
                )
            
            if df is not None and not df.empty:
                return self._create_success_result(
                    timer.latency_ms,
                    f"Found {len(df)} funds"
                )
            return self._create_fail_result(
                CheckStatus.ERROR,
                "No fund data returned"
            )
            
        except asyncio.TimeoutError:
            return self._create_fail_result(
                CheckStatus.TIMEOUT,
                f"Timeout after {self.timeout}s"
            )
        except ImportError:
            return self._create_fail_result(
                CheckStatus.ERROR,
                "akshare library not installed"
            )
        except Exception as e:
            return self._create_fail_result(
                CheckStatus.FAIL,
                str(e)[:100]
            )
    
    async def check_stock_realtime(self) -> CheckResult:
        """
        检测 A 股实时行情获取功能
        
        Returns:
            CheckResult: 检测结果
        """
        try:
            import akshare as ak
            
            with self._measure_time() as timer:
                df = await asyncio.wait_for(
                    asyncio.to_thread(ak.stock_zh_a_spot_em),
                    timeout=self.timeout
                )
            
            if df is not None and not df.empty:
                return self._create_success_result(
                    timer.latency_ms,
                    f"Found {len(df)} A-share stocks"
                )
            return self._create_fail_result(
                CheckStatus.ERROR,
                "No stock data returned"
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
