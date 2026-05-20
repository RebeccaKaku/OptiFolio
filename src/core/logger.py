"""
统一日志管理模块

提供标准化的日志配置和工具，支持：
1. 控制台和文件输出
2. 不同级别的日志记录
3. 结构化日志格式
4. 模块特定的日志器
"""

import logging
import sys
import os
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path


class FMLogger:
    """FM系统日志管理器"""
    
    _instance: Optional['FMLogger'] = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if FMLogger._initialized:
            return
            
        self.loggers: Dict[str, logging.Logger] = {}
        self.default_level = logging.INFO
        self.log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        self.date_format = '%Y-%m-%d %H:%M:%S'
        self.log_dir = Path("logs")
        self._setup_log_directory()
        
        FMLogger._initialized = True
    
    def _setup_log_directory(self):
        """创建日志目录"""
        self.log_dir.mkdir(exist_ok=True)
    
    def get_logger(self, name: str = "FM", level: Optional[int] = None) -> logging.Logger:
        """
        获取或创建日志器
        
        Args:
            name: 日志器名称
            level: 日志级别（可选）
            
        Returns:
            配置好的日志器
        """
        if name in self.loggers:
            return self.loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(level or self.default_level)
        
        # 避免重复添加处理器
        if not logger.handlers:
            # 控制台处理器
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                '[%(levelname)s] %(message)s',
                datefmt=self.date_format
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
            
            # 文件处理器
            log_file = self.log_dir / f"{name.lower()}_{datetime.now().strftime('%Y%m%d')}.log"
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                self.log_format,
                datefmt=self.date_format
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        
        self.loggers[name] = logger
        return logger
    
    def set_global_level(self, level: int):
        """设置全局日志级别"""
        self.default_level = level
        for logger in self.loggers.values():
            logger.setLevel(level)
    
    def cleanup_old_logs(self, days: int = 30):
        """清理旧日志文件"""
        cutoff = datetime.now().timestamp() - (days * 24 * 3600)
        
        for log_file in self.log_dir.glob("*.log"):
            if log_file.stat().st_mtime < cutoff:
                try:
                    log_file.unlink()
                except OSError:
                    pass


# 便捷函数
def get_logger(name: str = "FM") -> logging.Logger:
    """获取日志器的便捷函数"""
    return FMLogger().get_logger(name)


def log_operation(logger: logging.Logger, operation: str, details: Dict[str, Any] = None):
    """
    记录操作日志
    
    Args:
        logger: 日志器
        operation: 操作名称
        details: 操作详情
    """
    msg = f"[{operation}]"
    if details:
        detail_str = ", ".join(f"{k}={v}" for k, v in details.items())
        msg += f" {detail_str}"
    logger.info(msg)


def log_error(logger: logging.Logger, operation: str, error: Exception, 
              details: Dict[str, Any] = None):
    """
    记录错误日志
    
    Args:
        logger: 日志器
        operation: 操作名称
        error: 异常对象
        details: 额外详情
    """
    msg = f"[{operation}] Error: {str(error)}"
    if details:
        detail_str = ", ".join(f"{k}={v}" for k, v in details.items())
        msg += f" | Details: {detail_str}"
    logger.error(msg, exc_info=True)


# 预定义的模块日志器
def get_asset_logger() -> logging.Logger:
    """获取资产模块日志器"""
    return get_logger("FM.Asset")


def get_data_logger() -> logging.Logger:
    """获取数据模块日志器"""
    return get_logger("FM.Data")


def get_portfolio_logger() -> logging.Logger:
    """获取组合模块日志器"""
    return get_logger("FM.Portfolio")


def get_strategy_logger() -> logging.Logger:
    """获取策略模块日志器"""
    return get_logger("FM.Strategy")


# 兼容性：替换旧的print语句的辅助函数
def info(msg: str, module: str = "System"):
    """记录信息日志（兼容旧代码）"""
    get_logger(f"FM.{module}").info(msg)


def warning(msg: str, module: str = "System"):
    """记录警告日志（兼容旧代码）"""
    get_logger(f"FM.{module}").warning(msg)


def error(msg: str, module: str = "System"):
    """记录错误日志（兼容旧代码）"""
    get_logger(f"FM.{module}").error(msg)


def debug(msg: str, module: str = "System"):
    """记录调试日志（兼容旧代码）"""
    get_logger(f"FM.{module}").debug(msg)