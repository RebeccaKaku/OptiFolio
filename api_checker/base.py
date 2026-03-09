# api_checker/base.py
"""
API 检测器基类和数据结构定义
"""

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class CheckStatus(Enum):
    """检测状态枚举"""
    OK = "OK"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


@dataclass
class CheckResult:
    """
    单个 API 检测结果
    
    Attributes:
        name: API 名称
        status: 检测状态
        latency_ms: 响应延迟（毫秒）
        message: 详细信息
        timestamp: 检测时间
        extra: 额外信息
    """
    name: str
    status: CheckStatus
    latency_ms: Optional[float] = None
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    extra: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_ok(self) -> bool:
        """检测是否成功"""
        return self.status == CheckStatus.OK
    
    def __str__(self) -> str:
        """格式化输出"""
        status_icon = "[OK]" if self.is_ok else "[FAIL]"
        latency_str = f"{self.latency_ms:.0f}ms" if self.latency_ms is not None else "N/A"
        return f"{status_icon} {self.name:<20} - {self.status.value:<8} (latency: {latency_str}) {self.message}"


class APIChecker(ABC):
    """
    API 检测器抽象基类
    
    所有具体的 API 检测器都需要继承此类并实现 check() 方法
    """
    
    def __init__(self, name: str, timeout: float = 10.0):
        """
        初始化检测器
        
        Args:
            name: 检测器名称
            timeout: 超时时间（秒）
        """
        self.name = name
        self.timeout = timeout
        self.logger = logging.getLogger(f"api_checker.{name}")
    
    @abstractmethod
    async def check(self) -> CheckResult:
        """
        执行 API 检测（异步方法）
        
        Returns:
            CheckResult: 检测结果
        """
        pass
    
    def _create_success_result(self, latency_ms: float, message: str = "", **extra) -> CheckResult:
        """创建成功结果"""
        return CheckResult(
            name=self.name,
            status=CheckStatus.OK,
            latency_ms=latency_ms,
            message=message,
            extra=extra
        )
    
    def _create_fail_result(self, status: CheckStatus, message: str, **extra) -> CheckResult:
        """创建失败结果"""
        return CheckResult(
            name=self.name,
            status=status,
            message=message,
            extra=extra
        )
    
    def _measure_time(self) -> "_TimeMeasure":
        """创建时间测量上下文管理器"""
        return _TimeMeasure(self)


class _TimeMeasure:
    """时间测量上下文管理器"""
    
    def __init__(self, checker: APIChecker):
        self.checker = checker
        self.start_time: Optional[float] = None
        self.elapsed_ms: Optional[float] = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed_ms = (time.perf_counter() - self.start_time) * 1000
        return False
    
    @property
    def latency_ms(self) -> float:
        """获取延迟（毫秒）"""
        return self.elapsed_ms if self.elapsed_ms is not None else 0.0
