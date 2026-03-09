# api_checker/runner.py
"""
API 检测运行器
统一运行所有检测器，输出到控制台和日志文件
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from .base import APIChecker, CheckResult, CheckStatus
from .crypto_checker import CryptoAPIChecker
from .yahoo_checker import YahooAPIChecker
from .akshare_checker import AkshareAPIChecker


class APICheckerRunner:
    """
    API 检测运行器
    
    统一管理所有 API 检测器，并发执行检测，
    并将结果输出到控制台和日志文件
    """
    
    def __init__(
        self,
        log_dir: str = "logs",
        log_filename: Optional[str] = None,
        verbose: bool = True
    ):
        """
        初始化检测运行器
        
        Args:
            log_dir: 日志文件目录
            log_filename: 日志文件名，默认为 api_check_YYYYMMDD.log
            verbose: 是否输出详细信息到控制台
        """
        self.log_dir = log_dir
        self.log_filename = log_filename or f"api_check_{datetime.now().strftime('%Y%m%d')}.log"
        self.verbose = verbose
        self.checkers: List[APIChecker] = []
        self.results: List[CheckResult] = []
        
        # 设置日志
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志配置"""
        # 确保日志目录存在
        os.makedirs(self.log_dir, exist_ok=True)
        
        log_path = os.path.join(self.log_dir, self.log_filename)
        
        # 配置日志格式
        self.logger = logging.getLogger("api_checker")
        self.logger.setLevel(logging.INFO)
        
        # 清除已有的处理器
        self.logger.handlers.clear()
        
        # 文件处理器
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # 控制台处理器
        if self.verbose:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter('%(message)s')
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
    
    def add_checker(self, checker: APIChecker):
        """
        添加检测器
        
        Args:
            checker: API 检测器实例
        """
        self.checkers.append(checker)
    
    def add_default_checkers(
        self,
        crypto_exchanges: Optional[List[str]] = None
    ):
        """
        添加默认的检测器集合
        
        Args:
            crypto_exchanges: 加密货币交易所列表
        """
        self.checkers.clear()
        self.checkers.extend([
            CryptoAPIChecker(exchanges=crypto_exchanges),
            YahooAPIChecker(),
            AkshareAPIChecker(),
        ])
    
    async def run_all(self) -> List[CheckResult]:
        """
        并发运行所有检测器
        
        Returns:
            List[CheckResult]: 所有检测结果列表
        """
        if not self.checkers:
            self.add_default_checkers()
        
        self.results.clear()
        
        # 打印报告头
        self._print_header()
        
        # 并发执行所有检测
        tasks = [checker.check() for checker in self.checkers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # 如果检测器本身抛出异常，创建一个错误结果
                error_result = CheckResult(
                    name=self.checkers[i].name,
                    status=CheckStatus.ERROR,
                    message=f"Checker exception: {str(result)[:100]}"
                )
                self.results.append(error_result)
                self._print_result(error_result)
            else:
                self.results.append(result)
                self._print_result(result)
        
        # 打印汇总
        self._print_summary()
        
        return self.results
    
    def _print_header(self):
        """打印报告头"""
        header = f"\n{'='*60}\nAPI Health Check Report\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}"
        self.logger.info(header)
    
    def _print_result(self, result: CheckResult):
        """打印单个检测结果"""
        # 主结果
        self.logger.info(str(result))
        
        # 如果有详细的交易所结果，也打印出来
        if 'exchange_results' in result.extra:
            self.logger.info("  Exchange details:")
            for ex_name, ex_result in result.extra['exchange_results'].items():
                status_icon = "[OK]" if ex_result.is_ok else "[FAIL]"
                latency_str = f"{ex_result.latency_ms:.0f}ms" if ex_result.latency_ms else "N/A"
                self.logger.info(f"    {status_icon} {ex_name:<15} - {ex_result.status.value:<8} ({latency_str}) {ex_result.message}")
    
    def _print_summary(self):
        """打印汇总信息"""
        total = len(self.results)
        success = sum(1 for r in self.results if r.is_ok)
        
        # 计算平均延迟
        latencies = [r.latency_ms for r in self.results if r.latency_ms is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        
        summary = f"{'='*60}\nSummary: {success}/{total} APIs available | Avg latency: {avg_latency:.0f}ms\n{'='*60}"
        self.logger.info(summary)
    
    def get_summary(self) -> Dict[str, Any]:
        """
        获取检测结果汇总（供程序调用）
        
        Returns:
            Dict: 汇总信息字典
        """
        total = len(self.results)
        success = sum(1 for r in self.results if r.is_ok)
        
        return {
            'timestamp': datetime.now().isoformat(),
            'total': total,
            'success': success,
            'failed': total - success,
            'success_rate': success / total if total > 0 else 0,
            'results': [
                {
                    'name': r.name,
                    'status': r.status.value,
                    'latency_ms': r.latency_ms,
                    'message': r.message,
                    'is_ok': r.is_ok
                }
                for r in self.results
            ]
        }
    
    def get_failed_results(self) -> List[CheckResult]:
        """获取所有失败的检测结果"""
        return [r for r in self.results if not r.is_ok]
    
    def get_successful_results(self) -> List[CheckResult]:
        """获取所有成功的检测结果"""
        return [r for r in self.results if r.is_ok]


async def quick_check(
    crypto_exchanges: Optional[List[str]] = None,
    log_dir: str = "logs"
) -> Dict[str, Any]:
    """
    快速执行 API 检测（便捷函数）
    
    Args:
        crypto_exchanges: 加密货币交易所列表
        log_dir: 日志目录
        
    Returns:
        Dict: 检测结果汇总
    """
    runner = APICheckerRunner(log_dir=log_dir)
    runner.add_default_checkers(crypto_exchanges=crypto_exchanges)
    await runner.run_all()
    return runner.get_summary()


def run_check(
    crypto_exchanges: Optional[List[str]] = None,
    log_dir: str = "logs"
) -> Dict[str, Any]:
    """
    同步方式执行 API 检测（便捷函数）
    
    Args:
        crypto_exchanges: 加密货币交易所列表
        log_dir: 日志目录
        
    Returns:
        Dict: 检测结果汇总
    """
    return asyncio.run(quick_check(crypto_exchanges, log_dir))


# 命令行入口
if __name__ == "__main__":
    import sys
    
    # 解析命令行参数
    exchanges = None
    log_dir = "logs"
    
    if len(sys.argv) > 1:
        # 第一个参数可以是交易所列表，用逗号分隔
        exchanges = sys.argv[1].split(',')
    
    if len(sys.argv) > 2:
        # 第二个参数是日志目录
        log_dir = sys.argv[2]
    
    # 执行检测
    run_check(crypto_exchanges=exchanges, log_dir=log_dir)
